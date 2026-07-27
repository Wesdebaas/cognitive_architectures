import rclpy
from rclpy.node import Node

from geometry_msgs.msg import TransformStamped
from tf2_msgs.msg import TFMessage
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster


class GroundTruthLocalization(Node):

    def __init__(self):
        super().__init__('ground_truth_localization')

        self.declare_parameter('model_name', 'mirte')
        self.declare_parameter('pose_topic', '/world/default/dynamic_pose/info')
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('odom_frame', 'odom')
        self.declare_parameter('base_frame', 'base_link')

        self.model_name = self.get_parameter('model_name').value
        self.map_frame = self.get_parameter('map_frame').value
        self.odom_frame = self.get_parameter('odom_frame').value
        self.base_frame = self.get_parameter('base_frame').value
        pose_topic = self.get_parameter('pose_topic').value

        if not self.get_parameter('use_sim_time').value:
            self.get_logger().error('use_sim_time is false')

        self.tf_broadcaster = TransformBroadcaster(self)
        self.static_broadcaster = StaticTransformBroadcaster(self)
        self.publish_map_to_odom()

        self.seen_robot = False
        self.create_subscription(TFMessage, pose_topic, self.on_poses, 10)
        self.get_logger().info(
            f"Looking for model '{self.model_name}' on {pose_topic}")

    def publish_map_to_odom(self):
        """Send the frames map -> odom"""
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = self.map_frame
        t.child_frame_id = self.odom_frame
        t.transform.rotation.w = 1.0   # translation and x/y/z rotation default to zero
        self.static_broadcaster.sendTransform(t)

    def on_poses(self, msg):
        """Pick our robot out of Gazebo's list and relabel it odom -> base_link."""
        if not msg.transforms:
            return

        # Entry 0 is the model's world pose, and the robot is the only non-static model in this house. 
        transform = msg.transforms[0]

        if not self.seen_robot:
            self.seen_robot = True
            self.get_logger().info(
                f'Publishing {self.odom_frame} -> {self.base_frame}')

        out = TransformStamped()
        out.header.stamp = self.get_clock().now().to_msg()
        out.header.frame_id = self.odom_frame
        out.child_frame_id = self.base_frame
        out.transform = transform.transform
        self.tf_broadcaster.sendTransform(out)

    def warn_if_never_seen(self):
        if self.seen_robot:
            return
        self.get_logger().warn(
            f"No entity named '{self.model_name}' seen yet")


def main(args=None):
    rclpy.init(args=args)
    node = GroundTruthLocalization()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
