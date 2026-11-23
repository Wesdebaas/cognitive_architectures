"""Round robin, the baseline the AM is compared with: it looks at the place it looked at longest ago. No goals, no
relevance; distance only breaks ties."""


class RoundRobin:

    def __init__(self, am, record, every_place=False):
        """am: the AM after its knowledge is asserted; only its places and its cost are used. every_place: all places;
        otherwise only those the AM has a belief about, the places an item can be."""
        linked = {target for _, target, _ in am.relevance.a}
        self.actions = [action for action in am.knowledge.actions if every_place or action[1] in linked]
        self.cost = am.decision.cost
        self.record = record
        self.looked = {}   # action -> t of its last look

    def decide(self, t, position):
        """Never looked at first, then the longest ago; ties: the nearest, then by name. Never waits."""
        chosen = min(self.actions, key=lambda action: (self.looked.get(action, -1), self.cost(action, position), action))
        self.record('decision', t, chosen_action=chosen[0], chosen_target=chosen[1], options=[], goal_weights=[],
                    stalenesses=[])
        return chosen

    def observe(self, action, values, t):
        self.looked[action] = t
