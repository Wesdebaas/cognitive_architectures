"""The awareness manager. Knows no scenario, ontology or commonsense source: a scenario's scenario.py
gives it everything it uses. No ROS.

  knowledge   one RDF store: goals, conditions, places, items, their words, and an ontology
  located_at  word -> [(place word, weight)]: where a commonsense source says the thing is
"""

import math

import pyoxigraph as ox

AM = 'http://example.org/awareness-manager#'


def short(term):
    if isinstance(term, ox.BlankNode):
        return '[anonymous]'
    return term.value.split('#')[-1]


def hop_factor(weight):
    """How much relevance crosses one commonsense edge: between 0 and 1, more for heavier edges."""
    return 1 - math.exp(-weight)
    # return weight / (1 + weight)


class AwarenessManager:

    def __init__(self, knowledge, located_at):
        self.knowledge = knowledge
        self.located_at = located_at

    def beliefs(self, goal):
        """{(item, place, claim): A} for every place where the commonsense source says an item the goal needs is.

        A = A(item) x hop factor of the heaviest located-at edge, with A(item) = 1 because a condition names the item.
        """
        query = f'''SELECT DISTINCT ?item ?word WHERE {{
            <{AM}{goal}> <{AM}requires> ?condition . ?condition <{AM}about> ?item .
            ?item <{AM}word> ?word }}'''
        items = [(row['word'].value, short(row['item'])) for row in self.knowledge.query(query)]

        query = f'SELECT ?place ?word WHERE {{ ?place a <{AM}Place> ; <{AM}word> ?word }}'
        places = [(row['word'].value, short(row['place'])) for row in self.knowledge.query(query)]

        weights = {}
        for item_word, item in items:
            for end, weight in self.located_at(item_word):
                for place_word, place in places:
                    if end == place_word:
                        belief = (item, place, 'present')
                        weights[belief] = max(weight, weights.get(belief, 0.0))
        return {belief: hop_factor(weight) for belief, weight in sorted(weights.items())}
