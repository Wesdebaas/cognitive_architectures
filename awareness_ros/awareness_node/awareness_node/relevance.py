"""Relevance A: which beliefs follow from the knowledge, and how relevant each one's target is for its item."""

import math

from awareness_msgs.msg import Belief, Beliefs, Edge

from .kb import AM, DERIVED, OBSERVATIONS, RDF, short, value


def support(w, c):
    """Shafer's degree of support from weight of evidence w: 1 - e^(c*w), c < 0."""
    return 1 - math.exp(c * w)


class Relevance:

    def __init__(self, kb, knowledge, association, parameters):
        self.kb = kb
        self.knowledge = knowledge
        self.association = association   # word -> [(associated word, votes)], e.g. ConceptNet AtLocation
        self.parameters = parameters
        self.associated = {}   # the association's answers; it does not change during a run
        self.revisions = 0

    def update(self):
        """Replace am:derived with the beliefs that follow now. Returns (added, removed, changed) beliefs."""
        before = self.a
        beliefs = {}
        for goal in self.knowledge.goals:
            for belief, how in self.beliefs(goal).items():
                beliefs.setdefault(belief, self.belief_message(belief, how)).needed_for.append(goal)
        self.revisions += 1
        self.kb.write(Beliefs(number=self.revisions, beliefs=list(beliefs.values())),
                      f'SELECT * WHERE {{ GRAPH <{DERIVED.value}> {{ <{AM}derived> <{AM}revision> {self.revisions} }} }}')
        after = self.a
        return (sorted(set(after) - set(before)), sorted(set(before) - set(after)),
                sorted(b for b in after if b in before and after[b] != before[b]))

    def beliefs(self, goal):
        """{(item, target, claim): how its A was derived} for every item the goal needs.

        A is the same for every goal that needs the belief; the goal decides only whether the belief counts (its
        weight in P). Two independent pieces of evidence, combined as Shafer combines simple support functions:
          A = 1 - (1 - A_source)(1 - A_finds),  A_source = discount x support(w),  A_finds = support(find_votes x n)
        """
        targets = self.knowledge.targets()
        c = self.parameters['c']
        found = {}
        for item, classes in self.knowledge.items(goal).items():
            votes, source = self.nearest_evidence(classes, targets)
            trust = self.discount(classes, source)
            edges = self.edges(self.knowledge.words(source), targets)
            finds = self.finds(item)
            for target in set(votes) | set(finds):
                w, n = votes.get(target, 0.0), finds.get(target, 0)
                from_source = trust * support(w, c)
                from_finds = support(self.parameters['find_votes'] * n, c)
                found[(item, target, self.knowledge.claim)] = {
                    'A': from_source + from_finds - from_source * from_finds, 'w': w, 'discount': trust,
                    'from': sorted(source), 'edges': sorted(edges.get(target, [])), 'finds': n,
                    'A_source': from_source, 'A_finds': from_finds}
        return dict(sorted(found.items()))

    def finds(self, item):
        """{target: how often the item was found there}."""
        query = f'''SELECT ?target (COUNT(?observation) AS ?n) WHERE {{ GRAPH <{OBSERVATIONS.value}> {{
            ?observation a <{AM}Observation> ; <{AM}target> ?target ; <{AM}claim> "{self.knowledge.claim}" ; <{AM}reported> ?report .
            ?report <{AM}item> <{AM}{item}> ; <{AM}find> true }} }} GROUP BY ?target'''
        return {short(row['target']): value(row['n']) for row in self.kb.query(query)}

    def edges(self, words, targets):
        """{target: [(word, target word, votes)]} for every association from these words to a target's word."""
        edges = {}
        for word in words:
            if word not in self.associated:
                self.associated[word] = self.association(word)
            for end, w in self.associated[word]:
                for target_word, target in targets:
                    if end == target_word:
                        edges.setdefault(target, []).append((word, target_word, w))
        return edges

    def evidence(self, words, targets):
        """{target: w}, the votes of the edges summed."""
        return {target: sum(w for word, target_word, w in edges) for target, edges in self.edges(words, targets).items()}

    def nearest_evidence(self, classes, targets):
        """(votes, the classes they came from): climb the classes one level at a time until a level has votes."""
        level, seen = set(classes), set()
        while level:
            votes = self.evidence(self.knowledge.words(level), targets)
            if votes:
                return votes, level
            seen |= level
            level = self.knowledge.parents(level) - seen
        return {}, set()

    def discount(self, own, source):
        """1 - alpha if the votes are borrowed from other classes, else 1."""
        return 1.0 if source == own else 1 - self.parameters['alpha']

    @staticmethod
    def belief_message(belief, how):
        """update adds the goals that need it."""
        item, target, claim = belief
        return Belief(item=item, claim=claim, target=target, relevance=float(how['A']), votes=float(how['w']),
                      votes_from=how['from'], discount=float(how['discount']), finds=how['finds'],
                      edges=[Edge(word=word, target_word=target_word, votes=float(votes))
                             for word, target_word, votes in how['edges']])

    @property
    def a(self):
        """{belief: A} for every belief in am:derived."""
        query = f'''SELECT ?item ?claim ?target ?a WHERE {{ GRAPH <{DERIVED.value}> {{
            ?belief <{RDF}reifies> <<( ?item ?claim ?target )>> ; <{AM}relevance> ?a }} }}'''
        return dict(sorted(((short(row['item']), short(row['target']), short(row['claim'])), value(row['a']))
                           for row in self.kb.query(query)))

    @property
    def goal_beliefs(self):
        """{goal: the beliefs it needs}."""
        query = f'''SELECT ?goal ?item ?claim ?target WHERE {{ GRAPH <{DERIVED.value}> {{
            ?belief <{RDF}reifies> <<( ?item ?claim ?target )>> ; <{AM}neededFor> ?goal }} }}'''
        needs = {goal: set() for goal in self.knowledge.goals}
        for row in self.kb.query(query):
            needs[short(row['goal'])].add((short(row['item']), short(row['target']), short(row['claim'])))
        return needs

    def explanations(self):
        """For every belief in am:derived, how its A was derived, as beliefs() gives it."""
        def rows(pattern, *names):
            query = f'''SELECT ?item ?claim ?target {" ".join("?" + n for n in names)} WHERE {{ GRAPH <{DERIVED.value}> {{
                ?belief <{RDF}reifies> <<( ?item ?claim ?target )>> . {pattern} }} }}'''
            for row in self.kb.query(query):
                yield (short(row['item']), short(row['target']), short(row['claim'])), row
        found = {}
        c = self.parameters['c']
        for belief, row in rows(f'?belief <{AM}relevance> ?a ; <{AM}votes> ?w ; <{AM}discount> ?d ; <{AM}finds> ?n .',
                                'a', 'w', 'd', 'n'):
            w, d, n = value(row['w']), value(row['d']), value(row['n'])
            found[belief] = {'item': belief[0], 'target': belief[1], 'claim': belief[2], 'A': round(value(row['a']), 4),
                             'w': w, 'discount': d, 'finds': n, 'A_source': round(d * support(w, c), 4),
                             'A_finds': round(support(self.parameters['find_votes'] * n, c), 4),
                             'from': [], 'edges': [], 'goals': []}
        for belief, row in rows(f'?belief <{AM}votesFrom> ?cls .', 'cls'):
            found[belief]['from'].append(short(row['cls']))
        for belief, row in rows(f'?belief <{AM}neededFor> ?goal .', 'goal'):
            found[belief]['goals'].append(short(row['goal']))
        for belief, row in rows(f'?belief <{AM}edge> ?e . ?e <{AM}word> ?word ; <{AM}targetWord> ?pw ; <{AM}votes> ?v .',
                                'word', 'pw', 'v'):
            found[belief]['edges'].append([row['word'].value, row['pw'].value, value(row['v'])])
        for how in found.values():
            for key in ('from', 'edges', 'goals'):
                how[key].sort()
        return [found[belief] for belief in sorted(found)]
