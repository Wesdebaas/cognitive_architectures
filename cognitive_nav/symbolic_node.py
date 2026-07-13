import rclpy
from rclpy.node import Node

from owlready2 import sync_reasoner, default_world
from cognitive_nav.ontology import load_ontology
from yolo_msgs.msg import DetectionArray
from std_msgs.msg import String


# Maximum distance (in meters) for a detection to be added to the ontology
MAX_DETECTION_DISTANCE = 3.0

# Mapping from YOLO class names to ontology class names
LABEL_TO_ONTOLOGY = {
    "sofa":         "Sofa",
    "bed":          "Bed",
    "chair":        "Chair",
    "dining table": "DiningTable",
    "tv":           "TV",
    "cup":          "Cup",
    "refrigerator": "Fridge",
    "oven":         "Oven",
}


class SymbolicNode(Node):

    def __init__(self):
        super().__init__('symbolic_node')

        # Load the ontology and initialize the room instance
        self.onto = load_ontology()
        self.Room = self.onto.Room
        self.room = self.Room("unknown_room_1")

        # Subscribe to 3D detections from YOLO
        self.subscription = self.create_subscription(
            DetectionArray,
            '/yolo/detections_3d',
            self.detections_callback,
            10
        )

        # Publish inferences
        self.publisher = self.create_publisher(
            String,
            "/symbolic/room_inference",
            10,
        )

        self.get_logger().info("Symbolic node initialized")

    def detections_callback(self, msg: DetectionArray):
        """
        Callback for incoming YOLO 3D detections.
        Updates the ontology with the current observations and
        executes one symbolic reasoning cycle.
        """

        # Forget previous observations
        self.room.is_a = [self.Room]
        self.room.contains.clear()

        any_valid = False

        for detection in msg.detections:

            distance = detection.bbox3d.center.position.z

            if distance > MAX_DETECTION_DISTANCE:
                continue

            if self.add_perception(
                detection.class_name,
                detection.id
            ):
                any_valid = True

        if any_valid:
            self.symbolic_cycle()

    def add_perception(self, label, detection_id):

        ontology_class_name = LABEL_TO_ONTOLOGY.get(label)

        if ontology_class_name is None:
            return False

        with self.onto:

            ontology_class = getattr(self.onto, ontology_class_name)

            instance_name = f"{ontology_class_name.lower()}_{detection_id}"

            obj = ontology_class(instance_name)

            self.room.contains.append(obj)

            self.get_logger().info(f"Added '{instance_name}'")

            return True


    def reason(self):
        """
        Perform reasoning on the ontology to infer new knowledge.
        Must be called within the ontology context so the reasoner
        can access all declared axioms.
        """
        with self.onto:
            sync_reasoner(self.onto, debug=0)

    def get_room_type(self):
        """
        Query the inferred types of the current room using owlready2's is_a property.
        Returns all classes (direct and inferred) the room instance belongs to.

        Returns:
            list: A list of inferred classes for the room.
        """
        return list(self.room.is_a)

    def log_ontology_instances(self):
        """
        Log all object instances currently stored in the room's ontology.
        Useful for debugging after reasoning.
        """
        instances = [o.name for o in self.room.contains]
        self.get_logger().info(f"Ontology instances: {instances}")

    def reset_room(self):
        self.room.contains.clear()

    def symbolic_cycle(self):
        """
        Execute one symbolic reasoning cycle.
        """
        self.reason()

        classes = self.get_room_type()

        inferred_rooms = [
            c.name for c in classes
            if hasattr(c, "name")
            and c in (
                self.onto.LivingRoom,
                self.onto.Bedroom,
                self.onto.Kitchen,
                self.onto.DiningRoom,
            )
        ]

        for room in inferred_rooms:

            msg = String()
            msg.data = room

            self.publisher.publish(msg)

            self.get_logger().info(
                f"Published room hypotheses: {room}"
            )

        else:

            self.get_logger().warn(
                "Unable to infer the current room."
            )


def main():
    rclpy.init()

    node = SymbolicNode()

    # Keep the node running and listening for detections
    rclpy.spin(node)

    # Clean up and shut down
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()