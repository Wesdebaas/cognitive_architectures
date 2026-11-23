"""Priority P: how much an action's observation is worth now, for the goals that are active or expected."""

from .kb import AM, DERIVED, RDF, short, value


class Priority:

    def __init__(self, kb, knowledge, staleness, goals):
        self.kb = kb
        self.knowledge = knowledge
        self.staleness = staleness
        self.goals = goals
        self.clear()

    def clear(self):
        """Forget what was calculated, after new beliefs."""
        self.needs = {}   # (claim, target) -> the beliefs there, their A and goals

    @staticmethod
    def belief_weight(goals, weights):
        """The summed weights of the goals that need the belief: one observation serves each."""
        return sum(weights.get(goal, 0.0) for goal in goals)

    def terms(self, action, t):
        """[(item, E, A, weight)] for every belief the action observes that a weighted goal needs."""
        action_type, target = action
        claim = self.knowledge.types[action_type][1]
        weights = self.goals.weights(t)
        if (claim, target) not in self.needs:
            query = f'''SELECT ?item ?a ?goal WHERE {{ GRAPH <{DERIVED.value}> {{
                ?belief <{RDF}reifies> <<( ?item <{AM}{claim}> <{AM}{target}> )>> ; <{AM}relevance> ?a ;
                        <{AM}neededFor> ?goal }} }}'''
            needs = {}
            for row in self.kb.query(query):
                a, goals = needs.setdefault(short(row['item']), (value(row['a']), set()))
                goals.add(short(row['goal']))
            self.needs[(claim, target)] = sorted(needs.items())
        found = []
        for item, (a, goals) in self.needs[(claim, target)]:
            weight = self.belief_weight(goals, weights)
            if weight > 0:
                found.append((item, self.staleness.e((item, target, claim), t), a, weight))
        return found

    def p(self, action, t):
        """P = sum of E x A x weight over the terms."""
        return sum(e * a * weight for item, e, a, weight in self.terms(action, t))
