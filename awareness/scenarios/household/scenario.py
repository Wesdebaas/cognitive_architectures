"""The household scenario: which files and sources the awareness manager is given. No ROS.

The only file where this scenario, SOMA and ConceptNet meet. A new scenario = a new folder with its own scenario.py.

Run:  python3 scenario.py <goal>        (prints the beliefs and actions the goal derives)
python3 scenario.py breakfast
"""

import csv
import math
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

# The robot's speed in metres per second. Chosen: 0.5.
SPEED = 0.5


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


def coordinates():
    """{place: (x, y)} in metres."""
    with open(HERE / 'places.csv') as f:
        return {row['place']: (float(row['x']), float(row['y'])) for row in csv.DictReader(f)}


COORDINATES = coordinates()


def travel_time(start, end):
    """Seconds from start to end, whole seconds: 0 if already there, None if either has no coordinates (unreachable)."""
    if start == end:
        return 0.0
    if start not in COORDINATES or end not in COORDINATES:
        return None
    return float(round(math.dist(COORDINATES[start], COORDINATES[end]) / SPEED))


def awareness_manager():
    # This robot drives, so its transition cost is travel time. ConceptNet's AtLocation is the association source;
    # its beliefs claim that the item is present at the place.
    return AwarenessManager(knowledge(), association=conceptnet.located_at, claim='present',
                            transition_cost=travel_time, parameters=parameters())


if __name__ == '__main__':
    goal = sys.argv[1]
    am = awareness_manager()
    for belief, a in am.beliefs(goal).items():
        print(*belief, f'A = {a:.3f}')
    print()
    for (action_type, target), beliefs in am.actions(goal).items():
        print(action_type, target, beliefs)
