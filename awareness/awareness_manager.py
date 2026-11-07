"""The awareness manager. Knows no scenario, ontology or commonsense source: a scenario's scenario.py
gives it everything it uses. No ROS.

  knowledge        one RDF store: goals, conditions, places, items, their words, action types, and an ontology,
                   in its default graph. The awareness manager writes into two named graphs of the same store
                   (see below), so whatever can read the store can read what it derived and observed.
  association      word -> [(word, w)]: the things a source associates with a word, w = weight of evidence (adds up).
                   Each (item, thing) pair becomes a belief about the item at that thing.
  claim            what such a belief claims about the item at the thing (for an AtLocation source: "present");
                   an action type observes the beliefs whose claim it declares.
  transition_cost  (from, to) -> seconds to get into position for an action at `to`, or None if impossible.
                   Travel time for a driving robot, turning time for a pan-tilt camera, 0 for a fixed sensor.
  parameters       {'T': {item: seconds until a belief about it is fully stale}, 'idle_threshold': P below which nothing is done, 'c': see support, 'alpha': see discount}

Every goal's beliefs are derived once (prepare). At run time it is told which goal is active (set_goal) and what
an action reported at its target (observe), and asked what to do next (decide). A goal switch keeps every observation.
Knowledge told during a run (tell) is stored, and nothing is derived from it.

Observations are stored apart from beliefs: what was seen is a fact about the world, a belief is a hypothesis. An action
reports a value of its claim for the items it assessed at its target. An action type declared complete assesses every
item there: an item it did not report has the claim false (looking in a cupboard: what is not seen is not there).

  am:derived       the beliefs, cleared and rebuilt by prepare. A belief names its claim with rdf:reifies (RDF 1.2),
                   which states the claim without asserting it, and carries its A (am:relevance) and the goals that
                   need it (am:neededFor):
                     am:belief_cup_1_present_cupboard_1 rdf:reifies <<( am:cup_1 am:present am:cupboard_1 )>> ;
                         am:relevance 0.26 ; am:neededFor am:breakfast , am:coffee .
  am:observations  one am:Look per observation, only ever added to:
                     am:look_7 a am:Look ; am:action am:inspect ; am:target am:table_1 ; am:claim "present" ;
                         am:t 263 ; am:complete true ; am:reported [ am:item am:cup_1 ; am:value true ] .
  am:decisions     one am:Decision per decision, only ever added to: what was weighed and what was chosen. A wait
                   has no am:chosenAction and is written once, when it starts:
                     am:decision_3 a am:Decision ; am:t 263 ; am:position am:dock ; am:goal am:breakfast ;
                         am:chosenAction am:inspect ; am:chosenTarget am:table_1 ;
                         am:option [ am:action am:inspect ; am:target am:table_1 ;
                                     am:priority 0.61 ; am:cost 25.0 ; am:utility 0.0244 ] ;
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

    def beliefs(self, goal):
        """{(item, place, claim): A} for every place the association source links to an item the goal needs.

        A = discount x (1 - e^(c*w)), w = the votes of the nearest class level that has any.
        """
        places = self.places()
        beliefs = {}
        for item, classes in self.items(goal).items():
            votes, source = self.nearest_evidence(classes, places)
            trust = self.discount(classes, source)
            for place, w in votes.items():
                beliefs[(item, place, self.claim)] = trust * support(w, self.parameters['c'])
        return dict(sorted(beliefs.items()))

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

    def evidence(self, words, places):
        """{place: w}: votes summed over every edge from these words to a place's word."""
        evidence = {}
        for word in words:
            for end, w in self.association(word):
                for place_word, place in places:
                    if end == place_word:
                        evidence[place] = evidence.get(place, 0.0) + w
        return evidence

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
        """Derive every goal's beliefs and every action once (static in v1). No goal is active and nothing is observed yet.

        A belief and its A do not depend on the goal, so one belief can belong to several goals (a shared item).
        """
        for graph in (DERIVED, OBSERVATIONS, DECISIONS):
            self.knowledge.clear_graph(graph)
        self.prepared_goals = self.goals()   # the goals whose beliefs were derived; set_goal accepts only these
        for goal in self.prepared_goals:
            for belief, a in self.beliefs(goal).items():
                self.store_belief(belief, a, goal)
        self.actions = list(self.observed_by({}))
        self.types = self.action_types()
        self.goal = None

    def store_belief(self, belief, a, goal):
        """Write a belief, its A and one goal that needs it into am:derived. Writing it again for another goal adds
        only that goal: a store holds each triple once."""
        item, place, claim = belief
        name = self.belief_node(belief)
        claimed = ox.Triple(node(item), node(claim), node(place))
        self.knowledge.extend([ox.Quad(name, ox.NamedNode(f'{RDF}reifies'), claimed, DERIVED),
                               ox.Quad(name, node('relevance'), ox.Literal(a), DERIVED),
                               ox.Quad(name, node('neededFor'), node(goal), DERIVED)])

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

    def tell(self, turtle):
        """Store knowledge told during a run, as Turtle text. Beliefs and actions stay as prepare derived them."""
        self.knowledge.load(input=turtle.encode(), format=ox.RdfFormat.TURTLE)

    def set_goal(self, goal):
        """Make this goal the active one. Observations are kept: what was seen for one goal counts for the next."""
        if goal not in self.prepared_goals:
            raise ValueError(f'unknown goal {goal}')
        self.goal = goal

    def observe(self, action, values, t):
        """Store what an action reported at time t: {item: value of its claim} for the items it assessed at its target.
        One am:Look in am:observations, numbered in the order the looks were made."""
        action_type, target = action
        classes, claim, duration, complete = self.types[action_type]
        look = node(f'look_{self.count("Look", OBSERVATIONS) + 1}')
        quads = [(look, ox.NamedNode(f'{RDF}type'), node('Look')), (look, node('action'), node(action_type)),
                 (look, node('target'), node(target)), (look, node('claim'), ox.Literal(claim)),
                 (look, node('t'), ox.Literal(t)), (look, node('complete'), ox.Literal(complete))]
        for item, reported in values.items():
            report = ox.BlankNode()
            quads += [(look, node('reported'), report), (report, node('item'), node(item)),
                      (report, node('value'), ox.Literal(reported))]
        self.knowledge.extend([ox.Quad(*quad, OBSERVATIONS) for quad in quads])

    def last_observation(self, belief):
        """(t, value) of the last observation that assessed the belief's item at its place, or None if there was none.

        An item a complete action did not report has the claim false; an incomplete action says nothing about it.
        """
        item, place, claim = belief
        query = f'''SELECT ?t ?complete ?value WHERE {{ GRAPH <{OBSERVATIONS.value}> {{
            ?look a <{AM}Look> ; <{AM}target> <{AM}{place}> ; <{AM}claim> "{claim}" ; <{AM}t> ?t ;
                  <{AM}complete> ?complete .
            OPTIONAL {{ ?look <{AM}reported> ?report . ?report <{AM}item> <{AM}{item}> ; <{AM}value> ?value }}
            FILTER(BOUND(?value) || ?complete) }} }}
            ORDER BY DESC(?t) LIMIT 1'''
        for row in self.knowledge.query(query):
            return value(row['t']), value(row['value']) if row['value'] is not None else False
        return None

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
        item = belief[0]
        return min(1.0, (t - observation[0]) / self.parameters['T'][item])

    def p(self, action, t):
        """Priority: sum of E x A over B(o), the active goal's beliefs the action observes. 0 if no goal is active."""
        if self.goal is None:
            return 0.0
        action_type, target = action
        claim = self.types[action_type][1]
        query = f'''SELECT ?item ?a WHERE {{ GRAPH <{DERIVED.value}> {{
            ?belief <{RDF}reifies> <<( ?item <{AM}{claim}> <{AM}{target}> )>> ; <{AM}relevance> ?a ;
                    <{AM}neededFor> <{AM}{self.goal}> }} }}'''
        terms = sorted((short(row['item']), value(row['a'])) for row in self.knowledge.query(query))
        return sum(self.e((item, target, claim), t) * a for item, a in terms)

    def cost(self, action, position):
        """C in seconds: the transition to the target plus the action's duration. None if the target is unreachable."""
        action_type, target = action
        classes, claim, duration, complete = self.types[action_type]
        transition = self.transition_cost(position, target)
        return None if transition is None else transition + duration

    def decide(self, t, position):
        """The action to do now, or None to idle: among actions with P >= threshold, the highest U = P / C, ties by name.
        Idle while no goal is active. The decision is written into am:decisions."""
        options = []   # (action, P, C)
        if self.goal is not None:
            options = [(action, self.p(action, t), self.cost(action, position)) for action in self.actions]
        candidates = [(-p / c, action) for action, p, c in options
                      if p >= self.parameters['idle_threshold'] and c is not None]
        chosen = min(candidates)[1] if candidates else None
        self.record(t, position, options, chosen)
        return chosen

    def record(self, t, position, options, chosen):
        """Write a decision into am:decisions: the options with their P, C and U, E of every belief the active goal
        needs, and the chosen action. A wait is written only when it starts, not again while it lasts."""
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
        for belief in sorted(self.goal_beliefs.get(self.goal, set())):
            staleness = ox.BlankNode()
            quads += [(decision, node('staleness'), staleness), (staleness, node('belief'), self.belief_node(belief)),
                      (staleness, node('value'), ox.Literal(self.e(belief, t)))]
        self.knowledge.extend([ox.Quad(*quad, DECISIONS) for quad in quads])
