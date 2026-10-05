"""The graphs for one goal, each as (nodes, edges), edges being (from, label, to). No ROS.

Graph 1: goal -> conditions -> items, plus every place and item in the scenario.
Graph 2: goal -> conditions -> items, plus each item's ConceptNet word and that word's ConceptNet edges.
Graph 3: graph 2 pruned to the scenario's own words, linked back to their things.
Graph 4: graph 3 condensed: each item -> place link becomes a belief with its relevance A.

Run:  python3 graph.py <scenario folder> <goal>
python3 graph.py ../../scenarios/drinks serve_guests
"""

import sys
from pathlib import Path

import pyoxigraph as ox

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import beliefs
import conceptnet
import soma

CN = 'http://cognitive-nav.org/ontology#'
DUL = 'http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#'

# The types that say what kind of thing a node is.
KINDS = {DUL + 'Goal': 'goal', CN + 'Condition': 'condition', CN + 'Item': 'item type', CN + 'Place': 'place'}


def load(scenario):
    """SOMA plus the scenario's goals, mapping and things, in one store."""
    store = soma.load_soma()
    for name in ['goals.ttl', 'mapping.ttl', 'things.ttl']:
        store.load(path=str(Path(scenario) / name), format=ox.RdfFormat.TURTLE)
    return store


def kinds(store):
    """{thing: kind} for every goal, condition, item and place, read from their types."""
    query = 'SELECT ?thing ?type WHERE { ?thing a ?type }'
    return {soma.short(row['thing']): KINDS[row['type'].value] for row in store.query(query) if row['type'].value in KINDS}


def nodes_of(edges):
    return {node for start, label, end in edges for node in (start, end)}


def goal_edges(store, goal):
    """Goal -> conditions -> items."""
    query = f'SELECT ?condition ?item WHERE {{ <{CN}{goal}> <{CN}requires> ?condition . ?condition <{CN}about> ?item }}'
    edges = []
    for row in store.query(query):
        condition, item = soma.short(row['condition']), soma.short(row['item'])
        edges += [(goal, 'requires', condition), (condition, 'about', item)]
    return edges


def graph_1(store, goal):
    """Goal -> conditions -> items, plus every place and item in the scenario."""
    edges = sorted(set(goal_edges(store, goal)))
    things = {thing for thing, kind in kinds(store).items() if kind in ('place', 'item')}
    return nodes_of(edges) | things, edges


def graph_2(store, goal):
    """Goal -> conditions -> items, plus each item's ConceptNet word and that word's ConceptNet edges."""
    edges = goal_edges(store, goal)
    query = f'''SELECT DISTINCT ?item ?word WHERE {{
        <{CN}{goal}> <{CN}requires> ?condition . ?condition <{CN}about> ?item .
        ?item <{CN}conceptnetWord> ?word }}'''
    for row in store.query(query):
        item, word = soma.short(row['item']), row['word'].value
        edges.append((item, 'word', f'word:{word}'))
        edges += [(f'word:{start}', f'{relation} {weight}', f'word:{end}') for relation, start, end, weight in conceptnet.edges(word)]
    edges = sorted(set(edges))
    return nodes_of(edges), edges


def graph_3(store, goal):
    """Graph 2 keeping only ConceptNet edges between words of things in the scenario,
    each word linked back to its thing."""
    query = f'SELECT ?word ?thing WHERE {{ ?thing <{CN}conceptnetWord> ?word }}'
    things = [(f'word:{row["word"].value}', soma.short(row['thing'])) for row in store.query(query)]
    words = {word for word, thing in things}

    nodes, edges = graph_2(store, goal)
    edges = [(start, label, end) for start, label, end in edges
             if not start.startswith('word:') or (start in words and end in words)]

    nodes = nodes_of(edges)
    for word, thing in things:
        if word in nodes:
            edges.append((thing, 'word', word))
    edges = sorted(set(edges))
    return nodes_of(edges), edges


def graph_4(store, goal):
    """Goal -> conditions -> items, then item -> belief -> place for every derived belief, with its A."""
    edges = goal_edges(store, goal)
    for (item, place, claim), a in beliefs.derive_beliefs(store, goal).items():
        belief = f'{item} @ {place}'
        edges += [(item, claim, belief), (belief, f'A = {a:.3f}', place)]
    edges = sorted(set(edges))
    return nodes_of(edges), edges


if __name__ == '__main__':
    scenario, goal = sys.argv[1], sys.argv[2]
    store = load(scenario)
    for build in [graph_1, graph_2, graph_3, graph_4]:
        nodes, edges = build(store, goal)
        print(f'== {build.__name__}: {len(nodes)} nodes')
        for edge in edges:
            print(*edge)
