"""Driving and inspecting, shared by the tour scripts and the executive."""

import rclpy
from rclpy.duration import Duration

from geometry_msgs.msg import PoseStamped
from goal_awareness_msgs.msg import InspectionResult
from goal_awareness_scenario.inspection_node import REQUEST_TOPIC, RESULT_TOPIC
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


def settle(node, seconds):
    """Spin for a while. A node cannot sleep, only keep checking."""
    deadline = node.get_clock().now() + Duration(seconds=seconds)
    while node.get_clock().now() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)


class Inspector:
    """Ask for one inspection and block until its result comes back."""

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
