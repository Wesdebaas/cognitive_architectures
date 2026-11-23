"""The result of a run: the share of item-seconds in which the robot's looks say where an item really is.

ros2 run awareness_evaluation score <events file> ...
"""

import sys

from .steps import read, steps

STATES = ['correct', 'wrong', 'unknown']


def state(step, item):
    """correct: the looks say where the item is; wrong: they say another place; unknown: they say nothing."""
    says = step['says'].get(item)
    return 'unknown' if says is None else 'correct' if says == step['really'].get(item) else 'wrong'


def seconds(run, needed_only):
    """{goal: {state: item-seconds}}. needed_only: the items the active goal needs, while a goal is active; otherwise
    every item, the whole run, under 'day'. A step lasts until the next one."""
    totals = {}
    for step, following in zip(run, run[1:]):
        if needed_only and step['goal'] is None:
            continue
        key, items = (step['goal'], step['needs']) if needed_only else ('day', step['really'].keys() | step['says'].keys())
        counts = totals.setdefault(key, dict.fromkeys(STATES, 0))
        for item in items:
            counts[state(step, item)] += following['t'] - step['t']
    return totals


def percent(counts, which='correct'):
    return f'{100 * counts[which] / sum(counts.values()):.1f}%'


def main():
    rows = []
    for file in sys.argv[1:]:
        events = read(file)
        run = steps(events)
        needed = seconds(run, needed_only=True)
        day = {which: sum(counts[which] for counts in needed.values()) for which in STATES}
        rows.append([events[0]['policy']] + [percent(counts) for counts in needed.values()]
                    + [percent(day, which) for which in STATES] + [percent(seconds(run, needed_only=False)['day'])])
    print('needed items: per goal, then the day correct / wrong / unknown; all items: the day correct')
    header = ['policy'] + list(needed) + STATES + ['all items']
    for cells in [header] + rows:
        print(''.join(f'{cell:>12s}' for cell in cells))
