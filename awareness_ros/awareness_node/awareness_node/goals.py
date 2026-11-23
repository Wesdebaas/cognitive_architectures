"""Goals: stores which goal is active and which are expected, and how much each goal counts now."""

from awareness_msgs.msg import ActiveGoal, ExpectedGoal

from .kb import AM, GOALS, short, stored, value


class Goals:

    def __init__(self, kb, knowledge, parameters):
        self.kb = kb
        self.knowledge = knowledge
        self.parameters = parameters
        self.expectations = 0
        self.activations = 0
        self.clear()

    def clear(self):
        """Forget what was calculated, after new knowledge or a new goal."""
        self.calculated = {}   # t -> weights

    def expect(self, goal, arrival):
        """Store that the goal will arrive at this time."""
        self.expectations += 1
        self.kb.write(ExpectedGoal(number=self.expectations, goal=goal, arrival=float(arrival)),
                      stored(f'expected_goal_{self.expectations}', GOALS))
        self.clear()

    def set_active(self, goal, t):
        """Store that the goal is active from time t; None for no active goal."""
        if goal is not None and goal not in self.knowledge.goals:
            raise ValueError(f'unknown goal {goal}')
        self.activations += 1
        self.kb.write(ActiveGoal(number=self.activations, t=float(t), goal=goal or ''),
                      stored(f'active_goal_{self.activations}', GOALS))
        self.clear()

    @property
    def active(self):
        """The active goal, or None."""
        query = f'''SELECT ?goal WHERE {{ GRAPH <{GOALS.value}> {{
            ?active a <{AM}ActiveGoal> ; <{AM}number> ?number OPTIONAL {{ ?active <{AM}goal> ?goal }} }} }}
            ORDER BY DESC(?number) LIMIT 1'''
        for row in self.kb.query(query):
            return short(row['goal']) if row['goal'] is not None else None
        return None

    def weights(self, t):
        """{goal: weight}: 1 for the active goal, 2^(-dt / h) for one expected dt seconds ahead."""
        if t not in self.calculated:
            query = f'''SELECT ?goal (MIN(?arrival) AS ?next) WHERE {{ GRAPH <{GOALS.value}> {{
                ?expected a <{AM}ExpectedGoal> ; <{AM}goal> ?goal ; <{AM}arrival> ?arrival FILTER(?arrival > {t}) }} }}
                GROUP BY ?goal'''
            weights = {short(row['goal']): 2 ** (-(value(row['next']) - t) / self.parameters['horizon_halflife'])
                       for row in self.kb.query(query)}
            weights = {goal: w for goal, w in weights.items() if goal in self.knowledge.goals}
            active = self.active
            if active is not None:
                weights[active] = 1.0
            self.calculated = {t: dict(sorted(weights.items()))}
        return self.calculated[t]
