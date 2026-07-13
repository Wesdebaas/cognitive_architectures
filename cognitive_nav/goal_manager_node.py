import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


GOALS = [
    "Kitchen",
    "Bedroom",
]

GOAL_THRESHOLD = 1.5


class GoalManagerNode(Node):

    def __init__(self):
        super().__init__("goal_manager_node")

        self.current_goal_index = 0

        self.subscription = self.create_subscription(
            String,
            "/knowledge/beliefs",
            self.callback,
            10,
        )

        self.get_logger().info("Goal Manager started.")

        self.print_goal()

    def callback(self, msg):

        beliefs = json.loads(msg.data)

        self.print_beliefs(beliefs)

        self.check_goal(beliefs)

    def check_goal(self, beliefs):
        """
        Determine whether the current goal has been achieved.

        Hint:
            - Get the current goal from GOALS.
            - Compare its belief value against GOAL_THRESHOLD.
            - If the goal is reached, activate the next goal.
            - Otherwise, continue pursuing the current goal.
        """

        if self.current_goal_index >= len(GOALS):
            return

        goal = GOALS[self.current_goal_index]
        belief = beliefs.get(goal, 0.0)
        achieved = belief >= GOAL_THRESHOLD

        self.get_logger().info(
            f"Achieved: {'yes' if achieved else 'no'} "
            f"({belief:.2f} / {GOAL_THRESHOLD})"
        )

        if achieved:
            self.next_goal()

        self.print_goal()

    def next_goal(self):
        """
        Activate the next goal.

        When all goals have been completed,
        report that the mission has finished.
        """

        self.current_goal_index += 1

        self.print_goal()

    def print_goal(self):
        """
        Print the current active goal.

        If no goals remain, report that the mission
        has been completed.
        """

        if self.current_goal_index < len(GOALS):
            current_goal = GOALS[self.current_goal_index]
            self.get_logger().info(f"Current goal: {current_goal}")
        else:
            self.get_logger().info("All goals completed. Mission finished.")

    def print_beliefs(self, beliefs):

        self.get_logger().info("Beliefs:")

        for room, belief in beliefs.items():
            self.get_logger().info(
                f"  {room:12} {belief:.2f}"
            )


def main():

    rclpy.init()

    node = GoalManagerNode()

    rclpy.spin(node)

    node.destroy_node()

    rclpy.shutdown()


if __name__ == "__main__":
    main()
