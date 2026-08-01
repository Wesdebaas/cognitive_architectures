import os

import rclpy
from rclpy.duration import Duration
from rclpy.node import Node

import yaml
from ament_index_python.packages import get_package_share_directory
from goal_awareness_msgs.msg import InspectionResult, StationContent
from std_msgs.msg import String

REQUEST_TOPIC = '/scenario/inspect_request'
RESULT_TOPIC = '/scenario/inspection_result'
CHECK_PERIOD = 0.1


class InspectionNode(Node):
    """Look inside one station: wait a fixed cost, then report what is there."""

    def __init__(self):
        super().__init__('inspection_node')
        share = get_package_share_directory('goal_awareness_scenario')
        self.declare_parameter('contents_file',
                               os.path.join(share, 'config', 'station_contents.yaml'))
        self.declare_parameter('wait_seconds', 10.0)
        self._contents_file = self.get_parameter('contents_file').value
        self._wait = Duration(seconds=self.get_parameter('wait_seconds').value)

        # Idle while _station is None, inspecting that station otherwise.
        self._station = None
        self._deadline = None

        self._result_pub = self.create_publisher(InspectionResult, RESULT_TOPIC, 10)
        self.create_subscription(String, REQUEST_TOPIC, self._on_request, 10)
        self.create_timer(CHECK_PERIOD, self._on_tick)

        clock = 'sim' if self.get_parameter('use_sim_time').value else 'wall'
        self.get_logger().info(f'ready on {clock} clock, contents from {self._contents_file}')

    def _read_contents(self):
        """Re-read the file on every use, so the world can change between inspections."""
        try:
            with open(self._contents_file) as f:
                return yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError) as e:
            self.get_logger().error(f'cannot read {self._contents_file}: {e}')
            return None

    def _on_request(self, msg):
        station = msg.data
        if self._station is not None:
            self.get_logger().warn(f'still inspecting {self._station}, ignoring {station}')
            return
        contents = self._read_contents()
        if contents is None:
            return
        if station not in contents:
            self.get_logger().error(f'unknown station "{station}", expected {sorted(contents)}')
            return
        self._station = station
        self._deadline = self.get_clock().now() + self._wait
        self.get_logger().info(f'inspecting {station}')

    def _on_tick(self):
        """Poll the deadline instead of sleeping, so /clock keeps being serviced and the node doesn't get stuck."""
        if self._station is None or self.get_clock().now() < self._deadline:
            return
        station, self._station = self._station, None

        # Read again: the observation is of the world at the END of the wait.
        contents = self._read_contents()
        if contents is None:
            return
        msg = InspectionResult()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.station = station
        msg.contents = [StationContent(item=e['item'], quantity=float(e['quantity']))
                        for e in contents.get(station) or []]
        self._result_pub.publish(msg)
        found = ', '.join(f'{c.item}={c.quantity}' for c in msg.contents)
        self.get_logger().info(f'{station}: {found or "nothing"}')


def main(args=None):
    rclpy.init(args=args)
    node = InspectionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
