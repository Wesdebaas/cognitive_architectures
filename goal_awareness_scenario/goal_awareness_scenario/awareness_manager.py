"""Awareness manager node: all ROS I/O for the AM.

The ranking itself is computed by attention.py, epistemic.py and priority.py,
which import no ROS and can be run and checked on their own.
"""

import json
import os
from datetime import datetime, timezone

import rclpy
from rclpy.node import Node

from ament_index_python.packages import get_package_share_directory
from goal_awareness_msgs.msg import InspectionResult
from goal_awareness_scenario import params
from goal_awareness_scenario.epistemic import epistemic_error
from goal_awareness_scenario.inspection_node import RESULT_TOPIC
from triplestar_msgs.srv import SelectQuery

EDGES_SERVICE = '/triplestar/query/semantic_edges'
LAST_OBSERVED_SERVICE = '/triplestar/query/last_observed'
CN = 'http://cognitive-nav.org/ontology#'


def short(uri):
    return uri.rsplit('#', 1)[-1]


def to_posix(stamp):
    """xsd:dateTime string -> seconds. Naive stamps are UTC, never local time."""
    parsed = datetime.fromisoformat(stamp)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


class AwarenessManager(Node):

    def __init__(self):
        super().__init__('awareness_manager')

        config = os.path.join(
            get_package_share_directory('goal_awareness_scenario'),
            'config', 'awareness_params.yaml',
        )
        self.params = params.load(config)

        self.graph = {}
        self.storage = {}
        self.last_observed = {}

        self._edges = self.create_client(SelectQuery, EDGES_SERVICE)
        self._last_observed = self.create_client(SelectQuery, LAST_OBSERVED_SERVICE)
        self.create_subscription(InspectionResult, RESULT_TOPIC, self._on_inspection, 10)

    def fetch_graph(self, timeout=10.0):
        """Read the semantic graph from the KB. Startup only: the graph is static."""
        if not self._edges.wait_for_service(timeout_sec=timeout):
            raise RuntimeError(f'{EDGES_SERVICE} not available after {timeout} s')

        future = self._edges.call_async(SelectQuery.Request())
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        if not response.success:
            raise RuntimeError(f'semantic_edges failed: {response.error_message}')

        self.graph = {}
        self.storage = {}
        for row in json.loads(response.result)['results']['bindings']:
            source, relation, target = (row[k]['value'] for k in ('from', 'relation', 'to'))
            self.graph.setdefault(source, set()).add(target)
            if relation == CN + 'storedIn':
                self.storage.setdefault(short(target), []).append(short(source))

    def request_last_observed(self, timeout=10.0):
        """Ask the KB when each station was last inspected. Returns the future."""
        if not self._last_observed.wait_for_service(timeout_sec=timeout):
            raise RuntimeError(f'{LAST_OBSERVED_SERVICE} not available after {timeout} s')

        future = self._last_observed.call_async(SelectQuery.Request())
        future.add_done_callback(self._store_last_observed)
        return future

    def _store_last_observed(self, future):
        response = future.result()
        if not response.success:
            self.get_logger().error(f'last_observed failed: {response.error_message}')
            return
        self.last_observed = {
            short(row['station']['value']): to_posix(row['last_observed']['value'])
            for row in json.loads(response.result)['results']['bindings']
        }
        self.log_state()

    def _on_inspection(self, msg):
        """An inspection landed in the KB, so the cached timestamps are stale."""
        self.request_last_observed()

    def epistemic_errors(self, now=None):
        """E per item type. A station's inspection refreshes every item kept there."""
        if now is None:
            now = self.get_clock().now().nanoseconds / 1e9
        staleness = self.params['staleness_time']

        errors = {}
        for station, items in self.storage.items():
            observed = self.last_observed.get(station)
            elapsed = float('inf') if observed is None else now - observed
            for item in items:
                errors[item] = epistemic_error(elapsed, staleness[item])
        return errors

    def log_state(self):
        edges = sum(len(t) for t in self.graph.values())
        nodes = set(self.graph) | {t for targets in self.graph.values() for t in targets}
        self.get_logger().info(f'{edges} edges over {len(nodes)} nodes, alpha = {self.params["alpha"]}')
        self.get_logger().info(f'inspected stations: {sorted(self.last_observed) or "none yet"}')
        errors = self.epistemic_errors()
        self.get_logger().info(
            'E: ' + '  '.join(f'{item}={e:.3f}' for item, e in sorted(errors.items()))
        )


def main():
    rclpy.init()
    node = AwarenessManager()
    try:
        node.fetch_graph()
        rclpy.spin_until_future_complete(node, node.request_last_observed())
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
