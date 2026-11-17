"""Stand-in executor: carries an action out in simulation time, without Gazebo, then asks the world what is there.

An action takes exactly as long as the awareness manager expects: travel in a straight line plus the action type's
duration. So a run without Gazebo can be compared with the testbed.
"""

import csv
import math
from pathlib import Path

import pyoxigraph as ox
import rclpy
from ament_index_python.packages import get_package_share_directory
from awareness_msgs.action import Execute
from awareness_msgs.msg import Assessment
from awareness_msgs.srv import Inspect
from rclpy.action import ActionServer
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

AM = 'http://example.org/awareness-manager#'


class ExecutorNode(Node):

    def __init__(self):
        super().__init__('executor')
        scenario = self.declare_parameter('scenario', 'household').value
        self.position = self.declare_parameter('start_position', 'dock').value
        self.speed = self.declare_parameter('speed', 0.5).value   # metres per second, as the AM assumes
        with open(Path(get_package_share_directory('awareness_scenario')) / scenario / 'places.csv') as f:
            self.coordinates = {row['place']: (float(row['x']), float(row['y'])) for row in csv.DictReader(f)}
        types = ox.Store()
        types.load(path=str(Path(get_package_share_directory('awareness_kb')) / 'preload' / 'robot-action-types.ttl'),
                   format=ox.RdfFormat.TURTLE)
        self.durations = {row['type'].value.split('#')[-1]: float(row['seconds'].value) for row in
                          types.query(f'SELECT ?type ?seconds WHERE {{ ?type <{AM}duration> ?seconds }}')}
        # Reentrant, so the clock is still read while an action waits for it.
        group = ReentrantCallbackGroup()
        self.inspect = self.create_client(Inspect, '/inspect', callback_group=group)
        ActionServer(self, Execute, '/execute', self.execute, callback_group=group)
        self.get_logger().info(f'at {self.position}; can do {", ".join(sorted(self.durations))}')

    def seconds(self, action_type, target):
        """Travel in whole seconds plus the duration; None if the target has no coordinates."""
        if target not in self.coordinates or self.position not in self.coordinates:
            return None
        travel = round(math.dist(self.coordinates[self.position], self.coordinates[target]) / self.speed)
        return travel + self.durations[action_type]

    def execute(self, handle):
        action_type, target = handle.request.action_type, handle.request.target
        seconds = self.seconds(action_type, target) if action_type == 'inspect' else None
        if seconds is None:
            self.get_logger().warning(f'cannot {action_type} {target}')
            handle.abort()
            return Execute.Result(success=False)
        self.get_logger().info(f'{action_type} {target}: {seconds:g} s')
        self.get_clock().sleep_for(Duration(seconds=seconds))
        items = self.inspect.call(Inspect.Request(target=target)).items
        self.position = target
        handle.succeed()
        return Execute.Result(success=True, assessed=[Assessment(item=item, value=True) for item in items])


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
