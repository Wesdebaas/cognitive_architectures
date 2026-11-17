"""The awareness manager: decides what the robot should observe next."""

from .decision import Decision
from .knowledge import Knowledge
from .observations import Observations
from .priority import Priority
from .relevance import Relevance
from .staleness import Staleness


class AwarenessManager:

    def __init__(self, kb, association, claim, transition_cost, parameters):
        self.parameters = parameters
        self.knowledge = Knowledge(kb, claim)
        self.relevance = Relevance(kb, self.knowledge, association, parameters)
        self.observations = Observations(kb, self.knowledge)
        self.staleness = Staleness(self.knowledge, self.observations, parameters)
        self.priority = Priority(kb, self.knowledge, self.staleness, parameters)
        self.decision = Decision(kb, self.knowledge, self.relevance, self.staleness, self.priority, transition_cost,
                                 parameters)

    def start(self):
        self.update_beliefs()
        self.priority.goal = None

    def update_beliefs(self):
        """Returns (added, removed, changed) beliefs."""
        self.knowledge.reload()
        changes = self.relevance.update()
        self.priority.clear()
        return changes

    def assert_knowledge(self, turtle, t):
        self.observations.assert_knowledge(turtle, t)
        return self.update_beliefs()

    def announce(self, goal, t):
        self.observations.announce(goal, t)
        self.priority.clear()

    def set_goal(self, goal):
        """None for no active goal. What was observed for one goal counts for the next."""
        if goal is not None and goal not in self.knowledge.goals:
            raise ValueError(f'unknown goal {goal}')
        self.priority.goal = goal

    def observe(self, action, values, t):
        """A find is evidence for its belief, so the beliefs are updated."""
        found = self.observations.observe(action, values, t)
        return self.update_beliefs() if found else ([], [], [])

    def decide(self, t, position):
        """The action to do now, or None to wait."""
        return self.decision.decide(t, position)
