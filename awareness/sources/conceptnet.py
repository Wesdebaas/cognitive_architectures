"""Look up what ConceptNet knows about a word. No ROS.

Run:  python3 conceptnet.py juice wine
"""

import sys
from pathlib import Path

CONCEPTNET_FILE = Path(__file__).resolve().parent / 'conceptnet-5.7.0-selected.tsv'


def word_of(node):
    """'/c/en/glass/n/wn/artifact' -> 'glass'."""
    return node.split('/')[3]


def edges(word, path=CONCEPTNET_FILE):
    """Every edge with the word at its start or end: (relation, start, end, weight)."""
    found = []
    with open(path) as f:
        for line in f:
            relation, start, end, weight, dataset = line.rstrip('\n').split('\t')
            if word_of(start) == word or word_of(end) == word:
                found.append((relation, word_of(start), word_of(end), float(weight)))
    return found


def votes(weight):
    """ConceptNet's edge weight back to the summed votes it was damped from: w <= 2 stays, else (w/2)^2 + 1."""
    return weight if weight <= 2 else (weight / 2) ** 2 + 1


def located_at(word):
    """Where ConceptNet says the thing a word names is: [(place word, votes)], from AtLocation edges starting at the word."""
    return [(end, votes(weight)) for relation, start, end, weight in edges(word) if relation == '/r/AtLocation' and start == word]


if __name__ == '__main__':
    for word in sys.argv[1:]:
        print(f'== {word}')
        for relation, start, end, weight in edges(word):
            print(f'   {start} {relation} {end} {weight}')
