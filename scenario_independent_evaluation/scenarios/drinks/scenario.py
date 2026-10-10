"""The drinks scenario: which files and sources the awareness manager is given. No ROS.

The only file where this scenario, SOMA and ConceptNet meet. A new scenario = a new folder with its own scenario.py.

Run:  python3 scenario.py <goal>        (prints the beliefs the goal derives)
python3 scenario.py serve_guests
"""

import sys
from pathlib import Path

import pyoxigraph as ox

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from awareness_manager import AwarenessManager
from sources import conceptnet, soma

KNOWLEDGE_FILES = ['goals.ttl', 'mapping.ttl', 'things.ttl']


def knowledge():
    """SOMA plus this scenario's goals, mapping and things, in one store."""
    store = soma.load_soma()
    for name in KNOWLEDGE_FILES:
        store.load(path=str(HERE / name), format=ox.RdfFormat.TURTLE)
    return store


def awareness_manager():
    return AwarenessManager(knowledge(), located_at=conceptnet.located_at)


if __name__ == '__main__':
    goal = sys.argv[1]
    for belief, a in awareness_manager().beliefs(goal).items():
        print(*belief, f'A = {a:.3f}')
