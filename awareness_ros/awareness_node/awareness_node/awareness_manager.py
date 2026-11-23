"""The awareness manager: decides what the robot should observe next."""

from .decision import Decision
from .goals import Goals
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
        self.goals = Goals(kb, self.knowledge, parameters)
        self.priority = Priority(kb, self.knowledge, self.staleness, self.goals)
        self.decision = Decision(kb, self.knowledge, self.relevance, self.staleness, self.goals, self.priority,
                                 transition_cost, parameters)

    def start(self):
        self.update_beliefs()

    def update_beliefs(self):
        """Returns (added, removed, changed) beliefs."""
        self.knowledge.reload()
        changes = self.relevance.update()
        self.goals.clear()
        self.priority.clear()
        return changes

    def assert_knowledge(self, turtle, t):
        """Earlier empty observations no longer count for the items it introduces; earlier sightings still do."""
        introduced = self.knowledge.assert_knowledge(turtle, t)
        self.observations.forget(items=introduced)
        return self.update_beliefs()

    def expect_goal(self, goal, arrival):
        self.goals.expect(goal, arrival)

    def set_active_goal(self, goal, t):
        self.goals.set_active(goal, t)

    def observe(self, action, values, t):
        """A find is evidence for its belief, so the beliefs are updated."""
        found = self.observations.observe(action, values, t)
        return self.update_beliefs() if found else ([], [], [])

    def decide(self, t, position):
        """The action to do now, or None to wait."""
        return self.decision.decide(t, position)
