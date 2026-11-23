"""The result of a run: the share of item-seconds in which the robot's looks say where an item really is.

ros2 run awareness_evaluation score <condition, folder or events file> ...
A condition (e.g. votes_960_2) or folder scores every policy's run in it.
"""

import sys

from .paths import condition
from .simulate import POLICIES
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


def result(events):
    """{goal: share correct, ..., 'correct' / 'wrong' / 'unknown': the day's shares, 'all items': share correct}, in
    percent, of the needed items while a goal is active and of all items over the whole run."""
    run = steps(events)
    needed = seconds(run, needed_only=True)
    day = {which: sum(counts[which] for counts in needed.values()) for which in STATES}
    share = {goal: percent(counts) for goal, counts in needed.items()}
    share.update({which: percent(day, which) for which in STATES})
    share['all items'] = percent(seconds(run, needed_only=False)['day'])
    return share


def percent(counts, which='correct'):
    return 100 * counts[which] / sum(counts.values())


def table(files):
    rows = []
    for file in files:
        events = read(file)
        rows.append((events[0]['policy'], result(events)))
    columns = list(rows[0][1])
    print(f'{"policy":>25s}' + ''.join(f'{cell:>12s}' for cell in columns))
    for policy, share in rows:
        print(f'{policy:>25s}' + ''.join(f'{share[column]:11.1f}%' for column in columns))


def main():
    """One table per condition or folder; events files next to each other share one."""
    tables = []
    for name in sys.argv[1:]:
        path = condition(name)
        if path.is_dir():
            tables.append((path.name, [path / f'{policy}.events.jsonl' for policy in POLICIES]))
        elif tables and tables[-1][0] is None:
            tables[-1][1].append(path)
        else:
            tables.append((None, [path]))
    print('needed items: per goal, then the day correct / wrong / unknown; all items: the day correct')
    for title, files in tables:
        print(f'\n{title}' if title else '')
        table(files)
