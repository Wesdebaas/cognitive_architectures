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

        if self.current_goal_index >= len(GOALS):
            return

        goal = GOALS[self.current_goal_index]

        if beliefs[goal] >= GOAL_THRESHOLD:

            self.get_logger().info(
                f"Goal '{goal}' achieved!"
            )

            self.next_goal()

        else:

            self.get_logger().info(
                f"Pursuing '{goal}'..."
            )

    def next_goal(self):

        self.current_goal_index += 1

        if self.current_goal_index < len(GOALS):

            self.get_logger().info(
                f"Next goal: {GOALS[self.current_goal_index]}"
            )

        else:

            self.get_logger().info(
                "Mission completed!"
            )

    def print_goal(self):

        if self.current_goal_index < len(GOALS):

            self.get_logger().info(
                f"Current goal: {GOALS[self.current_goal_index]}"
            )

        else:

            self.get_logger().info(
                "No remaining goals."
            )

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