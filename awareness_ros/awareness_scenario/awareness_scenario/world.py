"""The simulated world: where every item is, moved as the scenario says, and what is at a target (/inspect)."""

import csv
from pathlib import Path

import pyoxigraph as ox
import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from awareness_msgs.srv import Inspect
from rclpy.node import Node

AM = 'http://example.org/awareness-manager#'


class WorldNode(Node):

    def __init__(self):
        super().__init__('world')
        world = self.declare_parameter('world', 'household/day').value
        folder = Path(get_package_share_directory('awareness_scenario')) / world
        with open(folder.parent / 'run.yaml') as f:
            run = yaml.safe_load(f)
        store = ox.Store()
        store.load(path=str(folder / 'world.ttl'), format=ox.RdfFormat.TURTLE)
        self.start = {row['item'].value.split('#')[-1]: row['place'].value.split('#')[-1]
                      for row in store.query(f'SELECT ?item ?place WHERE {{ ?item <{AM}isAt> ?place }}')}
        self.where = dict(self.start)
        with open(folder / 'world_events.csv') as f:
            moves = sorted((float(row['t']), row['item'], row['place']) for row in csv.DictReader(f))
        # Every change of the whole run, in time order: (t, item, place), place '' = at no place; item None = night,
        # when everything goes back to where world.ttl says and the next day's moves follow.
        day = 24 * run['seconds_per_day_hour']
        self.changes = []
        for number in range(run['days']):
            self.changes += [(number * day + t, item, place) for t, item, place in moves]
            if number < run['days'] - 1:
                self.changes.append((number * day + run['run_length'], None, None))
        self.changes.sort(key=lambda change: change[0])
        self.create_service(Inspect, '/inspect', self.inspect)
        self.create_timer(1.0, self.advance)
        self.get_logger().info(f'{world}: {len(self.where)} items placed')

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def advance(self):
        """Make every change that is due."""
        t = self.now()
        while self.changes and self.changes[0][0] <= t:
            _, item, place = self.changes.pop(0)
            if item is None:
                for item in sorted(set(self.where) | set(self.start)):
                    self.move(item, self.start.get(item, ''))
            else:
                self.move(item, place)

    def move(self, item, place):
        if self.where.get(item, '') == place:
            return
        if place:
            self.where[item] = place
        else:
            del self.where[item]
        self.get_logger().info(f'{item} -> {place or "no place"}')

    def inspect(self, request, response):
        self.advance()   # a move due now happens before the look, as in the testbed
        response.items = sorted(item for item, place in self.where.items() if place == request.target)
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
