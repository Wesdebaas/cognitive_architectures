"""Run the awareness manager in the testbed's world on a 1-second clock, printing every decision. No ROS.

Each tick: if the running action has ended, the executor reports what it saw and the awareness manager
observes it; then, if the robot is free, the awareness manager decides. Actions are never interrupted.

Run:  python3 run.py <scenario folder> <goal>
python3 run.py ../scenarios/drinks serve_guests
"""

import importlib.util
import sys
from pathlib import Path

from executor import Executor


def load_scenario(folder):
    """The scenario.py module of a scenario folder."""
    spec = importlib.util.spec_from_file_location('scenario', Path(folder) / 'scenario.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(scenario, goal):
    am = scenario.awareness_manager()
    am.set_goal(goal)
    executor = Executor(scenario.WORLD_FILE)
    parameters = scenario.parameters()

    position = parameters['start_position']
    action, ends, idle = None, None, False
    for t in range(parameters['run_length'] + 1):
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


if __name__ == '__main__':
    run(load_scenario(sys.argv[1]), sys.argv[2])
