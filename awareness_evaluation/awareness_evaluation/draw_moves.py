"""Draws where a scenario's items start and when they move, from a seed. Writes day/world.ttl and day/world_events.csv.

ros2 run awareness_evaluation draw_moves <scenario folder> <seed>
"""

import random
import sys
from pathlib import Path

import pyoxigraph as ox
import yaml
from awareness_node.build import awareness_manager
from awareness_node.local_kb import LocalKB

AM = 'http://example.org/awareness-manager#'


def possible_places(folder, knowledge):
    """{item: {kind: [place]}}: the places the AM believes an item can be at, the ones ConceptNet links its kind to."""
    am = awareness_manager(LocalKB(), folder / 'places.csv', speed=1.0)  # speed: not used here
    am.start()
    beliefs = []
    for name in knowledge:
        beliefs += am.assert_knowledge((folder / name).read_text(), 0)[0]
    kind = {place: kind for place, kind in query(folder, knowledge,
            f'SELECT ?a ?b WHERE {{ ?a a <{AM}Place> , ?b . FILTER(?b != <{AM}Place>) }}')}
    places = {}
    for item, place, _ in sorted(beliefs):
        places.setdefault(item, {}).setdefault(kind[place], []).append(place)
    return places


def query(folder, knowledge, sparql):
    """[(a, b)] from the scenario's own knowledge, names without prefix."""
    store = ox.Store()
    for name in knowledge:
        store.load(path=str(folder / name), format=ox.RdfFormat.TURTLE)
    return [(row['a'].value.split('#')[-1], row['b'].value.split('#')[-1]) for row in store.query(sparql)]


def draw(rng, kinds, now=None):
    """A kind with equal chance, then one of its places with equal chance; never the place the item is at now."""
    while True:
        place = rng.choice(kinds[rng.choice(sorted(kinds))])
        if place != now:
            return place


def main():
    folder, seed = Path(sys.argv[1]), int(sys.argv[2])
    rng = random.Random(seed)
    with open(folder / 'run.yaml') as f:
        run = yaml.safe_load(f)
    places = possible_places(folder, run['knowledge'])
    persistence = {item: float(mu) for item, mu in query(folder, run['knowledge'],
                   f'SELECT ?a ?b WHERE {{ ?a <{AM}persistence> ?b }}')}

    start = {item: draw(rng, places[item]) for item in sorted(places)}
    moves = []
    for item in sorted(places):
        t, at = 0, start[item]
        while True:
            # Exponential waiting times with mean = the item's persistence, in whole seconds, at least 1.
            t += max(1, round(rng.expovariate(1 / persistence[item])))
            if t >= run['run_length']:
                break
            at = draw(rng, places[item], at)
            moves.append((t, item, at))
    moves.sort(key=lambda move: move[0])

    with open(folder / 'day' / 'world.ttl', 'w') as f:
        f.write(f'@prefix am: <{AM}> .\n\n')
        f.write(f'# Where every item really is at t = 0; world_events.csv changes it. Drawn by draw_moves, seed {seed}.\n')
        for item in sorted(start):
            f.write(f'am:{item} am:isAt am:{start[item]} .\n')
    with open(folder / 'day' / 'world_events.csv', 'w') as f:
        f.write('t,item,place\n')
        for t, item, place in moves:
            f.write(f'{t},{item},{place}\n')
    print(f'{len(start)} items placed, {len(moves)} moves')
