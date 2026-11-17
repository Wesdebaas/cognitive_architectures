"""The day's script: asserts the scenario's knowledge and announces every goal arrival, then sets goals, asserts
knowledge and starts nights on time."""

import csv
from pathlib import Path

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from awareness_msgs.srv import Announce, AssertKnowledge, SetGoal
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

# What comes first when several things fall on the same second, as in the testbed.
NIGHT, ASSERTION, GOAL, END = range(4)


class ScenarioNode(Node):

    def __init__(self):
        super().__init__('scenario')
        world = self.declare_parameter('world', 'household/day').value
        self.folder = Path(get_package_share_directory('awareness_scenario')) / world
        with open(self.folder.parent / 'run.yaml') as f:
            run = yaml.safe_load(f)
        with open(self.folder / 'goal_events.csv') as f:
            goals = [(float(row['t']), row['goal']) for row in csv.DictReader(f)]
        with open(self.folder / 'knowledge_events.csv') as f:
            assertions = [(float(row['t']), row['file']) for row in csv.DictReader(f)]
        self.knowledge = run['knowledge']   # this scenario's own goals and instances, asserted first
        day, days = 24 * run['seconds_per_day_hour'], run['days']
        # (t, what comes first, kind, value): goals every day, knowledge on the first day only, a night after every
        # day but the last, and the end of the run.
        self.arrivals = [(number * day + t, goal) for number in range(days) for t, goal in goals]
        self.timetable = sorted(
            [(t, GOAL, goal) for t, goal in self.arrivals]
            + [(t, ASSERTION, name) for t, name in assertions]
            + [(number * day + run['run_length'], NIGHT, None) for number in range(days - 1)]
            + [((days - 1) * day + run['run_length'], END, None)], key=lambda entry: entry[:2])
        clients = ReentrantCallbackGroup()   # so their answers arrive while the timetable waits for them
        self.set_goal = self.create_client(SetGoal, '/awareness/set_goal', callback_group=clients)
        self.announce = self.create_client(Announce, '/awareness/announce', callback_group=clients)
        self.assert_knowledge = self.create_client(AssertKnowledge, '/awareness/assert_knowledge', callback_group=clients)
        self.announced = False
        self.done = False
        self.create_timer(1.0, self.tick, callback_group=MutuallyExclusiveCallbackGroup())
        self.get_logger().info(f'{world}: {days} days, {len(self.timetable)} entries')

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def tick(self):
        if not self.announced:
            for client in (self.set_goal, self.announce, self.assert_knowledge):
                client.wait_for_service()
            for name in self.knowledge:
                self.call_assert_knowledge(self.folder.parent / name)
            for arrival, goal in self.arrivals:
                self.announce.call(Announce.Request(goal=goal, arrival=arrival))
            self.get_logger().info(f'announced {len(self.arrivals)} goal arrivals')
            self.announced = True
        while self.timetable and self.timetable[0][0] <= self.now():
            t, kind, value = self.timetable.pop(0)
            if kind == NIGHT:
                self.call_set_goal('')
            elif kind == ASSERTION:
                self.call_assert_knowledge(self.folder / value)
            elif kind == GOAL:
                self.call_set_goal(value)
            else:
                self.get_logger().info('run over')
                self.done = True

    def call_assert_knowledge(self, path):
        answer = self.assert_knowledge.call(AssertKnowledge.Request(turtle=path.read_text()))
        self.get_logger().info(f'asserted {path.name}' if answer.success else f'{path.name} refused: {answer.message}')

    def call_set_goal(self, goal):
        answer = self.set_goal.call(SetGoal.Request(goal=goal))
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
