"""Run the awareness manager in one world of a scenario on a 1-second clock, printing every decision. No ROS.

A world is a folder with three files: world.ttl (where every item is at t = 0), world_events.csv (t,item,place:
from time t on, the item is at the place) and goal_events.csv (t,goal: from time t on, this goal is active).
Only the testbed reads them; the awareness manager learns of a goal when it arrives and of the world by observing.

Each tick: first a goal arrives if one is due, then the world changes if an event is due; then, if the running
action has ended, the executor reports what it saw (the world at the end of the action) and the awareness manager
stores it; then, if the robot is free, the awareness manager decides. Actions are never interrupted.
After that, the active goal, what was reported without a belief, where each item really is, E of every belief and
P, C, U of every action are logged: runs/<scenario>_<world>.csv, one row per tick.

Run:  python3 run.py <scenario folder> <world folder>
python3 run.py ../scenarios/breakfast ../scenarios/breakfast/worlds/d14
"""

import csv
import sys
from pathlib import Path

from executor import Executor
from load import load_scenario


def goal_events(file):
    """[(t, goal)] in time order."""
    with open(file) as f:
        return sorted((float(row['t']), row['goal']) for row in csv.DictReader(f))


def log_items(am):
    """The items any goal has beliefs about."""
    return sorted({item for item, place, claim in am.a})


def log_header(am):
    beliefs, actions = sorted(am.a), sorted(am.b)
    return (['t', 'position', 'running', 'goal', 'unused']
            + [f'at {item}' for item in log_items(am)]
            + [f'E {item}@{place}' for item, place, claim in beliefs]
            + [f'{value} {action_type} {target}' for value in 'PCU' for action_type, target in actions])


def log_row(am, executor, t, position, action):
    """The active goal, what was reported at time t without a belief, where each item really is, then the values
    the awareness manager sees at time t. C and U are empty for an unreachable target."""
    beliefs, actions = sorted(am.a), sorted(am.b)
    p = {o: am.p(o, t) for o in actions}
    c = {o: am.cost(o, position) for o in actions}
    unused = [f'{item}@{place} {claim}={value}' for s, item, place, claim, value in am.unused_sightings() if s == t]
    return ([t, position, ' '.join(action) if action else '', am.goal or '', ' '.join(unused)]
            + [executor.location(item) for item in log_items(am)]
            + [round(am.e(belief, t), 4) for belief in beliefs]
            + [round(p[o], 4) for o in actions]
            + ['' if c[o] is None else c[o] for o in actions]
            + ['' if c[o] is None else round(p[o] / c[o], 4) for o in actions])


def run(scenario, world, log_file):
    am = scenario.awareness_manager()
    am.prepare()
    executor = Executor(world / 'world.ttl', world / 'world_events.csv')
    goals = goal_events(world / 'goal_events.csv')
    settings = scenario.testbed()

    position = settings['start_position']
    action, ends, idle = None, None, False
    log_file.parent.mkdir(exist_ok=True)
    log = open(log_file, 'w', newline='')
    writer = csv.writer(log)
    writer.writerow(log_header(am))
    for t in range(settings['run_length'] + 1):
        while goals and goals[0][0] <= t:
            am.set_goal(goals.pop(0)[1])
            print(f'{t:>4}  goal: {am.goal}')

        for _, item, place in executor.advance(t):
            print(f'{t:>4}  world: {item} -> {place or "no place"}')

        if action is not None and t >= ends:
            am.observe(action, executor.execute(*action), t)
            for _, item, place, claim, value in [s for s in am.unused_sightings() if s[0] == t]:
                print(f'{t:>4}  reported without a belief: {item} {claim} = {value} at {place}')
            position = action[1]
            action = None

        if action is None:
            action = am.decide(t, position)
            if action is None:
                if not idle:
                    print(f'{t:>4}  at {position:<15} idle')
                idle = True
            else:
                idle = False
                p, c = am.p(action, t), am.cost(action, position)
                ends = t + c
                print(f'{t:>4}  at {position:<15} {action[0]} {action[1]:<15} P = {p:.3f}  C = {c:>4g}  U = {p / c:.4f}  ends {ends:g}')

        writer.writerow(log_row(am, executor, t, position, action))
    log.close()
    print(f'unused sightings: {len(am.unused_sightings())}')
    print(f'log: {log_file}')


if __name__ == '__main__':
    folder, world = Path(sys.argv[1]), Path(sys.argv[2])
    log_file = Path(__file__).resolve().parent / 'runs' / f'{folder.resolve().name}_{world.resolve().name}.csv'
    run(load_scenario(folder), world, log_file)
