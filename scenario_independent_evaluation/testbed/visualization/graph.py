"""The graphs for one goal, each as (nodes, edges), edges being (from, label, to). No ROS.

Graph 1: goal -> conditions -> items, plus every place and item in the scenario.
Graph 2: goal -> conditions -> items, plus each item's ConceptNet word and that word's ConceptNet edges.
Graph 3: graph 2 pruned to the scenario's own words, linked back to their things.
Graph 4: graph 3 condensed: each item -> place link becomes a belief with its relevance A.

Graph 2 and 3 draw ConceptNet itself, so unlike the awareness manager they name it.

Run:  python3 graph.py <scenario folder> <goal>
python3 graph.py ../../scenarios/drinks serve_guests
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from awareness_manager import AM, short
from sources import conceptnet

DUL = 'http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#'

# The types that say what kind of thing a node is.
KINDS = {DUL + 'Goal': 'goal', AM + 'Condition': 'condition', AM + 'Item': 'item type', AM + 'Place': 'place'}


def load_scenario(folder):
    """The scenario.py module of a scenario folder."""
    spec = importlib.util.spec_from_file_location('scenario', Path(folder) / 'scenario.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def kinds(store):
    """{thing: kind} for every goal, condition, item and place, read from their types."""
    query = 'SELECT ?thing ?type WHERE { ?thing a ?type }'
    return {short(row['thing']): KINDS[row['type'].value] for row in store.query(query) if row['type'].value in KINDS}


def nodes_of(edges):
    return {node for start, label, end in edges for node in (start, end)}


def goal_edges(store, goal):
    """Goal -> conditions -> items."""
    query = f'SELECT ?condition ?item WHERE {{ <{AM}{goal}> <{AM}requires> ?condition . ?condition <{AM}about> ?item }}'
    edges = []
    for row in store.query(query):
        condition, item = short(row['condition']), short(row['item'])
        edges += [(goal, 'requires', condition), (condition, 'about', item)]
    return edges


def graph_1(am, goal):
    """Goal -> conditions -> items, plus every place and item in the scenario."""
    store = am.knowledge
    edges = sorted(set(goal_edges(store, goal)))
    things = {thing for thing, kind in kinds(store).items() if kind in ('place', 'item')}
    return nodes_of(edges) | things, edges


def graph_2(am, goal):
    """Goal -> conditions -> items, plus each item's ConceptNet word and that word's ConceptNet edges."""
    store = am.knowledge
    edges = goal_edges(store, goal)
    query = f'''SELECT DISTINCT ?item ?word WHERE {{
        <{AM}{goal}> <{AM}requires> ?condition . ?condition <{AM}about> ?item .
        ?item <{AM}word> ?word }}'''
    for row in store.query(query):
        item, word = short(row['item']), row['word'].value
        edges.append((item, 'word', f'word:{word}'))
        edges += [(f'word:{start}', f'{relation} {weight}', f'word:{end}') for relation, start, end, weight in conceptnet.edges(word)]
    edges = sorted(set(edges))
    return nodes_of(edges), edges


def graph_3(am, goal):
    """Graph 2 keeping only ConceptNet edges between words of things in the scenario,
    each word linked back to its thing."""
    store = am.knowledge
    query = f'SELECT ?word ?thing WHERE {{ ?thing <{AM}word> ?word }}'
    things = [(f'word:{row["word"].value}', short(row['thing'])) for row in store.query(query)]
    words = {word for word, thing in things}

    nodes, edges = graph_2(am, goal)
    edges = [(start, label, end) for start, label, end in edges
             if not start.startswith('word:') or (start in words and end in words)]

    nodes = nodes_of(edges)
    for word, thing in things:
        if word in nodes:
            edges.append((thing, 'word', word))
    edges = sorted(set(edges))
    return nodes_of(edges), edges


def graph_4(am, goal):
    """Goal -> conditions -> items, then item -> belief -> place for every derived belief, with its A."""
    edges = goal_edges(am.knowledge, goal)
    for (item, place, claim), a in am.beliefs(goal).items():
        belief = f'{item} @ {place}'
        edges += [(item, claim, belief), (belief, f'A = {a:.3f}', place)]
    edges = sorted(set(edges))
    return nodes_of(edges), edges


if __name__ == '__main__':
    scenario, goal = sys.argv[1], sys.argv[2]
    am = load_scenario(scenario).awareness_manager()
    for build in [graph_1, graph_2, graph_3, graph_4]:
        nodes, edges = build(am, goal)
        print(f'== {build.__name__}: {len(nodes)} nodes')
        for edge in edges:
            print(*edge)
