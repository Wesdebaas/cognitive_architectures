"""The awareness manager, or the round robin baseline, run through a scenario without ROS nodes: one program, one
second at a time, on LocalKB. Writes events.jsonl, one JSON object per line: what the world did (start, goal, move, look,
night, end) and every message the AM wrote to its KB (decision, observation, beliefs, assertion, expectedgoal,
activegoal); round robin writes its own decisions.

ros2 run awareness_evaluation simulate <scenario's day folder> <events file> [policy]
policy: awareness_manager (the default), awareness_manager_no_anticipation, round_robin_item_places or
round_robin_all_places
"""

import json
import sys
from pathlib import Path

import yaml
from awareness_node.build import awareness_manager
from awareness_node.local_kb import LocalKB
from awareness_scenario.timeline import ASSERTION, GOAL, NIGHT, World, settings, timetable
from rosidl_runtime_py.convert import message_to_ordereddict

from .round_robin import RoundRobin

# The AM, the AM that is not told which goals to expect, and round robin over the places an item can be or over every
# place.
POLICIES = ['awareness_manager', 'awareness_manager_no_anticipation', 'round_robin_item_places', 'round_robin_all_places']


class RecordingKB(LocalKB):
    """LocalKB that also records every message the AM writes, as an event at the current time."""

    def __init__(self, record):
        super().__init__()
        self.record = record
        self.t = 0

    def write(self, msg, check=None):
        super().write(msg, check)
        fields = message_to_ordereddict(msg)
        fields.pop('t', None)   # the message's own time, the same second as the event's
        self.record(type(msg).__name__.lower(), self.t, **fields)


def run(folder, events, policy='awareness_manager'):
    folder = Path(folder)
    with open(folder.parent / 'robot.yaml') as f:
        robot = yaml.safe_load(f)['/**']['ros__parameters']

    def record(kind, t, **fields):
        events.write(json.dumps({'event': kind, 't': t, **fields}) + '\n')

    kb = RecordingKB(record)
    am = awareness_manager(kb, folder.parent / 'places.csv', robot['speed'])
    world = World(folder)
    arrivals, entries = timetable(folder)
    run = settings(folder)
    position, action, started, ends = robot['start_position'], None, None, None

    record('start', 0, position=position, locations=dict(sorted(world.where.items())),
           threshold=am.decision.parameters['idle_threshold'], policy=policy)
    am.start()
    for name in run['knowledge']:
        am.assert_knowledge((folder.parent / name).read_text(), 0)
    chooser = RoundRobin(am, record, every_place=policy == 'round_robin_all_places') \
        if policy.startswith('round_robin') else am
    if policy == 'awareness_manager':
        for arrival, goal in arrivals:
            am.expect_goal(goal, arrival)

    for t in range(int(entries[-1][0]) + 1):
        kb.t = t
        while entries and entries[0][0] <= t:
            _, kind, value = entries.pop(0)
            if kind == NIGHT:
                am.set_active_goal(None, t)
                record('night', t)
            elif kind == ASSERTION:
                am.assert_knowledge((folder / value).read_text(), t)
            elif kind == GOAL:
                try:
                    am.set_active_goal(value, t)
                    record('goal', t, goal=value, known=True, needs=sorted(am.knowledge.items(value)))
                except ValueError:
                    record('goal', t, goal=value, known=False)

        for item, place in world.advance(t):
            record('move', t, item=item, place=place)

        if action is not None and t >= ends:
            seen = world.inspect(action[1])
            record('look', t, started=started, action=action[0], target=action[1], seen=seen)
            chooser.observe(action, {item: True for item in seen}, t)
            position, action = action[1], None

        if action is None:
            action = chooser.decide(t, position)
            if action is not None:
                started, ends = t, t + am.decision.cost(action, position)

    record('end', t)


def main():
    policy = sys.argv[3] if len(sys.argv) > 3 else 'awareness_manager'
    if policy not in POLICIES:
        sys.exit(f'policy must be one of {POLICIES}')
    with open(sys.argv[2], 'w') as events:
        run(sys.argv[1], events, policy)
