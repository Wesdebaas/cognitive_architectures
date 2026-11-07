"""Carries out an action in the testbed's world and reports what it saw. No ROS.

The only code that reads the world files. The awareness manager never imports this: a real robot can replace it.
The world starts as the world file says; the events file (optional) moves items during a run.

Run:  python3 executor.py <world file> <action type> <target>     (the world at t = 0)
python3 executor.py ../scenarios/breakfast/worlds/d14/world.ttl inspect table_1
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

    def locations(self):
        """{item: place} for every item at a place. For the run log only, never for the awareness manager."""
        rows = self.world.query(f'SELECT ?item ?place WHERE {{ ?item <{AM}isAt> ?place }}')
        return {row['item'].value.split('#')[-1]: row['place'].value.split('#')[-1] for row in rows}

    def classes(self, items):
        """{item: its class} for the items the world file gives a class. Perfect classification: never wrong."""
        found = {}
        for item in items:
            for row in self.world.query(f'SELECT ?class WHERE {{ <{AM}{item}> a ?class }}'):
                found[item] = row['class'].value.split('#')[-1]
        return found

    def execute(self, action_type, target):
        """{item: value of the action's claim} for the items the action assessed at the target."""
        if action_type == 'inspect':
            return self.inspect(target)
        raise ValueError(f'the executor cannot do {action_type}')

    def inspect(self, target):
        """Look at the target: {item: True} for every item that is there. Perfect perception: nothing missed,
        nothing invented; the action type is declared complete, so an item not reported is not there."""
        rows = self.world.query(f'SELECT ?item WHERE {{ ?item <{AM}isAt> <{AM}{target}> }}')
        return {row['item'].value.split('#')[-1]: True for row in rows}


if __name__ == '__main__':
    world_file, action_type, target = sys.argv[1], sys.argv[2], sys.argv[3]
    for item, value in sorted(Executor(world_file).execute(action_type, target).items()):
        print(item, value)
