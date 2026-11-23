"""The day's script: asserts the scenario's knowledge and says when to expect each goal, then sets the active goal,
asserts knowledge and starts nights on time."""

from pathlib import Path

import rclpy
from ament_index_python.packages import get_package_share_directory
from awareness_msgs.srv import AssertKnowledge, ExpectGoal, SetActiveGoal
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from .timeline import ASSERTION, GOAL, NIGHT, settings, timetable


class ScenarioNode(Node):

    def __init__(self):
        super().__init__('scenario')
        world = self.declare_parameter('world', 'household/day').value
        self.folder = Path(get_package_share_directory('awareness_scenario')) / world
        run = settings(self.folder)
        self.knowledge = run['knowledge']   # this scenario's own goals and instances, asserted first
        self.arrivals, self.timetable = timetable(self.folder)
        clients = ReentrantCallbackGroup()   # so their answers arrive while the timetable waits for them
        self.set_active_goal = self.create_client(SetActiveGoal, '/awareness/set_active_goal', callback_group=clients)
        self.expect_goal = self.create_client(ExpectGoal, '/awareness/expect_goal', callback_group=clients)
        self.assert_knowledge = self.create_client(AssertKnowledge, '/awareness/assert_knowledge', callback_group=clients)
        self.started = False
        self.done = False
        self.create_timer(1.0, self.tick, callback_group=MutuallyExclusiveCallbackGroup())
        self.get_logger().info(f'{world}: {run['days']} days, {len(self.timetable)} entries')

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def tick(self):
        if not self.started:
            for client in (self.set_active_goal, self.expect_goal, self.assert_knowledge):
                client.wait_for_service()
            for name in self.knowledge:
                self.call_assert_knowledge(self.folder.parent / name)
            for arrival, goal in self.arrivals:
                self.expect_goal.call(ExpectGoal.Request(goal=goal, arrival=arrival))
            self.get_logger().info(f'{len(self.arrivals)} goals expected')
            self.started = True
        while self.timetable and self.timetable[0][0] <= self.now():
            t, kind, value = self.timetable.pop(0)
            if kind == NIGHT:
                self.call_set_active_goal('')
            elif kind == ASSERTION:
                self.call_assert_knowledge(self.folder / value)
            elif kind == GOAL:
                self.call_set_active_goal(value)
            else:
                self.get_logger().info('run over')
                self.done = True

    def call_assert_knowledge(self, path):
        answer = self.assert_knowledge.call(AssertKnowledge.Request(turtle=path.read_text()))
        self.get_logger().info(f'asserted {path.name}' if answer.success else f'{path.name} refused: {answer.message}')

    def call_set_active_goal(self, goal):
        answer = self.set_active_goal.call(SetActiveGoal.Request(goal=goal))
        self.get_logger().info(f'goal: {goal or "none (night)"}' if answer.success else f'goal {goal} refused: {answer.message}')


def main():
    rclpy.init()
    node = ScenarioNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        while rclpy.ok() and not node.done:
            executor.spin_once(timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.try_shutdown()
