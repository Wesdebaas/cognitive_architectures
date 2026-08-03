"""Attention: spreading activation over the semantic graph."""

from collections import deque
from pathlib import Path

import rdflib

CN = rdflib.Namespace('http://cognitive-nav.org/ontology#')

PRELOAD = Path(__file__).resolve().parents[2] / 'goal_awareness_kb' / 'preload'


def load_edges(guests='guests_mixed.ttl', preload=PRELOAD):
    """Read the semantic graph as {node: set(successors)}."""
    g = rdflib.Graph()
    for f in ['semantic_graph.ttl', guests]:
        g.parse(preload / f)

    props = set(g.subjects(rdflib.RDFS.subPropertyOf, CN.semanticEdge))
    symmetric = {p for p in props if (p, rdflib.RDF.type, rdflib.OWL.SymmetricProperty) in g}

    edges = {}
    for p in props:
        for subject, obj in g.subject_objects(p):
            edges.setdefault(subject, set()).add(obj)
            if p in symmetric:
                edges.setdefault(obj, set()).add(subject)
    return edges


def load_storage(guests='guests_mixed.ttl', preload=PRELOAD):
    """Which item types are kept at each station, from cn:storedIn."""
    g = rdflib.Graph()
    for f in ['semantic_graph.ttl', guests]:
        g.parse(preload / f)

    storage = {}
    for item, station in g.subject_objects(CN.storedIn):
        storage.setdefault(name(station), []).append(name(item))
    return storage


def distances(edges, goal):
    """Hop count from goal to every node it can reach. Unreachable nodes are absent."""
    d = {goal: 0}
    queue = deque([goal])
    while queue:
        node = queue.popleft()
        for successor in edges.get(node, ()):
            if successor not in d:
                d[successor] = d[node] + 1
                queue.append(successor)
    return d


def attention(d, alpha):
    """A = (1 - alpha)**d. Nodes absent from d are unreachable, so A is zero."""
    return {node: (1.0 - alpha) ** hops for node, hops in d.items()}


def name(node):
    return str(node).split('#')[1]


if __name__ == '__main__':
    alpha = 0.3

    edges = load_edges()
    print(f'{len(edges)} nodes with outgoing edges, alpha = {alpha}\n')

    for goal in ['prepare_dinner', 'serve_guests', 'restock_wine']:
        d = distances(edges, CN[goal])
        a = attention(d, alpha)
        print(goal)
        for node, hops in sorted(d.items(), key=lambda kv: (kv[1], name(kv[0]))):
            print(f'  d={hops}  A={a[node]:.4f}  {name(node)}')
        print()
