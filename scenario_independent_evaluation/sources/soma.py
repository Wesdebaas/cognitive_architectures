"""Look up what SOMA knows about a class. No ROS.

Run:  python3 soma.py WineBottle Bottle Refrigerator
"""

import sys
from pathlib import Path

import pyoxigraph as ox

SOMA_FILE = Path(__file__).resolve().parent / 'soma-home-2.1.0.ttl'
PREFIXES = '''
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX SOMA: <http://www.ease-crc.org/ont/SOMA.owl#>
'''


def load_soma(path=SOMA_FILE):
    store = ox.Store()
    store.load(path=str(path), format=ox.RdfFormat.TURTLE)
    return store


def short(term):
    if isinstance(term, ox.BlankNode):
        return '[anonymous]'
    return term.value.split('#')[-1]


def facts(store, name):
    """Everything the file states about the class: (property, value) pairs."""
    query = PREFIXES + f'SELECT ?property ?value WHERE {{ SOMA:{name} ?property ?value }}'
    return [(short(row['property']), short(row['value'])) for row in store.query(query)]


def parents(store, name):
    """All named classes above the class, up to the top."""
    query = PREFIXES + f'SELECT ?parent WHERE {{ SOMA:{name} rdfs:subClassOf+ ?parent }}'
    return sorted(short(row['parent']) for row in store.query(query) if isinstance(row['parent'], ox.NamedNode))


def children(store, name):
    """All named classes below the class, down to the bottom."""
    query = PREFIXES + f'SELECT ?child WHERE {{ ?child rdfs:subClassOf+ SOMA:{name} }}'
    return sorted(short(row['child']) for row in store.query(query) if isinstance(row['child'], ox.NamedNode))


def parent_edges(store, name):
    """(child, parent) for every subclass step from the class up to the top."""
    query = PREFIXES + f'SELECT ?child ?parent WHERE {{ SOMA:{name} rdfs:subClassOf* ?child . ?child rdfs:subClassOf ?parent }}'
    return [(short(row['child']), short(row['parent'])) for row in store.query(query) if isinstance(row['parent'], ox.NamedNode)]


if __name__ == '__main__':
    store = load_soma()
    for name in sys.argv[1:]:
        print(f'== {name}')
        for prop, value in facts(store, name):
            print(f'   {prop:<15} {value}')
        print('   parents: ', parents(store, name))
        print('   children:', children(store, name))
