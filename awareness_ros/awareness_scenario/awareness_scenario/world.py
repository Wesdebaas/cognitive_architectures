"""The simulated world: where every item is, moved as the scenario says, and what is at a target (/inspect)."""

from pathlib import Path

import rclpy
from ament_index_python.packages import get_package_share_directory
from awareness_msgs.srv import Inspect
from rclpy.node import Node

from .timeline import World


class WorldNode(Node):

    def __init__(self):
        super().__init__('world')
        world = self.declare_parameter('world', 'household/day').value
        self.world = World(Path(get_package_share_directory('awareness_scenario')) / world)
        self.create_service(Inspect, '/inspect', self.inspect)
        self.create_timer(1.0, self.advance)
        self.get_logger().info(f'{world}: {len(self.world.where)} items placed')

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def advance(self):
        """Make every change that is due."""
        for item, place in self.world.advance(self.now()):
            self.get_logger().info(f'{item} -> {place or "no place"}')

    def inspect(self, request, response):
        self.advance()   # a move due now happens before the look, as in the testbed
        response.items = self.world.inspect(request.target)
        return response


def main():
    rclpy.init()
    node = WorldNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.try_shutdown()
