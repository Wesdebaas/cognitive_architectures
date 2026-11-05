"""Policies to compare the awareness manager with. They use no beliefs and keep no observations. No ROS."""


class RoundRobin:
    """Inspects every target in name order, over and over, whatever the goal. Told targets join the round."""

    def __init__(self, am):
        self.am = am
        self.last = None

    def decide(self, t, position):
        """The next reachable action after the last one chosen, in name order. None if nothing is reachable."""
        actions = sorted(a for a in self.am.observed_by({}) if self.am.cost(a, position) is not None)
        if not actions:
            return None
        later = [a for a in actions if self.last is None or a > self.last]
        self.last = later[0] if later else actions[0]
        return self.last
