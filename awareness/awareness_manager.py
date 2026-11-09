"""The awareness manager. Knows no scenario, ontology or commonsense source: a scenario's scenario.py
gives it everything it uses. No ROS.

  knowledge        one RDF store: goals, conditions, places, items, their words, action types, and an ontology,
                   in its default graph. The awareness manager writes into three named graphs of the same store
                   (see below), so whatever can read the store can read what it derived, observed and decided.
  association      word -> [(word, w)]: the things a source associates with a word, w = weight of evidence (adds up).
                   Each (item, thing) pair becomes a belief about the item at that thing.
  claim            what such a belief claims about the item at the thing (for an AtLocation source: "present");
                   an action type observes the beliefs whose claim it declares.
  transition_cost  (from, to) -> seconds to get into position for an action at `to`, or None if impossible.
                   Travel time for a driving robot, turning time for a pan-tilt camera, 0 for a fixed sensor.
  parameters       {'T': seconds until a belief is fully stale, 'idle_threshold': P below which nothing is done,
                    'c': see support, 'alpha': see discount, 'find_votes': see derivations,
                    'horizon_halflife': see goal_weights}

Every goal's beliefs are derived at the start (prepare), again whenever knowledge is told during a run (tell), and again
whenever an item is found where it was not known to be (observe): a find is evidence, next to the source's. At
run time it is told when goals will arrive (announce), which goal is active (set_goal) and what an action reported at
its target (observe), and asked what to do next (decide). A goal switch keeps every observation. P weighs every goal:
the active one fully, an announced one less the further away its arrival is (goal_weights), so the robot can look for
the next goal's items before it arrives.

Observations are stored apart from beliefs: what was seen is a fact about the world, a belief is a hypothesis. An action
reports a value of its claim for the items it assessed at its target. An action type declared complete assesses every
item there: an item it did not report has the claim false (looking in a cupboard: what is not seen is not there).
A claim the knowledge declares an am:OnePlaceClaim holds at one place at a time: an item reported at one place has it
false at every other place (one knife cannot be in two drawers).

  am:derived       the beliefs, amended by derive so it always matches what follows from the default graph. A belief
                   names its claim with rdf:reifies (RDF 1.2), which states the claim without asserting it, and
                   carries its A (am:relevance), how A was derived (am:votes w, am:votesFrom the classes the votes
                   came from, am:discount, one am:edge per association edge used, am:finds n) and the goals that
                   need it:
                     am:belief_cup_1_present_cupboard_1 rdf:reifies <<( am:cup_1 am:present am:cupboard_1 )>> ;
                         am:relevance 0.26 ; am:votes 3.0 ; am:votesFrom SOMA:Cup ; am:discount 1.0 ; am:finds 0 ;
                         am:edge am:belief_cup_1_present_cupboard_1_edge_1 ; am:neededFor am:breakfast , am:coffee .
                     am:belief_cup_1_present_cupboard_1_edge_1 am:word "cup" ; am:placeWord "cupboard" ; am:votes 3.0 .
  am:observations  one am:Look per observation, one am:Telling per telling and one am:Announcement per announced goal
                   arrival, only ever added to:
                     am:look_7 a am:Look ; am:action am:inspect ; am:target am:table_1 ; am:claim "present" ;
                         am:t 263 ; am:complete true ; am:reported [ am:item am:cup_1 ; am:value true ; am:find true ] .
                     am:telling_1 a am:Telling ; am:t 50 ; am:introduced am:knife_1 .
                     am:announcement_3 a am:Announcement ; am:goal am:lunch ; am:arrival 3000 .
  am:decisions     one am:Decision per decision, only ever added to: what was weighed and what was chosen. A wait
                   has no am:chosenAction and is written once, when it starts:
                     am:decision_3 a am:Decision ; am:t 263 ; am:position am:dock ; am:goal am:breakfast ;
                         am:chosenAction am:inspect ; am:chosenTarget am:table_1 ;
                         am:option [ am:action am:inspect ; am:target am:table_1 ;
                                     am:priority 0.61 ; am:cost 25.0 ; am:utility 0.0244 ] ;
                         am:goalWeight [ am:goal am:breakfast ; am:value 1.0 ] , [ am:goal am:coffee ; am:value 0.13 ] ;
                         am:staleness [ am:belief am:belief_cup_1_present_table_1 ; am:value 1.0 ] .
                   priority = P, cost = C, utility = U, staleness = E. An unreachable option has no cost or utility.
"""

