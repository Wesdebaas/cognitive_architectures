"""Awareness manager node: all ROS I/O for the AM.

The ranking itself is computed by attention.py, epistemic.py and priority.py,
which import no ROS and can be run and checked on their own.
"""

import json
import math
import os
from datetime import datetime, timezone

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile

from ament_index_python.packages import get_package_share_directory
from goal_awareness_msgs.msg import AwarenessState, GoalSet, InspectionResult, NamedValue
from goal_awareness_msgs.srv import NextStation
from goal_awareness_scenario import params
from goal_awareness_scenario.attention import attention, distances, name
from goal_awareness_scenario.epistemic import epistemic_error
from goal_awareness_scenario.inspection_node import RESULT_TOPIC
from goal_awareness_scenario.priority import priority
from triplestar_msgs.srv import SelectQuery

EDGES_SERVICE = '/triplestar/query/semantic_edges'
LAST_OBSERVED_SERVICE = '/triplestar/query/last_observed'
NEXT_STATION_SERVICE = '/awareness/next_station'
MISSION_TOPIC = '/scenario/mission'
STATE_TOPIC = '/awareness/state'
CN = 'http://cognitive-nav.org/ontology#'
TICK_PERIOD = 1.0

LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)


def short(uri):
    return uri.rsplit('#', 1)[-1]


def named(values):
    """Sorted by name, so array indices stay stable for rqt_plot."""
    return [NamedValue(name=key, value=float(value)) for key, value in sorted(values.items())]


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

        self.declare_parameter('use_anticipatory_horizon', True)

        self.graph = {}
        self.storage = {}
        self.last_observed = {}
        self.eta = {}
        self._top = None

        self._edges = self.create_client(SelectQuery, EDGES_SERVICE)
        self._last_observed = self.create_client(SelectQuery, LAST_OBSERVED_SERVICE)
        self.create_subscription(GoalSet, MISSION_TOPIC, self._on_mission, LATCHED)
        self.create_subscription(InspectionResult, RESULT_TOPIC, self._on_inspection, 10)
        self.create_service(NextStation, NEXT_STATION_SERVICE, self._on_next_station)
        self._state = self.create_publisher(AwarenessState, STATE_TOPIC, 10)

    # knowledge base 

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

        edges = sum(len(t) for t in self.graph.values())
        nodes = set(self.graph) | {t for targets in self.graph.values() for t in targets}
        self.get_logger().info(
            f'{edges} edges over {len(nodes)} nodes, alpha = {self.params["alpha"]}')

        # Only start ranking once there is a graph to rank over.
        self.create_timer(TICK_PERIOD, self._tick)

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
        self.get_logger().info(f'inspected: {sorted(self.last_observed) or "nothing yet"}')

    def _on_inspection(self, msg):
        """An inspection landed in the KB, so the cached timestamps are stale."""
        self.request_last_observed()

    # the ranking 

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

    def _on_mission(self, msg):
        """The executive says what the mission is. It repeats itself, so only log changes."""
        eta = {g.name: g.eta.sec + g.eta.nanosec / 1e9 for g in msg.goals}
        if eta != self.eta:
            self.get_logger().info(f'mission: {sorted(eta)}')
        self.eta = eta

    def goals(self, now=None):
        """The mission, as {goal: weight}.

        A goal that has started is worth its full attention. One that has not
        is discounted by how far away it is in time, and without the horizon 
        it is worth nothing, which is the same as not being in the mission at all.
        """
        if now is None:
            now = self.get_clock().now().nanoseconds / 1e9
        horizon = self.get_parameter('use_anticipatory_horizon').value
        decay = math.log(2.0) / self.params['horizon_halflife']

        weights = {}
        for goal, eta in self.eta.items():
            ahead = eta - now
            if ahead <= 0.0:
                weights[goal] = 1.0
            elif horizon:
                weights[goal] = math.exp(-decay * ahead)
        return weights

    def combined_attention(self, goals):
        """A per item, summed over the goals and scaled by each one's weight."""
        combined = {}
        for goal, weight in goals.items():
            if CN + goal not in self.graph:
                self.get_logger().warn(f'goal "{goal}" is not in the semantic graph')
                continue
            reached = distances(self.graph, CN + goal)
            for node, value in attention(reached, self.params['alpha']).items():
                item = name(node)
                combined[item] = combined.get(item, 0.0) + weight * value
        return combined

    def compute(self):
        """E per item, A per item, P per station, for the goals that are active now."""
        goals = self.goals()
        errors = self.epistemic_errors()
        spread = self.combined_attention(goals)
        attentions = {item: spread.get(item, 0.0) for item in errors}
        return goals, errors, attentions, priority(attentions, errors, self.storage)

    def ranking(self):
        """Stations worth observing, best first. Stations at P = 0 are dropped."""
        _, _, _, p = self.compute()
        return sorted(((s, v) for s, v in p.items() if v > 0.0), key=lambda row: -row[1])

    def _tick(self):
        goals, errors, attentions, p = self.compute()

        state = AwarenessState()
        state.header.stamp = self.get_clock().now().to_msg()
        state.mission = ' '.join(f'{goal}={weight:.2f}'
                                 for goal, weight in sorted(goals.items()))
        state.epistemic_error = named(errors)
        state.attention = named(attentions)
        state.priority = named(p)
        self._state.publish(state)

        ranked = sorted(((s, v) for s, v in p.items() if v > 0.0), key=lambda row: -row[1])
        top = ranked[0][0] if ranked else None
        if top == self._top:
            return

        self._top = top
        if ranked:
            self.get_logger().info(
                'ranking: ' + '  '.join(f'{s}={v:.3f}' for s, v in ranked[:3]))
        else:
            self.get_logger().info('nothing worth observing')

    def _on_next_station(self, request, response):
        ranked = self.ranking()
        response.available = bool(ranked)
        if ranked:
            response.station, response.priority = ranked[0]
        return response


def main():
    rclpy.init()
    node = AwarenessManager()
    try:
        node.fetch_graph()
        rclpy.spin_until_future_complete(node, node.request_last_observed())
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
