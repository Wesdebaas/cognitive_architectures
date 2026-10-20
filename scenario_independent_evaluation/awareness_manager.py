"""The awareness manager. Knows no scenario, ontology or commonsense source: a scenario's scenario.py
gives it everything it uses. No ROS.

  knowledge        one RDF store: goals, conditions, places, items, their words, action types, and an ontology
  association      word -> [(word, w)]: the things a source associates with a word, w = weight of evidence (adds up).
                   Each (item, thing) pair becomes a belief about the item at that thing.
  transition_cost  (from, to) -> seconds to get into position for an action at `to`, or None if impossible.
                   Travel time for a driving robot, turning time for a pan-tilt camera, 0 for a fixed sensor.
  parameters       {'T': {item: seconds until a belief about it is fully stale}, 'idle_threshold': P below which nothing is done, 'c': see support}

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

        A = 1 - e^(c*w), w = evidence summed over all edges from the item's word to the place's word.
        """
        query = f'''SELECT DISTINCT ?item ?word WHERE {{
            <{AM}{goal}> <{AM}requires> ?condition . ?condition <{AM}about> ?item .
            ?item a ?class . ?class <{AM}word> ?word }}'''
        items = [(row['word'].value, short(row['item'])) for row in self.knowledge.query(query)]

        query = f'SELECT ?place ?word WHERE {{ ?place a <{AM}Place> , ?class . ?class <{AM}word> ?word }}'
        places = [(row['word'].value, short(row['place'])) for row in self.knowledge.query(query)]

        weights = {}
        for item_word, item in items:
            for end, weight in self.association(item_word):
                for place_word, place in places:
                    if end == place_word:
                        belief = (item, place, 'present')
                        weights[belief] = weights.get(belief, 0.0) + weight
        return {belief: support(weight, self.parameters['c']) for belief, weight in sorted(weights.items())}

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
