"""The awareness manager. Knows no scenario, ontology or commonsense source: a scenario's scenario.py
gives it everything it uses. No ROS.

  knowledge        one RDF store: goals, conditions, places, items, their words, action types, and an ontology
  association      word -> [(word, w)]: the things a source associates with a word, w = weight of evidence (adds up).
                   Each (item, thing) pair becomes a belief about the item at that thing.
  transition_cost  (from, to) -> seconds to get into position for an action at `to`, or None if impossible.
                   Travel time for a driving robot, turning time for a pan-tilt camera, 0 for a fixed sensor.
  parameters       {'T': {item: seconds until a belief about it is fully stale}, 'idle_threshold': P below which nothing is done, 'c': see support, 'alpha': see discount}

At run time it is told what was observed (observe) and asked what to do next (decide).
"""

import math

import pyoxigraph as ox

AM = 'http://example.org/awareness-manager#'
RDFS = 'http://www.w3.org/2000/01/rdf-schema#'


def short(term):
    if isinstance(term, ox.BlankNode):
        return '[anonymous]'
    return term.value.split('#')[-1]


def support(w, c):
    """Shafer's degree of support from weight of evidence w: 1 - e^(c*w), c < 0."""
    return 1 - math.exp(c * w)


class AwarenessManager:

    def __init__(self, knowledge, association, transition_cost, parameters):
        self.knowledge = knowledge
        self.association = association
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
                beliefs[(item, place, 'present')] = trust * support(w, self.parameters['c'])
        return dict(sorted(beliefs.items()))

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
        """{action type: (classes it applies to, claim it observes, duration in seconds)}, as declared."""
        query = f'''SELECT ?type ?class ?claim ?duration WHERE {{
            ?type a <{AM}ActionType> ; <{AM}appliesTo> ?class ; <{AM}observesClaim> ?claim ; <{AM}duration> ?duration }}'''
        types = {}
        for row in self.knowledge.query(query):
            classes, claim, duration = types.get(short(row['type']), (set(), row['claim'].value, float(row['duration'].value)))
            types[short(row['type'])] = (classes | {row['class'].value}, claim, duration)
        return types

    def instances(self, cls):
        """Every thing whose class is cls or below it."""
        query = f'SELECT DISTINCT ?thing WHERE {{ ?thing a/<{RDFS}subClassOf>* <{cls}> }}'
        return {short(row['thing']) for row in self.knowledge.query(query)}

    def actions(self, goal):
        """{(action type, target): B(o)}: one action per thing that is an instance of every class its type applies to.

        B(o) = the goal's beliefs whose place is the target and whose claim is the one the type observes.
        """
        beliefs = self.beliefs(goal)
        actions = {}
        for action_type, (classes, claim, duration) in sorted(self.action_types().items()):
            targets = set.intersection(*(self.instances(cls) for cls in classes))
            for target in sorted(targets):
                actions[(action_type, target)] = [b for b in beliefs if b[1] == target and b[2] == claim]
        return actions

    # ---- run time ----

    def set_goal(self, goal):
        """Derive the goal's beliefs and actions once (static in v1) and forget all observations."""
        self.a = self.beliefs(goal)
        self.b = self.actions(goal)
        self.durations = {action_type: duration for action_type, (classes, claim, duration) in self.action_types().items()}
        self.last_seen = {}   # belief -> time of its last observation
        self.values = {}      # belief -> what that observation said

    def observe(self, results, t):
        """Store what an action saw: {belief: True or False}, observed at time t."""
        for belief, value in results.items():
            self.last_seen[belief] = t
            self.values[belief] = value

    def observes(self, action):
        """B(o): the beliefs an action answers."""
        return self.b[action]

    def e(self, belief, t):
        """Staleness, linear: 0 just after an observation, 1 after T seconds or if never observed."""
        if belief not in self.last_seen:
            return 1.0
        item = belief[0]
        return min(1.0, (t - self.last_seen[belief]) / self.parameters['T'][item])

    def p(self, action, t):
        """Priority: sum of E x A over the beliefs the action observes."""
        return sum(self.e(belief, t) * self.a[belief] for belief in self.b[action])

    def cost(self, action, position):
        """C in seconds: the transition to the target plus the action's duration. None if the target is unreachable."""
        action_type, target = action
        transition = self.transition_cost(position, target)
        return None if transition is None else transition + self.durations[action_type]

    def decide(self, t, position):
        """The action to do now, or None to idle: among actions with P >= threshold, the highest U = P / C, ties by name."""
        candidates = []
        for action in self.b:
            p, c = self.p(action, t), self.cost(action, position)
            if p >= self.parameters['idle_threshold'] and c is not None:
                candidates.append((-p / c, action))
        return min(candidates)[1] if candidates else None
