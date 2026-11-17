"""The robot's true position from Gazebo, published as odom -> base_link (map -> odom is fixed): nothing else does."""

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_msgs.msg import TFMessage
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster


class Localization(Node):

    def __init__(self):
        super().__init__('localization')
        pose_topic = self.declare_parameter('pose_topic', '/world/default/dynamic_pose/info').value
        fixed = TransformStamped()
        fixed.header.stamp = self.get_clock().now().to_msg()
        fixed.header.frame_id, fixed.child_frame_id = 'map', 'odom'
        fixed.transform.rotation.w = 1.0
        self.static = StaticTransformBroadcaster(self)
        self.static.sendTransform(fixed)
        self.broadcaster = TransformBroadcaster(self)
        self.create_subscription(TFMessage, pose_topic, self.on_poses, 10)

    def on_poses(self, msg):
        """Gazebo's first pose is the robot's: it is the only model that moves in this house."""
        if not msg.transforms:
            return
        out = TransformStamped()
        out.header.stamp = self.get_clock().now().to_msg()
        out.header.frame_id, out.child_frame_id = 'odom', 'base_link'
        out.transform = msg.transforms[0].transform
        self.broadcaster.sendTransform(out)


def main():
    rclpy.init()
    node = Localization()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.try_shutdown()
