"""Fill in a world's score sheet from the event logs of its runs. No ROS.

Each cell is PASS, FAIL or NA (the situation did not occur), then the seconds and the inspections from the start of the
row's window to that outcome. A cell marked ! differs from the prediction in the sheet. There is no total: the rows are
chosen, so a sum would mean nothing.

Run:  python3 score.py <score sheet> <events file> [<events file> ...]
python3 score.py ../scenarios/household/worlds/day/score_sheet.yaml runs/household_day.events.jsonl runs/household_day_round_robin.events.jsonl
"""

import json
import sys

import yaml


def load_events(file):
    with open(file) as f:
        return [json.loads(line) for line in f]


def looks(events, start, end):
    """The inspections that ended in [start, end]."""
    return [e for e in events if e['event'] == 'look' and start <= e['t'] <= end]


def outcome(passed, start, end, events, t=None):
    """(PASS or FAIL, seconds to it, inspections to it). Without a time the outcome holds for the whole window."""
    when = end if t is None else t
    return ('PASS' if passed else 'FAIL'), when - start, len(looks(events, start, when))


def seen(events, check):
    """Was the item seen at the place during the window?"""
    for e in looks(events, check['from'], check['to']):
        if check['item'] in e['seen'] and e['target'] == check['place']:
            return outcome(True, check['from'], check['to'], events, e['t'])
    return outcome(False, check['from'], check['to'], events)


def counted(events, check):
    """Was an item seen and counted for the active goal during the window?"""
    for e in looks(events, check['from'], check['to']):
        if set(check['items']) & set(e['counted']):
            return outcome(True, check['from'], check['to'], events, e['t'])
    return outcome(False, check['from'], check['to'], events)


def looked(events, check):
    """Was the place inspected during the window?"""
    for e in looks(events, check['from'], check['to']):
        if e['target'] == check['place']:
            return outcome(True, check['from'], check['to'], events, e['t'])
    return outcome(False, check['from'], check['to'], events)


def first_look(events, check):
    """Is the first inspection decided in the window, among these places (any place if none are given), the expected one?"""
    for e in looks(events, check['from'], check['to']):
        if e['started'] >= check['from'] and e['target'] in check.get('among', [e['target']]):
            return outcome(e['target'] == check['expect'], check['from'], check['to'], events, e['t'])
    return outcome(False, check['from'], check['to'], events)


def fewer_looks(events, check):
    """Was one place inspected less often than another during the window?"""
    window = looks(events, check['from'], check['to'])
    fewer = sum(e['target'] == check['fewer'] for e in window)
    than = sum(e['target'] == check['than'] for e in window)
    return outcome(fewer < than, check['from'], check['to'], events)


def known_at(events, check):
    """At the goal arrival or telling at time t, did the policy hold a positive observation of the item at the place?"""
    for e in events:
        if e['event'] in ('goal', 'told') and e['t'] == check['t']:
            if any(item == check['item'] and place == check['place'] for item, place, _ in e['held']):
                return 'PASS', 0, 0
    return 'FAIL', 0, 0


def answered(events, check):
    """Did the policy ever state that the goal is answered?"""
    return ('PASS' if any(e['event'] == 'answered' and e['goal'] == check['goal'] for e in events) else 'FAIL'), 0, 0


def all_of(events, check):
    """Do all these checks pass? Seconds and inspections are added up."""
    results = [evaluate(events, c) for c in check['checks']]
    passed = all(r[0] == 'PASS' for r in results)
    return ('PASS' if passed else 'FAIL'), sum(r[1] for r in results), sum(r[2] for r in results)


CHECKS = {'seen': seen, 'counted': counted, 'looked': looked, 'first_look': first_look, 'fewer_looks': fewer_looks,
          'known_at': known_at, 'answered': answered, 'all_of': all_of}


def evaluate(events, check):
    return CHECKS[check['type']](events, check)


def cell(events, policy, row):
    """The text of one cell: outcome, seconds, inspections, and ! if the outcome was not predicted."""
    if row['check']['type'] == 'not_run':
        return f"not run ({row['check']['reason']})"
    if 'applies_if' in row and evaluate(events, row['applies_if'])[0] != 'PASS':
        result, seconds, inspections = 'NA', None, None
    else:
        result, seconds, inspections = evaluate(events, row['check'])
    mark = '' if row['predicted'].get(policy) == result else ' !'
    effort = '' if seconds is None else f' {seconds:g} s, {inspections} looks'
    return f'{result}{mark}{effort}'


def effort_row(runs, label, value):
    return f"| {label} | " + ' | '.join(str(value(events)) for _, events in runs) + ' | |'


def seconds_busy(events):
    return sum(e['t'] - e['started'] for e in events if e['event'] == 'look')


def main(sheet_file, event_files):
    with open(sheet_file) as f:
        sheet = yaml.safe_load(f)
    runs = []
    for file in event_files:
        events = load_events(file)
        runs.append((events[0]['policy'], events))

    print('| # | ' + ' | '.join(policy for policy, _ in runs) + ' | Setup |')
    print('|---|' + '---|' * len(runs) + '---|')
    wrong = []
    for row in sheet['rows']:
        cells = [cell(events, policy, row) for policy, events in runs]
        print(f"| {row['id']} | " + ' | '.join(cells) + f" | {row['setup']} |")
        wrong += [f"{row['id']} {policy}: predicted {row['predicted'].get(policy)}, got {c.split()[0]}"
                  for (policy, _), c in zip(runs, cells) if ' !' in c]
    for row in sheet['not_attempted']:
        print(f"| {row['id']} | " + ' | '.join('not attempted' for _ in runs) + f" | {row['setup']} |")
    print(effort_row(runs, 'inspections', lambda events: len(looks(events, 0, float('inf')))))
    print(effort_row(runs, 'seconds busy', seconds_busy))
    print()
    print('Predictions that were wrong: ' + (', '.join(wrong) if wrong else 'none'))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
