"""Run the awareness manager in the testbed's world on a 1-second clock, printing every decision. No ROS.

Each tick: if the running action has ended, the executor reports what it saw and the awareness manager
observes it; then, if the robot is free, the awareness manager decides. Actions are never interrupted.
After that, E of every belief and P, C, U of every action are logged: runs/<scenario>_<goal>.csv, one row per tick.

Run:  python3 run.py <scenario folder> <goal>
python3 run.py ../scenarios/breakfast set_table
"""

import csv
import sys
from pathlib import Path

from executor import Executor
from load import load_scenario


def log_header(am):
    beliefs, actions = sorted(am.a), sorted(am.b)
    return (['t', 'position', 'running']
            + [f'E {item}@{place}' for item, place, claim in beliefs]
            + [f'{value} {action_type} {target}' for value in 'PCU' for action_type, target in actions])


def log_row(am, t, position, action):
    """The values the awareness manager sees at time t. C and U are empty for an unreachable target."""
    beliefs, actions = sorted(am.a), sorted(am.b)
    p = {o: am.p(o, t) for o in actions}
    c = {o: am.cost(o, position) for o in actions}
    return ([t, position, ' '.join(action) if action else '']
            + [round(am.e(belief, t), 4) for belief in beliefs]
            + [round(p[o], 4) for o in actions]
            + ['' if c[o] is None else c[o] for o in actions]
            + ['' if c[o] is None else round(p[o] / c[o], 4) for o in actions])


def run(scenario, goal, log_file):
    am = scenario.awareness_manager()
    am.set_goal(goal)
    executor = Executor(scenario.WORLD_FILE)
    settings = scenario.testbed()

    position = settings['start_position']
    action, ends, idle = None, None, False
    log_file.parent.mkdir(exist_ok=True)
    log = open(log_file, 'w', newline='')
    writer = csv.writer(log)
    writer.writerow(log_header(am))
    for t in range(settings['run_length'] + 1):
        if action is not None and t >= ends:
            am.observe(executor.execute(*action, am.observes(action)), t)
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

        writer.writerow(log_row(am, t, position, action))
    log.close()
    print(f'log: {log_file}')


if __name__ == '__main__':
    folder, goal = Path(sys.argv[1]), sys.argv[2]
    run(load_scenario(folder), goal, Path(__file__).resolve().parent / 'runs' / f'{folder.resolve().name}_{goal}.csv')
