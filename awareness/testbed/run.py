"""Run a policy in one world of a scenario on a 1-second clock, printing every decision. No ROS.

A world is a folder with these files: world.ttl (where every item is at t = 0), world_events.csv (t,item,place: from
time t on, the item is at the place), goal_events.csv (t,goal: from time t on, this goal is active) and, optionally,
knowledge_events.csv (t,file: at time t the awareness manager is told this Turtle file, relative to the world folder).
Only the testbed reads them. The awareness manager is told every goal arrival in advance, at the start (announce), and
when each goal arrives; of the world it learns only by observing.

A run lasts the scenario's number of days (testbed.yaml). A day is 24 day hours: goals arrive by goal_events.csv during
its first run_length seconds, then it is night, with no active goal; overnight the world goes back to world.ttl and
its events are scheduled again for the next day. Knowledge is told on the first day only, so it is kept, as the
awareness manager keeps every observation.

Each tick: first a night starts if due, then knowledge is told if due (the awareness manager derives its beliefs again), then a goal arrives if
one is due, then the world changes if an event is due; then, if the running action has ended, the executor reports
what it saw (the world at the end of the action) and the awareness manager stores it (a find derives its beliefs again);
then, if anything was told, arrived or observed, whether the active goal is answered is logged when it changes; then, if
the robot is free, the policy decides. Actions are never interrupted.
A goal the awareness manager does not know is logged and ignored: the previous goal stays active.

The log, runs/<scenario>_<world>[_<policy>].events.jsonl, holds one JSON object per event (start, told, goal, move,
look, answered, unanswered, decide, night, day): everything a replay or a score sheet needs.

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
    """P, C and U of every action, as the awareness manager sees them at time t, with the beliefs P sums over: those the
    action observes that a weighted goal needs, each with its weight."""
    found = []
    for action_type, target in sorted(am.b):
        p, c = am.p((action_type, target), t), am.cost((action_type, target), position)
        claim = am.types[action_type][1]
        beliefs = []
        for item, e, a, weight in am.terms((action_type, target), t):
            observation = am.last_observation((item, target, claim))
            beliefs.append({'item': item, 'observed': observation[0] if observation else None,
                            'T': am.persistence(item), 'E': round(e, 4), 'A': round(a, 4), 'weight': round(weight, 4)})
        found.append({'type': action_type, 'target': target, 'P': round(p, 4), 'C': c,
                      'U': None if c is None else round(p / c, 4), 'beliefs': beliefs})
    return found


def run(scenario, world, events_file, policy='am', days=None):
    am = scenario.awareness_manager()
    am.prepare()
    executor = Executor(world / 'world.ttl', world / 'world_events.csv')
    settings = scenario.testbed()
    days = settings['days'] if days is None else days
    day_length = 24 * settings['seconds_per_day_hour']
    goals = [(day * day_length + t, goal) for day in range(days) for t, goal in goal_events(world / 'goal_events.csv')]
    nights = [day * day_length + settings['run_length'] for day in range(days - 1)]   # the last day ends the run
    told = knowledge_events(world / 'knowledge_events.csv')
    informed = policy == 'am'   # a baseline uses no beliefs and keeps no observations
    decider = am if informed else BASELINES[policy](am)

    position = settings['start_position']
    action, ends, started, idle = None, None, None, False
    news = False                 # something was told, arrived or observed this tick
    answered = (None, False)     # (goal, whether the awareness manager last said it is answered)
    events_file.parent.mkdir(parents=True, exist_ok=True)
    events = open(events_file, 'w')

    def event(kind, t, **fields):
        events.write(json.dumps({'event': kind, 't': t, **fields}) + '\n')

    if informed:
        for arrival, goal in goals:
            am.announce(goal, arrival)
    event('start', 0, policy=policy, position=position, locations=executor.locations(),
          threshold=am.parameters['idle_threshold'], c=am.parameters['c'], beliefs=am.explanations(),
          announced=[[goal, arrival] for arrival, goal in goals] if informed else [], days=days, day_length=day_length)

    for t in range((days - 1) * day_length + settings['run_length'] + 1):
        if t > 0 and t % day_length == 0:
            print(f'{t:>4}  day {t // day_length + 1} starts')
            event('day', t, day=t // day_length + 1)

        if nights and nights[0] <= t:
            nights.pop(0)
            if informed:
                am.set_goal(None)
            print(f'{t:>4}  night: no goal is active')
            event('night', t, held=held(am))
            for item, place in executor.new_day(t - settings['run_length'] + day_length):
                print(f'{t:>4}  world, overnight: {item} -> {place or "no place"}')
                event('move', t, item=item, place=place)
            news = True

        while told and told[0][0] <= t:
            name = told.pop(0)[1]
            added, removed, changed = am.tell((world / name).read_text(), t)
            print(f'{t:>4}  told: {name}, {len(added)} beliefs added, {len(removed)} removed')
            event('told', t, file=name, held=held(am), added=[list(b) for b in added], removed=[list(b) for b in removed],
                  changed=[list(b) for b in changed], beliefs=am.explanations())
            news = True

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
            news = True

        for _, item, place in executor.advance(t):
            print(f'{t:>4}  world: {item} -> {place or "no place"}')
            event('move', t, item=item, place=place)

        if action is not None and t >= ends:
            values = executor.execute(*action)
            derived = {}
            if informed:
                added, removed, changed = am.observe(action, values, t)
                for s, item, place, claim, value in am.unused_sightings():
                    if s == t:
                        print(f'{t:>4}  reported without a belief: {item} {claim} = {value} at {place}')
                if added or removed or changed:
                    print(f'{t:>4}  found at {action[1]}: {len(added)} beliefs added, {len(changed)} changed')
                    derived = {'added': [list(b) for b in added], 'removed': [list(b) for b in removed],
                               'changed': [list(b) for b in changed], 'beliefs': am.explanations()}
            event('look', t, started=started, target=action[1], seen=sorted(values), classes=executor.classes(values),
                  counted=counted(am, action, values) if informed else [], **derived)
            position = action[1]
            action = None
            news = True

        if informed and news and am.goal is not None:
            where = am.answered(am.goal)
            state = (am.goal, where is not None)
            if state != answered:
                if where is not None:
                    print(f'{t:>4}  answered: {am.goal}')
                    event('answered', t, goal=am.goal, items=[[item, place, s] for item, (place, s) in where.items()])
                elif answered[0] == am.goal and answered[1]:
                    print(f'{t:>4}  no longer answered: {am.goal}')
                    event('unanswered', t, goal=am.goal)
                answered = state
        news = False

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
