"""Run a policy in one world of a scenario on a 1-second clock, printing every decision. No ROS.

A world is a folder with these files: world.ttl (where every item is at t = 0), world_events.csv (t,item,place: from
time t on, the item is at the place), goal_events.csv (t,goal: from time t on, this goal is active) and, optionally,
knowledge_events.csv (t,file: at time t the awareness manager is told this Turtle file, relative to the world folder).
Only the testbed reads them; the awareness manager learns of a goal when it arrives and of the world by observing.

Each tick: first knowledge is told if due, then a goal arrives if one is due, then the world changes if an event is
due; then, if the running action has ended, the executor reports what it saw (the world at the end of the action) and
the awareness manager stores it; then, if the robot is free, the policy decides. Actions are never interrupted.
A goal the awareness manager does not know is logged and ignored: the previous goal stays active.

The log, runs/<scenario>_<world>[_<policy>].events.jsonl, holds one JSON object per event (start, told, goal, move,
look, decide): everything a replay or a score sheet needs.

Run:  python3 run.py <scenario folder> <world folder> [policy]     (policy: am, the default, or round_robin)
python3 run.py ../scenarios/household ../scenarios/household/worlds/day
"""

import csv
import json
import sys
from pathlib import Path

from baselines import RoundRobin
from executor import Executor
from load import load_scenario

BASELINES = {'round_robin': RoundRobin}


def goal_events(file):
    """[(t, goal)] in time order."""
    with open(file) as f:
        return sorted((float(row['t']), row['goal']) for row in csv.DictReader(f))


def knowledge_events(file):
    """[(t, file name)] in time order; none if the world has no such file."""
    if not file.exists():
        return []
    with open(file) as f:
        return sorted((float(row['t']), row['file']) for row in csv.DictReader(f))


def held(am):
    """[(item, place, t)]: every belief whose last observation said the item is there, and when."""
    return [[belief[0], belief[1], am.last_observation(belief)[0]] for belief in sorted(am.a) if am.seen(belief)]


def counted(am, action, values):
    """The items seen by this action for which the active goal holds a belief at the target."""
    active = am.goal_beliefs.get(am.goal, set())
    return sorted(belief[0] for belief in am.b.get(action, []) if belief in active and values.get(belief[0]))


def options(am, t, position):
    """P, C and U of every action, as the awareness manager sees them at time t, with the beliefs P sums over: the active
    goal's beliefs the action observes."""
    active = am.goal_beliefs.get(am.goal, set())
    found = []
    for action_type, target in sorted(am.b):
        p, c = am.p((action_type, target), t), am.cost((action_type, target), position)
        beliefs = []
        for belief in sorted(am.b[(action_type, target)]):
            if belief in active:
                observation = am.last_observation(belief)
                beliefs.append({'item': belief[0], 'observed': observation[0] if observation else None,
                                'T': am.parameters['T'].get(belief[0]), 'E': round(am.e(belief, t), 4),
                                'A': round(am.a[belief], 4)})
        found.append({'type': action_type, 'target': target, 'P': round(p, 4), 'C': c,
                      'U': None if c is None else round(p / c, 4), 'beliefs': beliefs})
    return found


def run(scenario, world, events_file, policy='am'):
    am = scenario.awareness_manager()
    am.prepare()
    executor = Executor(world / 'world.ttl', world / 'world_events.csv')
    goals = goal_events(world / 'goal_events.csv')
    told = knowledge_events(world / 'knowledge_events.csv')
    settings = scenario.testbed()
    informed = policy == 'am'   # a baseline uses no beliefs and keeps no observations
    decider = am if informed else BASELINES[policy](am)

    position = settings['start_position']
    action, ends, started, idle = None, None, None, False
    events_file.parent.mkdir(parents=True, exist_ok=True)
    events = open(events_file, 'w')

    def event(kind, t, **fields):
        events.write(json.dumps({'event': kind, 't': t, **fields}) + '\n')

    event('start', 0, policy=policy, position=position, locations=executor.locations(),
          threshold=am.parameters['idle_threshold'])

    for t in range(settings['run_length'] + 1):
        while told and told[0][0] <= t:
            name = told.pop(0)[1]
            am.tell((world / name).read_text())
            print(f'{t:>4}  told: {name}')
            event('told', t, file=name, held=held(am))

        while goals and goals[0][0] <= t:
            goal = goals.pop(0)[1]
            known = True
            if informed:
                try:
                    am.set_goal(goal)
                except ValueError:
                    known = False
            print(f'{t:>4}  goal: {goal}' + ('' if known else f' (unknown, {am.goal} stays active)'))
            event('goal', t, goal=goal, known=known, active=am.goal, held=held(am),
                  options=options(am, t, position) if informed else [])

        for _, item, place in executor.advance(t):
            print(f'{t:>4}  world: {item} -> {place or "no place"}')
            event('move', t, item=item, place=place)

        if action is not None and t >= ends:
            values = executor.execute(*action)
            if informed:
                am.observe(action, values, t)
                for s, item, place, claim, value in am.unused_sightings():
                    if s == t:
                        print(f'{t:>4}  reported without a belief: {item} {claim} = {value} at {place}')
            event('look', t, started=started, target=action[1], seen=sorted(values), classes=executor.classes(values),
                  counted=counted(am, action, values) if informed else [])
            position = action[1]
            action = None

        if action is None:
            action = decider.decide(t, position)
            if action is None:
                if not idle:
                    print(f'{t:>4}  at {position:<15} idle')
                    event('decide', t, chosen=None, options=options(am, t, position))
                idle = True
            else:
                idle = False
                started = t
                c = am.cost(action, position)
                ends = t + c
                if informed:
                    p = am.p(action, t)
                    print(f'{t:>4}  at {position:<15} {action[0]} {action[1]:<15} P = {p:.3f}  C = {c:>4g}  U = {p / c:.4f}  ends {ends:g}')
                    event('decide', t, chosen=list(action), options=options(am, t, position))
                else:
                    print(f'{t:>4}  at {position:<15} {action[0]} {action[1]:<15} C = {c:>4g}  ends {ends:g}')
                    event('decide', t, chosen=list(action), options=[])

    events.close()
    if informed:
        print(f'unused sightings: {len(am.unused_sightings())}')
    print(f'events: {events_file}')


if __name__ == '__main__':
    folder, world = Path(sys.argv[1]), Path(sys.argv[2])
    policy = sys.argv[3] if len(sys.argv) > 3 else 'am'
    name = f'{folder.resolve().name}_{world.resolve().name}' + ('' if policy == 'am' else f'_{policy}')
    run(load_scenario(folder), world, Path(__file__).resolve().parent / 'runs' / f'{name}.events.jsonl', policy)
