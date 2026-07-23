import json

import rclpy
from rclpy.node import Node

from std_msgs.msg import String

DECAY = 0.8


class KnowledgeManagementNode(Node):

    def __init__(self):
        super().__init__("knowledge_management_node")

        # Belief state
        self.room_beliefs = {
            "LivingRoom": 0.0,
            "Bedroom": 0.0,
            "Kitchen": 0.0,
            "DiningRoom": 0.0,
        }

        # Subscribe to symbolic room inference
        self.subscription = self.create_subscription(
            String,
            "/symbolic/room_inference",
            self.callback,
            10,
        )

        # Publish belief state
        self.publisher = self.create_publisher(
            String,
            "/knowledge/beliefs",
            10,
        )

        self.get_logger().info("Knowledge Management Node initialized.")

    def callback(self, msg: String):
        """
        Called whenever the symbolic reasoner infers a room.
        """

        inferred_room = msg.data

        self.apply_decay()

        self.update_beliefs(inferred_room)

        self.publish_beliefs()

        self.print_beliefs()

    def update_beliefs(self, inferred_room):

        if inferred_room in self.room_beliefs:
            self.room_beliefs[inferred_room] += 1.0

    def apply_decay(self):

        for room in self.room_beliefs:
            self.room_beliefs[room] *= DECAY

    def publish_beliefs(self):

        beliefs = {
            room: round(belief, 2)
            for room, belief in self.room_beliefs.items()
        }

        msg = String()
        msg.data = json.dumps(beliefs)

        self.publisher.publish(msg)

    def print_beliefs(self):

        self.get_logger().info("Current beliefs:")

        for room, belief in self.room_beliefs.items():
            self.get_logger().info(
                f"  {room:12} {belief:.2f}"
            )


def main():

    rclpy.init()
    node = KnowledgeManagementNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()