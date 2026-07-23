import json
from datetime import datetime, timezone

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from triplestar_msgs.srv import SelectQuery
from triplestar_msgs.msg import QuerySubstitution

DECAY = 0.8
WINDOW_SECONDS = 5.0   # how far back an observation still counts as "recent"
CYCLE_PERIOD = 1.0     # seconds between cognitive cycles


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

        # Query the knowledge base for the current room
        self.client = self.create_client(
            SelectQuery,
            "/triplestar/query/classify_room",
        )

        # Publish belief state
        self.publisher = self.create_publisher(
            String,
            "/knowledge/beliefs",
            10,
        )

        # Run one cognitive cycle every CYCLE_PERIOD seconds
        self.timer = self.create_timer(CYCLE_PERIOD, self.cycle)

        self.get_logger().info("Knowledge Management Node initialized.")

    def cycle(self):
        """
        Run one cognitive cycle: ask the knowledge base which room we are in,
        considering only observations from the last WINDOW_SECONDS.
        """

        if not self.client.service_is_ready():
            return

        now_seconds = self.get_clock().now().nanoseconds / 1e9
        cutoff = datetime.fromtimestamp(now_seconds - WINDOW_SECONDS, tz=timezone.utc)

        request = SelectQuery.Request()
        request.substitutions = [
            QuerySubstitution(
                variable="cutoff",
                rdf_term=f'"{cutoff.isoformat()}"^^<http://www.w3.org/2001/XMLSchema#dateTime>',
            )
        ]

        future = self.client.call_async(request)
        future.add_done_callback(self.callback)

    def callback(self, future):
        """
        Called when the knowledge base answers with the inferred room(s).
        """

        response = future.result()

        inferred_rooms = self.parse_rooms(response.result)

        self.apply_decay()

        for inferred_room in inferred_rooms:
            self.update_beliefs(inferred_room)

        self.publish_beliefs()

        self.print_beliefs()

    def parse_rooms(self, result_json):
        """
        Extract the inferred room names from the JSON response.

        Example:

            'http://cognitive-nav.org/ontology#LivingRoom' -> 'LivingRoom'
        """

        data = json.loads(result_json)
        return [
            binding["room"]["value"].rsplit("#", 1)[-1]
            for binding in data["results"]["bindings"]
        ]

    def update_beliefs(self, inferred_room):
        """
        Increase the belief associated with the inferred room.

        Example:

            LivingRoom += 1
        """

        self.room_beliefs[inferred_room] += 1.0

    def apply_decay(self):
        """
        Apply memory decay to every room belief.

        Example:

            belief *= DECAY
        """

        for room in self.room_beliefs:
            self.room_beliefs[room] *= DECAY

    def publish_beliefs(self):
        """
        Publish the complete belief state as a JSON string.

        Hint:
            Use json.dumps().
        """

        belief_json = json.dumps(self.room_beliefs)
        self.publisher.publish(String(data=belief_json))


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
