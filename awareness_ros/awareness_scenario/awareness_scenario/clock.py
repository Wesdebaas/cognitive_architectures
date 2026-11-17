"""A simulation clock that runs a fixed number of times faster than real time, from t = 0.

It holds t = 0 until the AM node is ready, so the run does not start without it.
"""

import rclpy
from awareness_msgs.srv import SetGoal
from builtin_interfaces.msg import Time
from rclpy.node import Node
from rosgraph_msgs.msg import Clock

STEP = 0.01   # wall seconds between two clock messages


class ClockNode(Node):

    def __init__(self):
        super().__init__('clock')
        self.speed = self.declare_parameter('speed', 10.0).value   # simulation seconds per wall second
        self.publisher = self.create_publisher(Clock, '/clock', 10)
        self.ready = self.create_client(SetGoal, '/awareness/set_goal')
        self.t = 0.0
        self.create_timer(STEP, self.tick)

    def tick(self):
        if self.t == 0.0 and not self.ready.service_is_ready():
            self.publisher.publish(Clock(clock=Time()))
            return
        self.t += STEP * self.speed
        seconds = int(self.t)
        self.publisher.publish(Clock(clock=Time(sec=seconds, nanosec=int((self.t - seconds) * 1e9))))


def main():
    rclpy.init()
    node = ClockNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.try_shutdown()
