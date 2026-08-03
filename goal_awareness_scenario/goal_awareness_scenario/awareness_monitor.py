"""Print the awareness manager's state as a table. Read-only: decides nothing."""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from goal_awareness_msgs.msg import AwarenessState
from goal_awareness_scenario.awareness_manager import STATE_TOPIC


class AwarenessMonitor(Node):

    def __init__(self):
        super().__init__('awareness_monitor')
        self.declare_parameter('every', 2)
        self._seen = 0
        self.create_subscription(AwarenessState, STATE_TOPIC, self._on_state, 10)

    def _on_state(self, msg):
        self._seen += 1
        if self._seen % max(1, self.get_parameter('every').value):
            return

        attention = {a.name: a.value for a in msg.attention}
        lines = [f'\n{msg.active_goal}', f'  {"station":<17}{"P":>8}']
        for station in sorted(msg.priority, key=lambda p: -p.value):
            lines.append(f'  {station.name:<17}{station.value:>8.3f}')

        lines.append(f'\n  {"item":<17}{"E":>8}{"A":>8}')
        for item in msg.epistemic_error:
            lines.append(f'  {item.name:<17}{item.value:>8.3f}{attention.get(item.name, 0.0):>8.3f}')

        print('\n'.join(lines), flush=True)


def main():
    rclpy.init()
    node = AwarenessMonitor()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
