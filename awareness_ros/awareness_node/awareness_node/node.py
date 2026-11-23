"""The awareness manager as a ROS node: takes goals and knowledge, and sends actions to the executor."""

import rclpy
from awareness_msgs.action import Execute
from awareness_msgs.srv import AssertKnowledge, ExpectGoal, SetActiveGoal
from rclpy.action import ActionClient
from rclpy.node import Node

from .build import awareness_manager
from .kb import KBClient


class AwarenessNode(Node):

    def __init__(self):
        super().__init__('awareness_manager')
        claim = self.declare_parameter('claim', 'present').value
        self.position = self.declare_parameter('start_position', 'dock').value
        speed = self.declare_parameter('speed', 0.5).value   # metres per second. Chosen: 0.5
        places = self.declare_parameter('places', '').value   # the scenario's places.csv: where each target is
        self.am = awareness_manager(KBClient(), places, speed, claim)
        self.am.start()
        self.action = None   # the action the executor is carrying out
        self.idle = False
        self.execute = ActionClient(self, Execute, '/execute')
        self.create_service(SetActiveGoal, '/awareness/set_active_goal', self.set_active_goal)
        self.create_service(ExpectGoal, '/awareness/expect_goal', self.expect_goal)
        self.create_service(AssertKnowledge, '/awareness/assert_knowledge', self.assert_knowledge)
        self.create_timer(1.0, self.tick)
        self.get_logger().info(f'ready at {self.position}, {len(self.am.relevance.a)} beliefs')

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def set_active_goal(self, request, response):
        try:
            self.am.set_active_goal(request.goal or None, self.now())
            response.success = True
            self.get_logger().info(f'active goal: {request.goal or "none"}')
        except ValueError as error:
            response.success, response.message = False, str(error)
            self.get_logger().warning(f'goal {request.goal} is unknown; {self.am.goals.active} stays active')
        return response

    def expect_goal(self, request, response):
        self.am.expect_goal(request.goal, request.arrival)
        self.get_logger().info(f'expected: {request.goal} at {request.arrival:g}')
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
