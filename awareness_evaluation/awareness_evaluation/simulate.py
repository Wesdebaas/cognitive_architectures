"""The awareness manager run through a scenario without ROS nodes: one program, one second at a time, on LocalKB.
Writes a plain text log, one line per event.

ros2 run awareness_evaluation simulate <scenario's day folder> <log file>
"""

import sys
from pathlib import Path

import yaml
from awareness_node.build import awareness_manager
from awareness_node.local_kb import LocalKB
from awareness_scenario.timeline import ASSERTION, GOAL, NIGHT, World, settings, timetable


def run(folder, log):
    folder = Path(folder)
    with open(folder.parent / 'robot.yaml') as f:
        robot = yaml.safe_load(f)['/**']['ros__parameters']
    am = awareness_manager(LocalKB(), folder.parent / 'places.csv', robot['speed'])
    world = World(folder)
    arrivals, entries = timetable(folder)
    position, action, ends, waiting = robot['start_position'], None, None, False

    def write(t, kind, text):
        log.write(f'{t:6d}  {kind:8s}  {text}\n')

    am.start()
    for name in settings(folder)['knowledge']:
        am.assert_knowledge((folder.parent / name).read_text(), 0)
    for arrival, goal in arrivals:
        am.announce(goal, arrival)
    write(0, 'start', f'at {position}')

    for t in range(int(entries[-1][0]) + 1):
        while entries and entries[0][0] <= t:
            _, kind, value = entries.pop(0)
            if kind == NIGHT:
                am.set_goal(None)
                write(t, 'night', '')
            elif kind == ASSERTION:
                am.assert_knowledge((folder / value).read_text(), t)
                write(t, 'assert', value)
            elif kind == GOAL:
                try:
                    am.set_goal(value)
                    write(t, 'goal', value)
                except ValueError:
                    write(t, 'goal', f'{value} is unknown; the previous goal stays')

        for item, place in world.advance(t):
            write(t, 'move', f'{item} -> {place or "no place"}')

        if action is not None and t >= ends:
            seen = world.inspect(action[1])
            am.observe(action, {item: True for item in seen}, t)
            write(t, 'observe', f'{action[0]} {action[1]}: {", ".join(seen) or "nothing"}')
            position, action = action[1], None

        if action is None:
            action = am.decide(t, position)
            if action is not None:
                ends = t + am.decision.cost(action, position)
                write(t, 'decide', f'{action[0]} {action[1]}')
            elif not waiting:
                write(t, 'decide', 'wait')
            waiting = action is None


def main():
    with open(sys.argv[2], 'w') as log:
        run(sys.argv[1], log)
