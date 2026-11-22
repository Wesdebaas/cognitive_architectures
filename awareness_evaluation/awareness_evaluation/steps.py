"""A run replayed step by step from its events.jsonl: after each event, where the items really are and where the robot's
looks say they are. No ROS.

ros2 run awareness_evaluation steps <events file>
"""

import json
import sys


def read(file):
    """Every event of a run, in the order they happened."""
    with open(file) as f:
        return [json.loads(line) for line in f]


def steps(events):
    """[{t, happened, goal, needs, robot, chosen, really, says, seen}]: one step per start, goal, move, look, decision,
    night and end. needs: the items the goal needs. really: where each item is. says: where the robot's looks say it is.
    seen: where and when each item was last seen, (place, t). A look sees everything at its place: an item seen is there;
    an item the looks said was there but not seen no longer is, so the robot does not know where it is."""
    result = []
    goal, needs, robot, chosen, really, says, seen = None, [], None, None, {}, {}, {}
    for event in events:
        kind = event['event']
        if kind == 'start':
            robot, really = event['position'], dict(event['locations'])
            happened = f'starts at {robot}'
        elif kind == 'goal':
            if event['known']:
                goal, needs = event['goal'], event['needs']
            happened = f"goal: {event['goal']}" + ('' if event['known'] else ', unknown')
        elif kind == 'night':
            goal, needs = None, []
            happened = 'night'
        elif kind == 'move':
            if event['place']:
                really[event['item']] = event['place']
            else:
                really.pop(event['item'], None)
            happened = f"{event['item']} moves to {event['place'] or 'no place'}"
        elif kind == 'look':
            robot, chosen = event['target'], None
            says = {item: place for item, place in says.items() if place != robot}
            says.update({item: robot for item in event['seen']})
            seen.update({item: (robot, event['t']) for item in event['seen']})
            happened = f"looks at {robot}: {', '.join(event['seen']) or 'nothing'}"
        elif kind == 'decision':
            chosen = event['chosen_target'] or None
            happened = f"decides: {chosen or 'wait'}"
        elif kind == 'end':
            happened = 'end'
        else:
            continue
        result.append({'t': event['t'], 'happened': happened, 'goal': goal, 'needs': needs, 'robot': robot,
                       'chosen': chosen, 'really': dict(really), 'says': dict(says), 'seen': dict(seen)})
    return result


def main():
    for step in steps(read(sys.argv[1])):
        print(f"{step['t']:6d}  {step['goal'] or '':10s}  {step['happened']}")
