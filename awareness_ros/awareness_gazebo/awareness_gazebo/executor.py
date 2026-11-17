"""Executor in Gazebo: drives to the target with Nav2, takes the action's duration, then asks the world what is there."""

import csv
import math
import time
from pathlib import Path

import pyoxigraph as ox
import rclpy
from ament_index_python.packages import get_package_share_directory
from awareness_msgs.action import Execute
from awareness_msgs.msg import Assessment
from awareness_msgs.srv import Inspect
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient, ActionServer
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

AM = 'http://example.org/awareness-manager#'
SUCCEEDED = 4   # action_msgs/GoalStatus


class ExecutorNode(Node):

    def __init__(self):
        super().__init__('executor')
        scenario = self.declare_parameter('scenario', 'kitchen').value
        with open(Path(get_package_share_directory('awareness_scenario')) / scenario / 'places.csv') as f:
            self.poses = {row['place']: (float(row['x']), float(row['y']), float(row['yaw'])) for row in csv.DictReader(f)}
        types = ox.Store()
        types.load(path=str(Path(get_package_share_directory('awareness_kb')) / 'preload' / 'robot-action-types.ttl'),
                   format=ox.RdfFormat.TURTLE)
        self.durations = {row['type'].value.split('#')[-1]: float(row['seconds'].value) for row in
                          types.query(f'SELECT ?type ?seconds WHERE {{ ?type <{AM}duration> ?seconds }}')}
        # Reentrant, so the clock, Nav2's answer and the world's answer still arrive while an action waits for them.
        group = ReentrantCallbackGroup()
        self.navigate = ActionClient(self, NavigateToPose, '/navigate_to_pose', callback_group=group)
        self.inspect = self.create_client(Inspect, '/inspect', callback_group=group)
        ActionServer(self, Execute, '/execute', self.execute, callback_group=group)
        self.get_logger().info(f'{scenario}: {len(self.poses)} poses; can do {", ".join(sorted(self.durations))}')

    def execute(self, handle):
        action_type, target = handle.request.action_type, handle.request.target
        if action_type != 'inspect' or target not in self.poses:
            self.get_logger().warning(f'cannot {action_type} {target}')
            handle.abort()
            return Execute.Result(success=False)
        start = self.get_clock().now()
        if not self.drive(target):
            self.get_logger().warning(f'could not reach {target}')
            handle.abort()
            return Execute.Result(success=False)
        driven = (self.get_clock().now() - start).nanoseconds / 1e9
        if not self.wait_until(lambda end=self.get_clock().now() + Duration(seconds=self.durations[action_type]):
                               self.get_clock().now() >= end):
            handle.abort()
            return Execute.Result(success=False)
        items = self.inspect.call(Inspect.Request(target=target)).items
        self.get_logger().info(f'{action_type} {target}: drove {driven:.0f} s, saw {", ".join(items) or "nothing"}')
        handle.succeed()
        return Execute.Result(success=True, assessed=[Assessment(item=item, value=True) for item in items])

    def drive(self, target):
        """True once Nav2 has brought the robot to the target's pose."""
        x, y, yaw = self.poses[target]
        goal = NavigateToPose.Goal(pose=PoseStamped())
        goal.pose.header.frame_id = 'map'
        goal.pose.pose.position.x, goal.pose.pose.position.y = x, y
        goal.pose.pose.orientation.z, goal.pose.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
        self.navigate.wait_for_server()
        sent = self.navigate.send_goal_async(goal)
        if not self.wait_until(sent.done) or not sent.result().accepted:
            return False
        result = sent.result().get_result_async()
        return self.wait_until(result.done) and result.result().status == SUCCEEDED

    @staticmethod
    def wait_until(condition):
        """Checks every 10 ms, so a shutdown is noticed while waiting. False on shutdown."""
        while not condition():
            if not rclpy.ok():
                return False
            time.sleep(0.01)
        return True


def main():
    rclpy.init()
    node = ExecutorNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.try_shutdown()
