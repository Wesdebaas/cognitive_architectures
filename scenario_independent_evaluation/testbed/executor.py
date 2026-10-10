"""Carries out an action in the testbed's world and reports what it saw. No ROS.

The only code that reads the world file. The awareness manager never imports this: a real robot can replace it.

Run:  python3 executor.py <world file> <action type> <target> <item> ...
python3 executor.py ../scenarios/drinks/world.ttl inspect refrigerator_1 juice wine
"""

import sys
from pathlib import Path

import pyoxigraph as ox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from awareness_manager import AM


class Executor:

    def __init__(self, world_file):
        self.world = ox.Store()
        self.world.load(path=str(world_file), format=ox.RdfFormat.TURTLE)

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
        return self.world.query(f'ASK {{ <{AM}{item}> <{AM}isAt> <{AM}{target}> }}')


if __name__ == '__main__':
    world_file, action_type, target, items = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
    beliefs = [(item, target, 'present') for item in items]
    for belief, seen in Executor(world_file).execute(action_type, target, beliefs).items():
        print(*belief, 'yes' if seen else 'no')
