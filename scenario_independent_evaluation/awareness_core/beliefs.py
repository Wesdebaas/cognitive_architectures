"""Derive the beliefs a goal makes worth having. No ROS.

Run:  python3 beliefs.py <scenario folder> <goal>
python3 draw.py ../../scenarios/drinks serve_guests
"""

import math
import sys
from pathlib import Path

import pyoxigraph as ox

import conceptnet
import soma

CN = 'http://cognitive-nav.org/ontology#'


def load(scenario):
    """SOMA plus the scenario's goals, mapping and things, in one store."""
    store = soma.load_soma()
    for name in ['goals.ttl', 'mapping.ttl', 'things.ttl']:
        store.load(path=str(Path(scenario) / name), format=ox.RdfFormat.TURTLE)
    return store


def hop_factor(weight):
    """How much relevance crosses one ConceptNet edge: between 0 and 1, more for heavier edges."""
    return 1 - math.exp(-weight)
    # return weight / (1 + weight)


def derive_beliefs(store, goal):
    """{(item, place, claim): A} for every place where ConceptNet says an item the goal needs is.

    A = A(item) x hop factor of the heaviest AtLocation edge, with A(item) = 1 because a condition names the item.
    """
    query = f'''SELECT DISTINCT ?item ?word WHERE {{
        <{CN}{goal}> <{CN}requires> ?condition . ?condition <{CN}about> ?item .
        ?item <{CN}conceptnetWord> ?word }}'''
    items = [(row['word'].value, soma.short(row['item'])) for row in store.query(query)]

    query = f'SELECT ?place ?word WHERE {{ ?place a <{CN}Place> ; <{CN}conceptnetWord> ?word }}'
    places = [(row['word'].value, soma.short(row['place'])) for row in store.query(query)]

    weights = {}
    for item_word, item in items:
        for relation, start, end, weight in conceptnet.edges(item_word):
            if relation != '/r/AtLocation' or start != item_word:
                continue
            for place_word, place in places:
                if end == place_word:
                    belief = (item, place, 'present')
                    weights[belief] = max(weight, weights.get(belief, 0.0))
    return {belief: hop_factor(weight) for belief, weight in sorted(weights.items())}


if __name__ == '__main__':
    scenario, goal = sys.argv[1], sys.argv[2]
    for belief, a in derive_beliefs(load(scenario), goal).items():
        print(*belief, f'A = {a:.3f}')
