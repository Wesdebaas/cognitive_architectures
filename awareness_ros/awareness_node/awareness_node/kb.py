"""Reading and writing the KB over ROS, and the names every part uses for it."""

import time

import pyoxigraph as ox
import rclpy
from awareness_msgs.msg import Announcement, Assertion, Beliefs, Decision, Observation
from triplestar_msgs.srv import SPARQLQuery

AM = 'http://example.org/awareness-manager#'
RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
RDFS = 'http://www.w3.org/2000/01/rdf-schema#'
DERIVED = ox.NamedNode(f'{AM}derived')
OBSERVATIONS = ox.NamedNode(f'{AM}observations')
DECISIONS = ox.NamedNode(f'{AM}decisions')

SERVICE = '/triplestar/sparql'
TOPICS = {Observation: '/awareness/observations', Announcement: '/awareness/announcements',
          Assertion: '/awareness/assertions', Beliefs: '/awareness/beliefs', Decision: '/awareness/decisions'}


def short(term):
    if isinstance(term, ox.BlankNode):
        return '[anonymous]'
    return term.value.split('#')[-1]


def node(name):
    return ox.NamedNode(f'{AM}{name}')


def value(literal):
    """A literal as a Python bool, int, float or str."""
    datatype = literal.datatype.value.split('#')[-1]
    if datatype == 'boolean':
        return literal.value == 'true'
    if datatype == 'integer':
        return int(literal.value)
    if datatype in ('double', 'decimal', 'float'):
        return float(literal.value)
    return literal.value


def stored(name, graph=OBSERVATIONS):
    """A SELECT that has a row once am:<name> is in the graph."""
    return f'SELECT * WHERE {{ GRAPH <{graph.value}> {{ <{AM}{name}> ?p ?o }} }}'


class KBClient:

    def __init__(self, timeout=10.0):
        self.timeout = timeout
        # Own node, so it can be called from another node's callback.
        self.node = rclpy.create_node('kb_client')
        self.publishers = {kind: self.node.create_publisher(kind, topic, 10) for kind, topic in TOPICS.items()}
        self.client = self.node.create_client(SPARQLQuery, SERVICE)
        if not self.client.wait_for_service(timeout_sec=timeout):
            raise RuntimeError(f'{SERVICE} is not available: is the KB running?')
        for kind, publisher in self.publishers.items():
            self.wait(lambda: publisher.get_subscription_count() > 0,
                      f'the KB does not listen on {TOPICS[kind]}: start it after this node')

    def query(self, sparql):
        """Answers as from pyoxigraph's Store.query. SELECT only: an ASK crashes the KB."""
        future = self.client.call_async(SPARQLQuery.Request(query=sparql, reasoning=False))
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=self.timeout)
        response = future.result()
        if response is None:
            raise RuntimeError(f'the KB did not answer within {self.timeout} s')
        if not response.success:
            raise RuntimeError(f'the KB could not answer: {response.error_message}')
        return ox.parse_query_results(response.result, format=ox.QueryResultsFormat.JSON)

    def write(self, msg, check=None):
        """Publish msg to the KB; with check, a SELECT, wait until it has a row."""
        self.publishers[type(msg)].publish(msg)
        if check is not None:
            self.wait(lambda: list(self.query(check)), f'the KB did not store {type(msg).__name__} {msg.number}')

    def wait(self, condition, error):
        deadline = time.monotonic() + self.timeout
        while not condition():
            if time.monotonic() > deadline:
                raise RuntimeError(error)
            time.sleep(0.005)

    def close(self):
        self.node.destroy_node()