import math

import pyoxigraph as ox

AM = 'http://example.org/awareness-manager#'
RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
RDFS = 'http://www.w3.org/2000/01/rdf-schema#'
DERIVED = ox.NamedNode(f'{AM}derived')
OBSERVATIONS = ox.NamedNode(f'{AM}observations')
DECISIONS = ox.NamedNode(f'{AM}decisions')


def short(term):
    if isinstance(term, ox.BlankNode):
        return '[anonymous]'
    return term.value.split('#')[-1]


def node(name):
    return ox.NamedNode(f'{AM}{name}')


def value(literal):
    """A literal as the Python value it was written from: bool, int or float, else its text."""
    datatype = literal.datatype.value.split('#')[-1]
    if datatype == 'boolean':
        return literal.value == 'true'
    if datatype == 'integer':
        return int(literal.value)
    if datatype in ('double', 'decimal', 'float'):
        return float(literal.value)
    return literal.value


def support(w, c):
    """Shafer's degree of support from weight of evidence w: 1 - e^(c*w), c < 0."""
    return 1 - math.exp(c * w)


class AwarenessManager:

    def __init__(self, knowledge, association, claim, transition_cost, parameters):
        self.knowledge = knowledge
        self.association = association
        self.claim = claim
        self.transition_cost = transition_cost
        self.parameters = parameters
        self.associated = {}   # word -> what the source associates with it; the source does not change during a run
        self.observed = {}     # belief -> its last observation; only observe and tell change it, and both empty this
        self.weights = {}      # (t, active goal) -> goal_weights; announce and derive empty this

    def beliefs(self, goal):
        """{(item, place, claim): A} for every place the association source links to an item the goal needs."""
        return {belief: how['A'] for belief, how in self.derivations(goal).items()}

    def derivations(self, goal):
        """{(item, place, claim): how its A was derived} for every place the association source links to an item the
        goal needs, or the item was found at: w (the votes of the nearest class level that has any), the classes they
        came from, the discount, the edges (word, place word, votes) behind w, and n, how often the item was found there.

        The source and the finds are two independent pieces of evidence for the same claim, combined as Shafer combines
        two simple support functions:
          A_source = discount x (1 - e^(c*w))      A_finds = 1 - e^(c * find_votes * n)
          A = 1 - (1 - A_source)(1 - A_finds) = A_source + A_finds - A_source x A_finds
        A finding counts as find_votes votes of the source would. Neither can rule a place out: A stays below 1.
        """
        places = self.places()
        c = self.parameters['c']
        found = {}
        for item, classes in self.items(goal).items():
            votes, source = self.nearest_evidence(classes, places)
            trust = self.discount(classes, source)
            edges = self.edges(self.words(source), places)
            finds = self.finds(item)
            for place in set(votes) | set(finds):
                w, n = votes.get(place, 0.0), finds.get(place, 0)
                from_source = trust * support(w, c)
                from_finds = support(self.parameters['find_votes'] * n, c)
                found[(item, place, self.claim)] = {
                    'A': from_source + from_finds - from_source * from_finds, 'w': w, 'discount': trust,
                    'from': sorted(source), 'edges': sorted(edges.get(place, [])), 'finds': n,
                    'A_source': from_source, 'A_finds': from_finds}
        return dict(sorted(found.items()))

    def finds(self, item):
        """{place: how often the item was found there}: looks that reported it where it was not known to be (observe)."""
        query = f'''SELECT ?place (COUNT(?look) AS ?n) WHERE {{ GRAPH <{OBSERVATIONS.value}> {{
            ?look a <{AM}Look> ; <{AM}target> ?place ; <{AM}claim> "{self.claim}" ; <{AM}reported> ?report .
            ?report <{AM}item> <{AM}{item}> ; <{AM}find> true }} }} GROUP BY ?place'''
        return {short(row['place']): value(row['n']) for row in self.knowledge.query(query)}

    def goals(self):
        """Every goal: everything that requires a condition."""
        query = f'SELECT DISTINCT ?goal WHERE {{ ?goal <{AM}requires> ?condition }}'
        return sorted(short(row['goal']) for row in self.knowledge.query(query))

    def items(self, goal):
        """{item: its classes} for every item a condition of the goal is about."""
        query = f'''SELECT ?item ?class WHERE {{
            <{AM}{goal}> <{AM}requires> ?condition . ?condition <{AM}about> ?item .
            ?item a ?class FILTER(?class != <{AM}Item>) }}'''
        items = {}
        for row in self.knowledge.query(query):
            items.setdefault(short(row['item']), set()).add(row['class'].value)
        return items

    def places(self):
        """[(word, place)] for every place, one pair per word of its class."""
        query = f'SELECT ?place ?word WHERE {{ ?place a <{AM}Place> , ?class . ?class <{AM}word> ?word }}'
        return [(row['word'].value, short(row['place'])) for row in self.knowledge.query(query)]

    def words(self, classes):
        """The words on these classes."""
        values = ' '.join(f'<{cls}>' for cls in classes)
        query = f'SELECT DISTINCT ?word WHERE {{ VALUES ?class {{ {values} }} ?class <{AM}word> ?word }}'
        return {row['word'].value for row in self.knowledge.query(query)}

    def parents(self, classes):
        """The named classes one subClassOf step above these classes."""
        values = ' '.join(f'<{cls}>' for cls in classes)
        query = f'SELECT DISTINCT ?parent WHERE {{ VALUES ?class {{ {values} }} ?class <{RDFS}subClassOf> ?parent FILTER isIRI(?parent) }}'
        return {row['parent'].value for row in self.knowledge.query(query)}

    def edges(self, words, places):
        """{place: [(word, place word, votes)]}: every edge from these words to a place's word."""
        edges = {}
        for word in words:
            if word not in self.associated:
                self.associated[word] = self.association(word)
            for end, w in self.associated[word]:
                for place_word, place in places:
                    if end == place_word:
                        edges.setdefault(place, []).append((word, place_word, w))
        return edges

    def evidence(self, words, places):
        """{place: w}: votes summed over every edge from these words to a place's word."""
        return {place: sum(w for word, place_word, w in edges) for place, edges in self.edges(words, places).items()}

    def nearest_evidence(self, classes, places):
        """(votes, the classes they came from): climb from the classes, one level at a time, until a level has votes."""
        level, seen = set(classes), set()
        while level:
            votes = self.evidence(self.words(level), places)
            if votes:
                return votes, level
            seen |= level
            level = self.parents(level) - seen
        return {}, set()

    def discount(self, own, source):
        """How much votes borrowed from the source classes count for an item of the own classes: 1 - alpha, or 1 if not borrowed."""
        return 1.0 if source == own else 1 - self.parameters['alpha']

    def action_types(self):
        """{action type: (classes it applies to, claim it observes, duration in seconds, complete)}, as declared."""
        query = f'''SELECT ?type ?class ?claim ?duration ?complete WHERE {{
            ?type a <{AM}ActionType> ; <{AM}appliesTo> ?class ; <{AM}observesClaim> ?claim ; <{AM}duration> ?duration ;
                  <{AM}complete> ?complete }}'''
        types = {}
        for row in self.knowledge.query(query):
            classes, claim, duration, complete = types.get(short(row['type']), (
                set(), row['claim'].value, float(row['duration'].value), row['complete'].value == 'true'))
            types[short(row['type'])] = (classes | {row['class'].value}, claim, duration, complete)
        return types

    def instances(self, cls):
        """Every thing whose class is cls or below it."""
        query = f'SELECT DISTINCT ?thing WHERE {{ ?thing a/<{RDFS}subClassOf>* <{cls}> }}'
        return {short(row['thing']) for row in self.knowledge.query(query)}

    def actions(self, goal):
        """{(action type, target): B(o)}: B(o) = the goal's beliefs the action observes."""
        return self.observed_by(self.beliefs(goal))

    def observed_by(self, beliefs):
        """{(action type, target): the beliefs it observes}: one action per thing that is an instance of every class
        its type applies to; it observes the beliefs whose place is the target and whose claim is the one the type observes.
        """
        actions = {}
        for action_type, (classes, claim, duration, complete) in sorted(self.action_types().items()):
            targets = set.intersection(*(self.instances(cls) for cls in classes))
            for target in sorted(targets):
                actions[(action_type, target)] = [b for b in beliefs if b[1] == target and b[2] == claim]
        return actions

    # ---- run time ----

    def prepare(self):
        """Derive every goal's beliefs and every action from the knowledge at the start. No goal is active and nothing is
        observed yet.

        A belief and its A do not depend on the goal, so one belief can belong to several goals (a shared item).
        """
        for graph in (DERIVED, OBSERVATIONS, DECISIONS):
            self.knowledge.clear_graph(graph)
        self.observed = {}
        self.derive()
        self.goal = None

    def derive(self):
        """Derive every goal's beliefs and every action from what the store holds now, and amend am:derived to match:
        what is new is added, what no longer follows is removed, what is unchanged is left alone.
        Returns (added, removed, changed): the beliefs that appeared, disappeared, and kept their place with another A."""
        before = self.a
        wanted = set()
        self.one_place = bool(self.knowledge.query(f'ASK {{ <{AM}{self.claim}> a <{AM}OnePlaceClaim> }}'))
        self.prepared_goals = self.goals()   # the goals whose beliefs were derived; set_goal accepts only these
        for goal in self.prepared_goals:
            for belief, how in self.derivations(goal).items():
                wanted |= self.belief_quads(belief, how, goal)
        present = set(self.knowledge.quads_for_pattern(None, None, None, DERIVED))
        for quad in present - wanted:
            self.knowledge.remove(quad)
        self.knowledge.extend(wanted - present)
        self.actions = list(self.observed_by({}))
        self.types = self.action_types()
        self.weights = {}
        after = self.a
        return (sorted(set(after) - set(before)), sorted(set(before) - set(after)),
                sorted(b for b in after if b in before and after[b] != before[b]))

    def belief_quads(self, belief, how, goal):
        """The quads that state a belief in am:derived: the claim it names, its A and how A was derived, and one goal
        that needs it. The same belief for another goal gives the same quads plus that goal."""
        item, place, claim = belief
        name = self.belief_node(belief)
        triples = [(name, ox.NamedNode(f'{RDF}reifies'), ox.Triple(node(item), node(claim), node(place))),
                   (name, node('relevance'), ox.Literal(how['A'])), (name, node('votes'), ox.Literal(how['w'])),
                   (name, node('discount'), ox.Literal(how['discount'])), (name, node('finds'), ox.Literal(how['finds'])),
                   (name, node('neededFor'), node(goal))]
        triples += [(name, node('votesFrom'), ox.NamedNode(cls)) for cls in how['from']]
        for number, (word, place_word, votes) in enumerate(how['edges'], 1):
            edge = node(f'{name.value.split("#")[-1]}_edge_{number}')
            triples += [(name, node('edge'), edge), (edge, node('word'), ox.Literal(word)),
                        (edge, node('placeWord'), ox.Literal(place_word)), (edge, node('votes'), ox.Literal(votes))]
        return {ox.Quad(*triple, DERIVED) for triple in triples}

    def explanations(self):
        """[{item, place, claim, A, w, discount, finds, A_source, A_finds, from, edges, goals}] for every belief in
        am:derived: how its A was derived, read back from the store (A_source and A_finds are recomputed from it)."""
        def rows(pattern, *names):
            query = f'''SELECT ?item ?claim ?place {" ".join("?" + n for n in names)} WHERE {{ GRAPH <{DERIVED.value}> {{
                ?belief <{RDF}reifies> <<( ?item ?claim ?place )>> . {pattern} }} }}'''
            for row in self.knowledge.query(query):
                yield (short(row['item']), short(row['place']), short(row['claim'])), row
        found = {}
        c = self.parameters['c']
        for belief, row in rows(f'?belief <{AM}relevance> ?a ; <{AM}votes> ?w ; <{AM}discount> ?d ; <{AM}finds> ?n .',
                                'a', 'w', 'd', 'n'):
            w, d, n = value(row['w']), value(row['d']), value(row['n'])
            found[belief] = {'item': belief[0], 'place': belief[1], 'claim': belief[2], 'A': round(value(row['a']), 4),
                             'w': w, 'discount': d, 'finds': n, 'A_source': round(d * support(w, c), 4),
                             'A_finds': round(support(self.parameters['find_votes'] * n, c), 4),
                             'from': [], 'edges': [], 'goals': []}
        for belief, row in rows(f'?belief <{AM}votesFrom> ?cls .', 'cls'):
            found[belief]['from'].append(short(row['cls']))
        for belief, row in rows(f'?belief <{AM}neededFor> ?goal .', 'goal'):
            found[belief]['goals'].append(short(row['goal']))
        for belief, row in rows(f'?belief <{AM}edge> ?e . ?e <{AM}word> ?word ; <{AM}placeWord> ?pw ; <{AM}votes> ?v .',
                                'word', 'pw', 'v'):
            found[belief]['edges'].append([row['word'].value, row['pw'].value, value(row['v'])])
        for how in found.values():
            for key in ('from', 'edges', 'goals'):
                how[key].sort()
        return [found[belief] for belief in sorted(found)]

    @staticmethod
    def belief_node(belief):
        item, place, claim = belief
        return node(f'belief_{item}_{claim}_{place}')

    def count(self, cls, graph):
        """How many things of class am:<cls> the graph holds; numbers looks and decisions in the order they were made."""
        query = f'SELECT (COUNT(?x) AS ?n) WHERE {{ GRAPH <{graph.value}> {{ ?x a <{AM}{cls}> }} }}'
        return value(next(iter(self.knowledge.query(query)))['n'])

    @property
    def a(self):
        """{belief: A} for every belief in am:derived, belief = (item, place, claim)."""
        query = f'''SELECT ?item ?claim ?place ?a WHERE {{ GRAPH <{DERIVED.value}> {{
            ?belief <{RDF}reifies> <<( ?item ?claim ?place )>> ; <{AM}relevance> ?a }} }}'''
        return dict(sorted(((short(row['item']), short(row['place']), short(row['claim'])), value(row['a']))
                           for row in self.knowledge.query(query)))

    @property
    def goal_beliefs(self):
        """{goal: the beliefs it needs} for every prepared goal, from am:neededFor."""
        query = f'''SELECT ?goal ?item ?claim ?place WHERE {{ GRAPH <{DERIVED.value}> {{
            ?belief <{RDF}reifies> <<( ?item ?claim ?place )>> ; <{AM}neededFor> ?goal }} }}'''
        needs = {goal: set() for goal in self.prepared_goals}
        for row in self.knowledge.query(query):
            needs[short(row['goal'])].add((short(row['item']), short(row['place']), short(row['claim'])))
        return needs

    @property
    def b(self):
        """{(action type, target): B(o)}: B(o) = the beliefs of any goal the action observes."""
        beliefs = self.a
        return {(action_type, target): [b for b in beliefs if b[1] == target and b[2] == self.types[action_type][1]]
                for action_type, target in self.actions}

    def tell(self, turtle, t):
        """Store knowledge told at time t, as Turtle text, and derive again. Returns (added, removed, changed) beliefs.

        The telling is recorded in am:observations with the items it introduced. A telling hints that something changed
        for those items, so an empty look from before it no longer counts for them; a sighting from before it still
        says where the item was (last_observation).
        """
        query = f'SELECT ?item WHERE {{ ?item a <{AM}Item> }}'
        known = {short(row['item']) for row in self.knowledge.query(query)}
        self.knowledge.load(input=turtle.encode(), format=ox.RdfFormat.TURTLE)
        introduced = sorted({short(row['item']) for row in self.knowledge.query(query)} - known)
        telling = node(f'telling_{self.count("Telling", OBSERVATIONS) + 1}')
        quads = [(telling, ox.NamedNode(f'{RDF}type'), node('Telling')), (telling, node('t'), ox.Literal(t))]
        quads += [(telling, node('introduced'), node(item)) for item in introduced]
        self.knowledge.extend([ox.Quad(*quad, OBSERVATIONS) for quad in quads])
        self.observed = {}
        return self.derive()

    def set_goal(self, goal):
        """Make this goal the active one. Observations are kept: what was seen for one goal counts for the next."""
        if goal not in self.prepared_goals:
            raise ValueError(f'unknown goal {goal}')
        self.goal = goal

    def observe(self, action, values, t):
        """Store what an action reported at time t: {item: value of its claim} for the items it assessed at its target.
        One am:Look in am:observations, numbered in the order the looks were made.

        A report of the claim true where the last observation did not already say so is a find (am:find true): the item
        turned up there. A find is evidence for that belief, so the beliefs are derived again. A report that confirms
        what was already seen is not a find, so a place the robot checks often does not raise its own A.
        Returns (added, removed, changed) beliefs, all empty if nothing was found."""
        action_type, target = action
        classes, claim, duration, complete = self.types[action_type]
        found = {item for item, reported in values.items() if reported is True and self.seen((item, target, claim)) is not True}
        look = node(f'look_{self.count("Look", OBSERVATIONS) + 1}')
        quads = [(look, ox.NamedNode(f'{RDF}type'), node('Look')), (look, node('action'), node(action_type)),
                 (look, node('target'), node(target)), (look, node('claim'), ox.Literal(claim)),
                 (look, node('t'), ox.Literal(t)), (look, node('complete'), ox.Literal(complete))]
        for item, reported in values.items():
            report = ox.BlankNode()
            quads += [(look, node('reported'), report), (report, node('item'), node(item)),
                      (report, node('value'), ox.Literal(reported))]
            if item in found:
                quads.append((report, node('find'), ox.Literal(True)))
        self.knowledge.extend([ox.Quad(*quad, OBSERVATIONS) for quad in quads])
        self.observed = {}
        return self.derive() if found else ([], [], [])

    def last_observation(self, belief):
        """(t, value) of the last observation that assessed the belief's item at its place, or None if there was none.

        An item a complete action did not report has the claim false; an incomplete action says nothing about it. If the
        claim is an am:OnePlaceClaim (an item is present at one place at a time), a report of it true at another place
        also says it is false here, at that time. Such an absence no longer counts once a later telling introduced the
        item (tell).
        """
        if belief not in self.observed:
            self.observed[belief] = self.query_last_observation(belief)
        return self.observed[belief]

    def query_last_observation(self, belief):
        """last_observation, read from am:observations."""
        item, place, claim = belief
        not_told_since = f'''NOT EXISTS {{
            ?telling a <{AM}Telling> ; <{AM}introduced> <{AM}{item}> ; <{AM}t> ?told FILTER(?told > ?t) }}'''
        query = f'''SELECT ?t ?complete ?value WHERE {{ GRAPH <{OBSERVATIONS.value}> {{
            ?look a <{AM}Look> ; <{AM}target> <{AM}{place}> ; <{AM}claim> "{claim}" ; <{AM}t> ?t ;
                  <{AM}complete> ?complete .
            OPTIONAL {{ ?look <{AM}reported> ?report . ?report <{AM}item> <{AM}{item}> ; <{AM}value> ?value }}
            FILTER(BOUND(?value) || (?complete && {not_told_since})) }} }}
            ORDER BY DESC(?t) LIMIT 1'''
        here = None
        for row in self.knowledge.query(query):
            here = value(row['t']), value(row['value']) if row['value'] is not None else False
        if self.one_place:
            query = f'''SELECT ?t WHERE {{ GRAPH <{OBSERVATIONS.value}> {{
                ?look a <{AM}Look> ; <{AM}target> ?other ; <{AM}claim> "{claim}" ; <{AM}t> ?t ; <{AM}reported> ?report .
                ?report <{AM}item> <{AM}{item}> ; <{AM}value> true
                FILTER(?other != <{AM}{place}> && {not_told_since}) }} }}
                ORDER BY DESC(?t) LIMIT 1'''
            for row in self.knowledge.query(query):
                if here is None or value(row['t']) > here[0]:
                    return value(row['t']), False
        return here

    def location(self, item):
        """(place, t): where the item was last found present and when, if no later observation says it is gone; else None."""
        query = f'''SELECT ?place ?t WHERE {{ GRAPH <{OBSERVATIONS.value}> {{
            ?look a <{AM}Look> ; <{AM}target> ?place ; <{AM}claim> "{self.claim}" ; <{AM}t> ?t ; <{AM}reported> ?report .
            ?report <{AM}item> <{AM}{item}> ; <{AM}value> true }} }} ORDER BY DESC(?t) LIMIT 1'''
        for row in self.knowledge.query(query):
            place = short(row['place'])
            if self.seen((item, place, self.claim)):
                return place, value(row['t'])
        return None

    def answered(self, goal):
        """{item: (place, t)} if every item the goal needs has a location (location), else None. It says what the last
        observations say, so it can be out of date: t tells how old each one is. A goal that names no item is never
        answered."""
        where = {}
        for item in sorted(self.items(goal)):
            where[item] = self.location(item)
            if where[item] is None:
                return None
        return where or None

    def seen(self, belief):
        """What the last observation said about the belief: True, False, or None if never observed."""
        observation = self.last_observation(belief)
        return None if observation is None else observation[1]

    def unused_sightings(self):
        """[(t, item, place, claim, value)]: everything reported for which the awareness manager has no belief.
        Not used in v1."""
        query = f'''SELECT ?t ?place ?claim ?item ?value WHERE {{ GRAPH <{OBSERVATIONS.value}> {{
            ?look a <{AM}Look> ; <{AM}target> ?place ; <{AM}claim> ?claim ; <{AM}t> ?t ; <{AM}reported> ?report .
            ?report <{AM}item> ?item ; <{AM}value> ?value }} }}'''
        beliefs = self.a
        reported = [(value(row['t']), short(row['item']), short(row['place']), row['claim'].value, value(row['value']))
                    for row in self.knowledge.query(query)]
        return sorted(sighting for sighting in reported if sighting[1:4] not in beliefs)

    def e(self, belief, t):
        """Staleness, linear: 0 just after an observation, 1 after T seconds or if never observed."""
        observation = self.last_observation(belief)
        if observation is None:
            return 1.0
        return min(1.0, (t - observation[0]) / self.parameters['T'])

    def announce(self, goal, t):
        """Store that the goal will arrive at time t: one am:Announcement in am:observations. Arrivals are given, not
        predicted; an announced goal that is not known yet (no beliefs) has no weight until it is told."""
        announcement = node(f'announcement_{self.count("Announcement", OBSERVATIONS) + 1}')
        quads = [(announcement, ox.NamedNode(f'{RDF}type'), node('Announcement')), (announcement, node('goal'), node(goal)),
                 (announcement, node('arrival'), ox.Literal(t))]
        self.knowledge.extend([ox.Quad(*quad, OBSERVATIONS) for quad in quads])
        self.weights = {}

    def goal_weights(self, t):
        """{goal: weight} at time t: 1 for the active goal; for a known goal announced to arrive later, 2^(-dt / h), dt
        the time to its next arrival and h = horizon_halflife: a goal h seconds away counts half. Others weigh nothing."""
        if (t, self.goal) not in self.weights:
            query = f'''SELECT ?goal (MIN(?arrival) AS ?next) WHERE {{ GRAPH <{OBSERVATIONS.value}> {{
                ?announcement a <{AM}Announcement> ; <{AM}goal> ?goal ; <{AM}arrival> ?arrival FILTER(?arrival > {t}) }} }}
                GROUP BY ?goal'''
            weights = {short(row['goal']): 2 ** (-(value(row['next']) - t) / self.parameters['horizon_halflife'])
                       for row in self.knowledge.query(query)}
            weights = {goal: w for goal, w in weights.items() if goal in self.prepared_goals}
            if self.goal is not None:
                weights[self.goal] = 1.0
            self.weights = {(t, self.goal): dict(sorted(weights.items()))}
        return self.weights[(t, self.goal)]

    @staticmethod
    def belief_weight(goals, weights):
        """How much a belief counts: the summed weights of the goals that need it, since its observation serves each."""
        return sum(weights.get(goal, 0.0) for goal in goals)

    def terms(self, action, t):
        """[(item, E, A, weight)] for every belief the action observes that a weighted goal needs (goal_weights)."""
        action_type, target = action
        claim = self.types[action_type][1]
        weights = self.goal_weights(t)
        query = f'''SELECT ?item ?a ?goal WHERE {{ GRAPH <{DERIVED.value}> {{
            ?belief <{RDF}reifies> <<( ?item <{AM}{claim}> <{AM}{target}> )>> ; <{AM}relevance> ?a ;
                    <{AM}neededFor> ?goal }} }}'''
        needs = {}
        for row in self.knowledge.query(query):
            a, goals = needs.setdefault(short(row['item']), (value(row['a']), set()))
            goals.add(short(row['goal']))
        found = []
        for item, (a, goals) in sorted(needs.items()):
            weight = self.belief_weight(goals, weights)
            if weight > 0:
                found.append((item, self.e((item, target, claim), t), a, weight))
        return found

    def p(self, action, t):
        """Priority: sum of E x A x weight over B(o), the beliefs the action observes that a weighted goal needs (terms).
        With only the active goal weighted this is the sum of E x A over its beliefs. 0 if no goal has weight."""
        return sum(e * a * weight for item, e, a, weight in self.terms(action, t))

    def cost(self, action, position):
        """C in seconds: the transition to the target plus the action's duration. None if the target is unreachable."""
        action_type, target = action
        classes, claim, duration, complete = self.types[action_type]
        transition = self.transition_cost(position, target)
        return None if transition is None else transition + duration

    def decide(self, t, position):
        """The action to do now, or None to idle: among actions with P >= threshold, the highest U = P / C, ties by name.
        Idle while no goal has weight. The decision is written into am:decisions."""
        options = [(action, self.p(action, t), self.cost(action, position)) for action in self.actions]
        candidates = [(-p / c, action) for action, p, c in options
                      if p >= self.parameters['idle_threshold'] and c is not None]
        chosen = min(candidates)[1] if candidates else None
        self.record(t, position, options, chosen)
        return chosen

    def record(self, t, position, options, chosen):
        """Write a decision into am:decisions: the options with their P, C and U, the weight of every weighted goal, E of
        every belief such a goal needs, and the chosen action. A wait is written only when it starts, not again while it
        lasts."""
        count = self.count('Decision', DECISIONS)
        if chosen is None and count:
            last = f'{AM}decision_{count}'
            if not self.knowledge.query(f'ASK {{ GRAPH <{DECISIONS.value}> {{ <{last}> <{AM}chosenAction> ?a }} }}'):
                return
        decision = node(f'decision_{count + 1}')
        quads = [(decision, ox.NamedNode(f'{RDF}type'), node('Decision')), (decision, node('t'), ox.Literal(t)),
                 (decision, node('position'), node(position))]
        if self.goal is not None:
            quads.append((decision, node('goal'), node(self.goal)))
        if chosen is not None:
            quads += [(decision, node('chosenAction'), node(chosen[0])), (decision, node('chosenTarget'), node(chosen[1]))]
        for (action_type, target), p, c in options:
            option = ox.BlankNode()
            quads += [(decision, node('option'), option), (option, node('action'), node(action_type)),
                      (option, node('target'), node(target)), (option, node('priority'), ox.Literal(p))]
            if c is not None:
                quads += [(option, node('cost'), ox.Literal(c)), (option, node('utility'), ox.Literal(p / c))]
        weights = self.goal_weights(t)
        needs = self.goal_beliefs
        for goal, weight in weights.items():
            entry = ox.BlankNode()
            quads += [(decision, node('goalWeight'), entry), (entry, node('goal'), node(goal)),
                      (entry, node('value'), ox.Literal(weight))]
        for belief in sorted(set().union(*(needs[goal] for goal in weights))):
            staleness = ox.BlankNode()
            quads += [(decision, node('staleness'), staleness), (staleness, node('belief'), self.belief_node(belief)),
                      (staleness, node('value'), ox.Literal(self.e(belief, t)))]
        self.knowledge.extend([ox.Quad(*quad, DECISIONS) for quad in quads])
