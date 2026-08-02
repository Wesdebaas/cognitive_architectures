import argparse
import os

import rclpy
from rclpy.duration import Duration
from rclpy.utilities import remove_ros_args

import yaml
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from goal_awareness_msgs.msg import InspectionResult
from goal_awareness_scenario.inspection_node import REQUEST_TOPIC, RESULT_TOPIC
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from std_msgs.msg import String


def make_pose(nav, frame_id, station):
    pose = PoseStamped()
    pose.header.frame_id = frame_id
    pose.header.stamp = nav.get_clock().now().to_msg()
    pose.pose.position.x = station['x']
    pose.pose.position.y = station['y']
    pose.pose.orientation.z = station['qz']
    pose.pose.orientation.w = station['qw']
    return pose


def drive(nav, pose):
    """Send one goal, block until it finishes, return status and sim-clock duration."""
    if not nav.goToPose(pose):
        return 'REJECTED', 0.0

    feedback = None
    while not nav.isTaskComplete():
        feedback = nav.getFeedback() or feedback

    status = nav.getResult().name
    if feedback is None:
        return status, 0.0
    return status, feedback.navigation_time.sec + feedback.navigation_time.nanosec / 1e9


class Inspector:
    """Ask for one inspection and block until its result comes back.    """

    def __init__(self, node):
        self._node = node
        self._pub = node.create_publisher(String, REQUEST_TOPIC, 10)
        node.create_subscription(InspectionResult, RESULT_TOPIC, self._on_result, 10)
        self._pending = None
        self._result = None

    def _on_result(self, msg):
        # Ignore results for anything other than the station we are waiting on.
        if msg.station == self._pending:
            self._result = msg

    def inspect(self, station, timeout=60.0):
        self._pending, self._result = station, None
        self._pub.publish(String(data=station))
        deadline = self._node.get_clock().now() + Duration(seconds=timeout)
        while self._result is None:
            if self._node.get_clock().now() > deadline:
                return None
            rclpy.spin_once(self._node, timeout_sec=0.1)
        return self._result


def run_tour(nav, inspector, frame_id, stations, order):
    for i, name in enumerate(order, 1):
        tag = f'[{i}/{len(order)}] {name}'
        nav.get_logger().info(f'{tag}: driving')

        status, seconds = drive(nav, make_pose(nav, frame_id, stations[name]))
        if status != TaskResult.SUCCEEDED.name:
            nav.get_logger().error(f'{tag}: navigation {status}, skipping')
            continue

        nav.get_logger().info(f'{tag}: arrived in {seconds:.1f} s, inspecting')
        result = inspector.inspect(name)
        if result is None:
            nav.get_logger().error(f'{tag}: no result -- is inspection_node running?')
            continue

        found = ', '.join(f'{c.item}={c.quantity}' for c in result.contents)
        nav.get_logger().info(f'{tag}: found {found or "nothing"}')

    nav.get_logger().info('tour complete')


def main(args=None):
    rclpy.init(args=args)

    share = get_package_share_directory('goal_awareness_scenario')
    parser = argparse.ArgumentParser()
    parser.add_argument('--waypoints', default=os.path.join(share, 'config', 'waypoints.yaml'))
    parser.add_argument('--stations', nargs='*', default=None,
                        help='stations to visit, in order (default: every station)')
    options = parser.parse_args(remove_ros_args(args)[1:])

    with open(options.waypoints) as f:
        waypoints = yaml.safe_load(f)
    stations = waypoints['stations']
    order = options.stations or list(stations)

    nav = BasicNavigator('scenario_tour')
    if not nav.get_parameter('use_sim_time').value:
        nav.get_logger().error('use_sim_time is false, durations would be wall clock')
    unknown = [n for n in order if n not in stations]
    if unknown:
        nav.get_logger().error(f'unknown stations {unknown}, expected {sorted(stations)}')
        return

    inspector = Inspector(nav)
    nav.get_logger().info(f'waiting for Nav2, then visiting {order}')
    nav.waitUntilNav2Active(localizer='map_server')

    try:
        run_tour(nav, inspector, waypoints['frame_id'], stations, order)
    except KeyboardInterrupt:
        pass
    finally:
        nav.destroy_node()
        rclpy.try_shutdown()
