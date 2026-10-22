"""Carries out an action in the testbed's world and reports what it saw. No ROS.

The only code that reads the world files. The awareness manager never imports this: a real robot can replace it.
The world starts as the world file says; the events file (optional) moves items during a run.

Run:  python3 executor.py <world file> <action type> <target> <item> ...     (the world at t = 0)
python3 executor.py ../scenarios/breakfast/world.ttl inspect table_1 breakfast_plate_1 cup_1
"""

import csv
import sys
from pathlib import Path

import pyoxigraph as ox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from awareness_manager import AM


class Executor:

    def __init__(self, world_file, events_file=None):
        self.world = ox.Store()
        self.world.load(path=str(world_file), format=ox.RdfFormat.TURTLE)
        self.events = []   # (t, item, place) not yet applied, in time order; place '' = at no place
        if events_file is not None:
            with open(events_file) as f:
                self.events = sorted((float(row['t']), row['item'], row['place']) for row in csv.DictReader(f))

    def advance(self, t):
        """Apply every event due at or before time t: the item leaves its place and goes to the event's place.

        Returns the applied events.
        """
        applied = []
        while self.events and self.events[0][0] <= t:
            event = self.events.pop(0)
            _, item, place = event
            self.world.update(f'DELETE WHERE {{ <{AM}{item}> <{AM}isAt> ?place }}')
            if place:
                self.world.update(f'INSERT DATA {{ <{AM}{item}> <{AM}isAt> <{AM}{place}> }}')
            applied.append(event)
        return applied

    def location(self, item):
        """Where the item really is, '' if at no place. For the run log only, never for the awareness manager."""
        places = [row['place'].value.split('#')[-1]
                  for row in self.world.query(f'SELECT ?place WHERE {{ <{AM}{item}> <{AM}isAt> ?place }}')]
        return ' '.join(sorted(places))

    def execute(self, action_type, target, beliefs):
        """{belief: True or False} for every belief the action observes."""
        if action_type == 'inspect':
            return {belief: self.inspect(target, belief) for belief in beliefs}
        raise ValueError(f'the executor cannot do {action_type}')

    def inspect(self, target, belief):
        """Look inside the target: is the belief's item there? Perfect perception."""
        item, place, claim = belief
        if claim != 'present':
            raise ValueError(f'inspect cannot observe {claim}')
        return bool(self.world.query(f'ASK {{ <{AM}{item}> <{AM}isAt> <{AM}{target}> }}'))


if __name__ == '__main__':
    world_file, action_type, target, items = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
    beliefs = [(item, target, 'present') for item in items]
    for belief, seen in Executor(world_file).execute(action_type, target, beliefs).items():
        print(*belief, 'yes' if seen else 'no')
