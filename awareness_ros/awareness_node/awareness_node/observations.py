"""Observations: what was observed, asserted and announced, and what the last observation of a belief said."""

import pyoxigraph as ox
from awareness_msgs.msg import Announcement, Assertion, Observation, Report

from .kb import AM, OBSERVATIONS, RDF, node, short, stored, value


class Observations:

    def __init__(self, kb, knowledge):
        self.kb = kb
        self.knowledge = knowledge
        self.observed = {}   # belief -> its last observation, until forget drops it
        self.observations = 0
        self.assertions = 0
        self.announcements = 0

    def observe(self, action, values, t):
        """Store what an action reported, {item: value}. Returns the finds: items reported true where the last
        observation did not already say so. A repeat sighting is no find, so a target checked often keeps its A."""
        action_type, target = action
        classes, claim, duration, complete = self.knowledge.types[action_type]
        found = {item for item, reported in values.items() if reported is True and self.seen((item, target, claim)) is not True}
        self.observations += 1
        reports = [Report(item=item, value=reported, find=item in found) for item, reported in values.items()]
        self.kb.write(Observation(number=self.observations, action=action_type, target=target, claim=claim,
                                  t=float(t), complete=complete, reported=reports),
                      stored(f'observation_{self.observations}'))
        items = {item for item, reported in values.items() if reported is True}
        if complete:
            known = {short(row['item']) for row in self.kb.query(f'SELECT ?item WHERE {{ ?item a <{AM}Item> }}')}
            items |= {item for item in known if self.missed(item) == (target, float(t))}
        self.forget(target=target, items=items)
        return found

    def assert_knowledge(self, turtle, t):
        """Store knowledge given as Turtle, with the items it introduces. Earlier empty observations no longer count
        for those items; earlier sightings still do."""
        triples = list(ox.parse(turtle, format=ox.RdfFormat.TURTLE))
        items = {short(triple.subject) for triple in triples
                 if triple.predicate == ox.NamedNode(f'{RDF}type') and triple.object == node('Item')}
        known = {short(row['item']) for row in self.kb.query(f'SELECT ?item WHERE {{ ?item a <{AM}Item> }}')}
        self.assertions += 1
        introduced = sorted(items - known)
        self.kb.write(Assertion(number=self.assertions, t=float(t), introduced=introduced,
                                triples=ox.serialize(triples, format=ox.RdfFormat.N_TRIPLES).decode()),
                      stored(f'assertion_{self.assertions}'))
        self.forget(items=set(introduced))

    def announce(self, goal, t):
        """Store that the goal will arrive at time t."""
        self.announcements += 1
        self.kb.write(Announcement(number=self.announcements, goal=goal, arrival=float(t)),
                      stored(f'announcement_{self.announcements}'))

    def last_observation(self, belief):
        """(t, value) of the last observation of the belief, or None."""
        if belief not in self.observed:
            self.observed[belief] = self.read_last_observation(belief)
        return self.observed[belief]

    def forget(self, target=None, items=()):
        """Drop the remembered last observations at the target and of the items."""
        self.observed = {belief: seen for belief, seen in self.observed.items()
                         if belief[1] != target and belief[0] not in items}

    def missed(self, item):
        """(target, t) of the first complete look that did not see the item where it was last seen; None if none."""
        claim = self.knowledge.claim
        query = f'''SELECT ?target ?t WHERE {{ GRAPH <{OBSERVATIONS.value}> {{
            ?observation a <{AM}Observation> ; <{AM}target> ?target ; <{AM}claim> "{claim}" ; <{AM}t> ?t ; <{AM}reported> ?report .
            ?report <{AM}item> <{AM}{item}> ; <{AM}value> true }} }} ORDER BY DESC(?t) LIMIT 1'''
        for row in self.kb.query(query):
            query = f'''SELECT ?t WHERE {{ GRAPH <{OBSERVATIONS.value}> {{
                ?observation a <{AM}Observation> ; <{AM}target> <{row['target'].value}> ; <{AM}claim> "{claim}" ; <{AM}t> ?t ;
                      <{AM}complete> true
                FILTER(?t > {value(row['t'])})
                FILTER NOT EXISTS {{ ?observation <{AM}reported> ?report . ?report <{AM}item> <{AM}{item}> ; <{AM}value> true }}
                }} }} ORDER BY ?t LIMIT 1'''
            for miss in self.kb.query(query):
                return short(row['target']), value(miss['t'])
        return None

    def read_last_observation(self, belief):
        """An item a complete action did not report has the claim false. For an am:OnePlaceClaim, a sighting elsewhere
        also makes it false here, and once the item is missed where it was last seen, it has moved: what was observed
        elsewhere before the miss no longer counts. An absence stops counting once an assertion introduces the item
        again."""
        item, target, claim = belief
        miss = self.missed(item) if self.knowledge.one_place else None
        after = f'FILTER(?t > {miss[1]})' if miss is not None and miss[0] != target else ''
        not_asserted_since = f'''NOT EXISTS {{
            ?assertion a <{AM}Assertion> ; <{AM}introduced> <{AM}{item}> ; <{AM}t> ?asserted FILTER(?asserted > ?t) }}'''
        query = f'''SELECT ?t ?complete ?value WHERE {{ GRAPH <{OBSERVATIONS.value}> {{
            ?observation a <{AM}Observation> ; <{AM}target> <{AM}{target}> ; <{AM}claim> "{claim}" ; <{AM}t> ?t ;
                  <{AM}complete> ?complete .
            OPTIONAL {{ ?observation <{AM}reported> ?report . ?report <{AM}item> <{AM}{item}> ; <{AM}value> ?value }}
            FILTER(BOUND(?value) || (?complete && {not_asserted_since})) {after} }} }}
            ORDER BY DESC(?t) LIMIT 1'''
        here = None
        for row in self.kb.query(query):
            here = value(row['t']), value(row['value']) if row['value'] is not None else False
        if self.knowledge.one_place:
            query = f'''SELECT ?t WHERE {{ GRAPH <{OBSERVATIONS.value}> {{
                ?observation a <{AM}Observation> ; <{AM}target> ?other ; <{AM}claim> "{claim}" ; <{AM}t> ?t ; <{AM}reported> ?report .
                ?report <{AM}item> <{AM}{item}> ; <{AM}value> true
                FILTER(?other != <{AM}{target}> && {not_asserted_since}) {after} }} }}
                ORDER BY DESC(?t) LIMIT 1'''
            for row in self.kb.query(query):
                if here is None or value(row['t']) > here[0]:
                    return value(row['t']), False
        return here

    def seen(self, belief):
        """What the last observation said: True, False, or None if never observed."""
        observation = self.last_observation(belief)
        return None if observation is None else observation[1]

    def location(self, item):
        """(target, t) where the item was last seen, if still believed there; else None."""
        claim = self.knowledge.claim
        query = f'''SELECT ?target ?t WHERE {{ GRAPH <{OBSERVATIONS.value}> {{
            ?observation a <{AM}Observation> ; <{AM}target> ?target ; <{AM}claim> "{claim}" ; <{AM}t> ?t ; <{AM}reported> ?report .
            ?report <{AM}item> <{AM}{item}> ; <{AM}value> true }} }} ORDER BY DESC(?t) LIMIT 1'''
        for row in self.kb.query(query):
            target = short(row['target'])
            if self.seen((item, target, claim)):
                return target, value(row['t'])
        return None

    def answered(self, goal):
        """{item: (target, t)} once every item the goal needs has a location, else None."""
        where = {}
        for item in sorted(self.knowledge.items(goal)):
            where[item] = self.location(item)
            if where[item] is None:
                return None
        return where or None
