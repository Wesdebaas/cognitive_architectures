"""Staleness E: how likely a belief's last observation no longer holds."""

import math


class Staleness:

    def __init__(self, knowledge, observations, parameters):
        self.knowledge = knowledge
        self.observations = observations
        self.parameters = parameters

    def persistence(self, item):
        """Seconds the item stays where it is: its am:persistence, else T."""
        return self.knowledge.persistences.get(item, self.parameters['T'])

    def e(self, belief, t):
        """E = 1 - e^(-dt / mu) (Toris and Chernova 2017, Eq. 2); 1 if never observed."""
        observation = self.observations.last_observation(belief)
        if observation is None:
            return 1.0
        return 1 - math.exp(-(t - observation[0]) / self.persistence(belief[0]))
