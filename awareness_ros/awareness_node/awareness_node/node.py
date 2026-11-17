"""The awareness manager as a ROS node: takes goals, announcements and knowledge, and sends actions to the executor."""

import csv
import math
from functools import partial
from pathlib import Path

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from awareness_msgs.action import Execute
from awareness_msgs.srv import Announce, AssertKnowledge, SetGoal
from rclpy.action import ActionClient
from rclpy.node import Node

from . import conceptnet
from .awareness_manager import AwarenessManager
from .kb import KBClient


class AwarenessNode(Node):

    def __init__(self):
        super().__init__('awareness_manager')
        share = Path(get_package_share_directory('awareness_node'))
        claim = self.declare_parameter('claim', 'present').value
        self.position = self.declare_parameter('start_position', 'dock').value
        self.speed = self.declare_parameter('speed', 0.5).value   # metres per second. Chosen: 0.5
        places = self.declare_parameter('places', '').value   # the scenario's places.csv: where each target is
        with open(share / 'config' / 'parameters.yaml') as f:
            parameters = yaml.safe_load(f)
        with open(places) as f:
            self.coordinates = {row['place']: (float(row['x']), float(row['y'])) for row in csv.DictReader(f)}
        association = partial(conceptnet.located_at, path=share / 'data' / conceptnet.FILE)
        self.am = AwarenessManager(KBClient(), association, claim, self.travel_time, parameters)
        self.am.start()
        self.action = None   # the action the executor is carrying out
        self.idle = False
        self.execute = ActionClient(self, Execute, '/execute')
        self.create_service(SetGoal, '/awareness/set_goal', self.set_goal)
        self.create_service(Announce, '/awareness/announce', self.announce)
        self.create_service(AssertKnowledge, '/awareness/assert_knowledge', self.assert_knowledge)
        self.create_timer(1.0, self.tick)
        self.get_logger().info(f'ready at {self.position}, {len(self.am.relevance.a)} beliefs')

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def travel_time(self, start, end):
        """Whole seconds in a straight line; None if either has no coordinates."""
        if start == end:
            return 0.0
        if start not in self.coordinates or end not in self.coordinates:
            return None
        return float(round(math.dist(self.coordinates[start], self.coordinates[end]) / self.speed))

    def set_goal(self, request, response):
        try:
            self.am.set_goal(request.goal or None)
            response.success = True
            self.get_logger().info(f'goal: {request.goal or "none"}')
        except ValueError as error:
            response.success, response.message = False, str(error)
            self.get_logger().warning(f'goal {request.goal} is unknown; {self.am.priority.goal} stays active')
        return response

    def announce(self, request, response):
        self.am.announce(request.goal, request.arrival)
        self.get_logger().info(f'announced: {request.goal} at {request.arrival:g}')
        return response

    def assert_knowledge(self, request, response):
        try:
            added, removed, changed = self.am.assert_knowledge(request.turtle, self.now())
            response.success = True
            self.get_logger().info(f'asserted: {len(added)} beliefs added, {len(removed)} removed')
        except SyntaxError as error:
            response.success, response.message = False, str(error)
            self.get_logger().warning(f'could not read the asserted Turtle: {error}')
        return response

    def tick(self):
        """Decide while the robot is free; the executor must be there to carry the action out."""
        if self.action is None and self.execute.server_is_ready():
            self.decide()

    def decide(self):
        t = self.now()
        action = self.am.decide(t, self.position)
        if action is None:
            if not self.idle:
                self.get_logger().info(f'at {self.position}: wait')
            self.idle = True
            return
        self.idle = False
        self.action = action
        p, c = self.am.priority.p(action, t), self.am.decision.cost(action, self.position)
        self.get_logger().info(f'at {self.position}: {action[0]} {action[1]}  P = {p:.3f}  C = {c:g}  U = {p / c:.4f}')
        sent = self.execute.send_goal_async(Execute.Goal(action_type=action[0], target=action[1]))
        sent.add_done_callback(self.accepted)

    def accepted(self, future):
        handle = future.result()
        if not handle.accepted:
            self.get_logger().warning(f'the executor refused {self.action}')
            self.action = None
            return
        handle.get_result_async().add_done_callback(self.finished)

    def finished(self, future):
        result, (action_type, target) = future.result().result, self.action
        if result.success:
            values = {assessment.item: assessment.value for assessment in result.assessed}
            added, removed, changed = self.am.observe(self.action, values, self.now())
            self.position = target
            seen = sorted(item for item, value in values.items() if value)
            self.get_logger().info(f'{action_type} {target}: {", ".join(seen) or "nothing"}'
                                   + (f'; found, {len(changed)} beliefs changed' if changed or added else ''))
        else:
            self.get_logger().warning(f'{action_type} {target} failed: nothing observed')
        self.action = None
        self.decide()


def main():
    rclpy.init()
    node = AwarenessNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.try_shutdown()
