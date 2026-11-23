"""Decision: the action with the highest utility U = P / C, or a wait, recorded in the KB."""

from awareness_msgs.msg import Decision as DecisionMessage, GoalWeight, Option, Staleness


class Decision:

    def __init__(self, kb, knowledge, relevance, staleness, goals, priority, transition_cost, parameters):
        self.kb = kb
        self.knowledge = knowledge
        self.relevance = relevance
        self.staleness = staleness
        self.goals = goals
        self.priority = priority
        self.transition_cost = transition_cost   # (from, to) -> seconds, or None if unreachable
        self.parameters = parameters
        self.decisions = 0
        self.waiting = False   # the last decision recorded was a wait

    def cost(self, action, position):
        """C: seconds to get to the target plus the action's duration; None if unreachable."""
        action_type, target = action
        classes, claim, duration, complete = self.knowledge.types[action_type]
        transition = self.transition_cost(position, target)
        return None if transition is None else transition + duration

    def decide(self, t, position):
        """The reachable action with P >= idle_threshold and the highest U, ties by name; None to wait."""
        options = [(action, self.priority.p(action, t), self.cost(action, position)) for action in self.knowledge.actions]
        candidates = [(-p / c, action) for action, p, c in options
                      if p >= self.parameters['idle_threshold'] and c is not None]
        chosen = min(candidates)[1] if candidates else None
        self.record(t, position, options, chosen)
        return chosen

    def record(self, t, position, options, chosen):
        """A wait is recorded once, when it starts."""
        if chosen is None and self.waiting:
            return
        self.waiting = chosen is None
        self.decisions += 1
        weights, needs = self.goals.weights(t), self.relevance.goal_beliefs
        beliefs = sorted(set().union(*(needs[goal] for goal in weights)))
        self.kb.write(DecisionMessage(
            number=self.decisions, t=float(t), position=position, goal=self.goals.active or '',
            chosen_action=chosen[0] if chosen else '', chosen_target=chosen[1] if chosen else '',
            options=[Option(action=action_type, target=target, priority=float(p), reachable=c is not None,
                            cost=float(c) if c is not None else 0.0, utility=float(p / c) if c is not None else 0.0)
                     for (action_type, target), p, c in options],
            goal_weights=[GoalWeight(goal=goal, value=float(weight)) for goal, weight in weights.items()],
            stalenesses=[Staleness(item=item, claim=claim, target=target,
                                   value=float(self.staleness.e((item, target, claim), t)))
                         for item, target, claim in beliefs]))
