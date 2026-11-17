"""Where ConceptNet says a thing is: AtLocation edges from a selection of ConceptNet 5.7.0."""

FILE = 'conceptnet-5.7.0-selected.tsv'


def word_of(node):
    """'/c/en/glass/n/wn/artifact' -> 'glass'."""
    return node.split('/')[3]


def edges(word, path):
    """(relation, start, end, weight) for every edge with the word at its start or end."""
    found = []
    with open(path) as f:
        for line in f:
            relation, start, end, weight, dataset = line.rstrip('\n').split('\t')
            if word_of(start) == word or word_of(end) == word:
                found.append((relation, word_of(start), word_of(end), float(weight)))
    return found


def votes(weight):
    """ConceptNet's weight back to the votes it was damped from: w <= 2 stays, else (w/2)^2 + 1."""
    return weight if weight <= 2 else (weight / 2) ** 2 + 1


def located_at(word, path):
    """[(place word, votes)] from the AtLocation edges that start at the word."""
    return [(end, votes(weight)) for relation, start, end, weight in edges(word, path)
            if relation == '/r/AtLocation' and start == word]
