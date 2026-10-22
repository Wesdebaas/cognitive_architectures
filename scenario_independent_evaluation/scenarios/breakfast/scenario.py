"""The breakfast scenario: which files and sources the awareness manager is given. No ROS.

The only file where this scenario, SOMA and ConceptNet meet. A new scenario = a new folder with its own scenario.py.

Run:  python3 scenario.py <goal>        (prints the beliefs and actions the goal derives)
python3 scenario.py set_table
"""

import csv
import sys
from pathlib import Path

import pyoxigraph as ox
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from awareness_manager import AwarenessManager
from sources import conceptnet, soma

KNOWLEDGE_FILES = ['goals.ttl', 'things.ttl', 'actions.ttl']
WORDS_FILE = HERE.parents[1] / 'sources' / 'soma-conceptnet-words.ttl'
WORLD_FILE = HERE / 'world.ttl'                 # for the testbed's executor only, never for the awareness manager
WORLD_EVENTS_FILE = HERE / 'world_events.csv'   # idem: t,item,place = from time t on, the item is at the place


def knowledge():
    """SOMA, its ConceptNet words, and this scenario's goals, things and action types, in one store."""
    store = soma.load_soma()
    store.load(path=str(WORDS_FILE), format=ox.RdfFormat.TURTLE)
    for name in KNOWLEDGE_FILES:
        store.load(path=str(HERE / name), format=ox.RdfFormat.TURTLE)
    return store


def parameters():
    """The awareness manager's parameters."""
    with open(HERE / 'parameters.yaml') as f:
        return yaml.safe_load(f)


def testbed():
    """The testbed's settings for a run in this scenario; the awareness manager never sees these."""
    with open(HERE / 'testbed.yaml') as f:
        return yaml.safe_load(f)


def travel_times():
    """{(from, to): seconds}, each row read both ways."""
    times = {}
    with open(HERE / 'travel_times.csv') as f:
        for row in csv.DictReader(f):
            times[(row['from'], row['to'])] = times[(row['to'], row['from'])] = float(row['seconds'])
    return times


TRAVEL_TIMES = travel_times()


def travel_time(start, end):
    """Seconds from start to end: 0 if already there, None if the table has no such pair (unreachable)."""
    return 0.0 if start == end else TRAVEL_TIMES.get((start, end))


def awareness_manager():
    # This robot drives, so its transition cost is travel time; ConceptNet's AtLocation is the association source.
    return AwarenessManager(knowledge(), association=conceptnet.located_at, transition_cost=travel_time,
                            parameters=parameters())


if __name__ == '__main__':
    goal = sys.argv[1]
    am = awareness_manager()
    for belief, a in am.beliefs(goal).items():
        print(*belief, f'A = {a:.3f}')
    print()
    for (action_type, target), beliefs in am.actions(goal).items():
        print(action_type, target, beliefs)
