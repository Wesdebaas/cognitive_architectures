"""Knowledge: stores what is asserted, and reads what the KB says about goals, items, targets, words, action types and
persistences."""

import pyoxigraph as ox
from awareness_msgs.msg import Assertion

from .kb import AM, RDF, RDFS, node, short, stored


class Knowledge:

    def __init__(self, kb, claim):
        self.kb = kb
        self.claim = claim   # the claim every belief makes, e.g. present
        self.assertions = 0

    def assert_knowledge(self, turtle, t):
        """Store knowledge given as Turtle. Returns the items it introduces."""
        triples = list(ox.parse(turtle, format=ox.RdfFormat.TURTLE))
        items = {short(triple.subject) for triple in triples
                 if triple.predicate == ox.NamedNode(f'{RDF}type') and triple.object == node('Item')}
        known = {short(row['item']) for row in self.kb.query(f'SELECT ?item WHERE {{ ?item a <{AM}Item> }}')}
        self.assertions += 1
        introduced = sorted(items - known)
        self.kb.write(Assertion(number=self.assertions, t=float(t), introduced=introduced,
                                triples=ox.serialize(triples, format=ox.RdfFormat.N_TRIPLES).decode()),
                      stored(f'assertion_{self.assertions}'))
        return introduced

    def reload(self):
        """Read again what an assertion can change."""
        self.one_place = bool(list(self.kb.query(f'SELECT * WHERE {{ <{AM}{self.claim}> a <{AM}OnePlaceClaim> }}')))
        self.goals = self.read_goals()
        self.types = self.read_action_types()
        self.persistences = self.read_persistences()
        self.actions = list(self.actions_observing({}))

    def read_goals(self):
        """Everything that requires a condition."""
        query = f'SELECT DISTINCT ?goal WHERE {{ ?goal <{AM}requires> ?condition }}'
        return sorted(short(row['goal']) for row in self.kb.query(query))

    def items(self, goal):
        """{item: its classes} for every item the goal needs."""
        query = f'''SELECT ?item ?class WHERE {{
            <{AM}{goal}> <{AM}requires> ?condition . ?condition <{AM}about> ?item .
            ?item a ?class FILTER(?class != <{AM}Item>) }}'''
        items = {}
        for row in self.kb.query(query):
            items.setdefault(short(row['item']), set()).add(row['class'].value)
        return items

    def targets(self):
        """[(word, target)], one pair per word of the target's class."""
        query = f'SELECT ?target ?word WHERE {{ ?target a <{AM}Place> , ?class . ?class <{AM}word> ?word }}'
        return [(row['word'].value, short(row['target'])) for row in self.kb.query(query)]

    def words(self, classes):
        values = ' '.join(f'<{cls}>' for cls in classes)
        query = f'SELECT DISTINCT ?word WHERE {{ VALUES ?class {{ {values} }} ?class <{AM}word> ?word }}'
        return {row['word'].value for row in self.kb.query(query)}

    def parents(self, classes):
        """The named classes one subClassOf step up."""
        values = ' '.join(f'<{cls}>' for cls in classes)
        query = f'SELECT DISTINCT ?parent WHERE {{ VALUES ?class {{ {values} }} ?class <{RDFS}subClassOf> ?parent FILTER isIRI(?parent) }}'
        return {row['parent'].value for row in self.kb.query(query)}

    def read_action_types(self):
        """{action type: (classes it applies to, claim it observes, duration in seconds, complete)}."""
        query = f'''SELECT ?type ?class ?claim ?duration ?complete WHERE {{
            ?type a <{AM}ActionType> ; <{AM}appliesTo> ?class ; <{AM}observesClaim> ?claim ; <{AM}duration> ?duration ;
                  <{AM}complete> ?complete }}'''
        types = {}
        for row in self.kb.query(query):
            classes, claim, duration, complete = types.get(short(row['type']), (
                set(), row['claim'].value, float(row['duration'].value), row['complete'].value == 'true'))
            types[short(row['type'])] = (classes | {row['class'].value}, claim, duration, complete)
        return types

    def instances(self, cls):
        """Everything of class cls or a class below it."""
        query = f'SELECT DISTINCT ?thing WHERE {{ ?thing a/<{RDFS}subClassOf>* <{cls}> }}'
        return {short(row['thing']) for row in self.kb.query(query)}

    def actions_observing(self, beliefs):
        """{(action type, target): the beliefs it observes}, for every target of every action type's classes."""
        actions = {}
        for action_type, (classes, claim, duration, complete) in sorted(self.read_action_types().items()):
            targets = set.intersection(*(self.instances(cls) for cls in classes))
            for target in sorted(targets):
                actions[(action_type, target)] = [b for b in beliefs if b[1] == target and b[2] == claim]
        return actions

    def read_persistences(self):
        """{item: seconds} for every item with an am:persistence."""
        query = f'SELECT ?item ?seconds WHERE {{ ?item <{AM}persistence> ?seconds }}'
        return {short(row['item']): float(row['seconds'].value) for row in self.kb.query(query)}
