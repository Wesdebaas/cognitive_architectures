"""The awareness manager. Knows no scenario, ontology or commonsense source: a scenario's scenario.py
gives it everything it uses. No ROS.

  knowledge        one RDF store: goals, conditions, places, items, their words, action types, and an ontology
  association      word -> [(word, w)]: the things a source associates with a word, w = weight of evidence (adds up).
                   Each (item, thing) pair becomes a belief about the item at that thing.
  claim            what such a belief claims about the item at the thing (for an AtLocation source: "present");
                   an action type observes the beliefs whose claim it declares.
  transition_cost  (from, to) -> seconds to get into position for an action at `to`, or None if impossible.
                   Travel time for a driving robot, turning time for a pan-tilt camera, 0 for a fixed sensor.
  parameters       {'T': {item: seconds until a belief about it is fully stale}, 'idle_threshold': P below which nothing is done, 'c': see support, 'alpha': see discount}

Every goal's beliefs are derived once (prepare). At run time it is told which goal is active (set_goal) and what
an action reported at its target (observe), and asked what to do next (decide). A goal switch keeps every observation.

Observations are stored apart from beliefs: what was seen is a fact about the world, a belief is a hypothesis. An action
reports a value of its claim for the items it assessed at its target. An action type declared complete assesses every
item there: an item it did not report has the claim false (looking in a cupboard: what is not seen is not there).
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
        self.a, self.goal_beliefs = {}, {}
        for goal in self.goals():
            beliefs = self.beliefs(goal)
            self.a.update(beliefs)
            self.goal_beliefs[goal] = set(beliefs)
        self.b = self.observed_by(self.a)   # every belief at the target, of any goal
        self.types = self.action_types()
        self.goal = None
        self.snapshots = {}   # (place, claim) -> [(t, {item: value}, complete)], oldest first

    def set_goal(self, goal):
        """Make this goal the active one. Observations are kept: what was seen for one goal counts for the next."""
        if goal not in self.goal_beliefs:
            raise ValueError(f'unknown goal {goal}')
        self.goal = goal

    def observe(self, action, values, t):
        """Store what an action reported at time t: {item: value of its claim} for the items it assessed at its target."""
        action_type, target = action
        classes, claim, duration, complete = self.types[action_type]
        self.snapshots.setdefault((target, claim), []).append((t, dict(values), complete))

    def last_observation(self, belief):
        """(t, value) of the last observation that assessed the belief's item at its place, or None if there was none.

        An item a complete action did not report has the claim false; an incomplete action says nothing about it.
        """
        item, place, claim = belief
        for t, values, complete in reversed(self.snapshots.get((place, claim), [])):
            if item in values:
                return t, values[item]
            if complete:
                return t, False
        return None

    def seen(self, belief):
        """What the last observation said about the belief: True, False, or None if never observed."""
        observation = self.last_observation(belief)
        return None if observation is None else observation[1]

    def unused_sightings(self):
        """[(t, item, place, claim, value)]: everything reported for which the awareness manager has no belief.
        Not used in v1."""
        return sorted((t, item, place, claim, value)
                      for (place, claim), history in self.snapshots.items()
                      for t, values, complete in history
                      for item, value in values.items() if (item, place, claim) not in self.a)

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
        active = self.goal_beliefs[self.goal]
        return sum(self.e(belief, t) * self.a[belief] for belief in self.b[action] if belief in active)

    def cost(self, action, position):
        """C in seconds: the transition to the target plus the action's duration. None if the target is unreachable."""
        action_type, target = action
        classes, claim, duration, complete = self.types[action_type]
        transition = self.transition_cost(position, target)
        return None if transition is None else transition + duration

    def decide(self, t, position):
        """The action to do now, or None to idle: among actions with P >= threshold, the highest U = P / C, ties by name.
        Idle while no goal is active."""
        if self.goal is None:
            return None
        candidates = []
        for action in self.b:
            p, c = self.p(action, t), self.cost(action, position)
            if p >= self.parameters['idle_threshold'] and c is not None:
                candidates.append((-p / c, action))
        return min(candidates)[1] if candidates else None
