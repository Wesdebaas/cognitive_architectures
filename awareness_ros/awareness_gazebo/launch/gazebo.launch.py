"""mirte in the AWS small house, driven by Nav2: Gazebo, the robot (no camera, no sonar), its true position, and Nav2.

ros2 launch awareness_gazebo gazebo.launch.py [gui:=false]
"""

import subprocess

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnShutdown
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def stop_gazebo(context):
    """Gazebo's simulator outlives a launch that shuts itself down, so stop it explicitly. A launch starts no new
    process while shutting down, so this runs inside it."""
    subprocess.run(['pkill', '-f', 'gz sim -r .*small_house.world'])
    return []


NAV2 = [('nav2_planner', 'planner_server'), ('nav2_controller', 'controller_server'),
        ('nav2_behaviors', 'behavior_server'), ('nav2_bt_navigator', 'bt_navigator')]


def generate_launch_description():
    house = FindPackageShare('aws_robomaker_small_house_world')
    params = PathJoinSubstitution([FindPackageShare('awareness_gazebo'), 'config', 'nav2_params.yaml'])
    sim_time = {'use_sim_time': True}
    odometry = [('/odom', '/mirte_base_controller/odometry')]
    headless = PythonExpression(["'' if '", LaunchConfiguration('gui'), "' == 'true' else '-s '"])
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true'),
        IncludeLaunchDescription(
            AnyLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare('ros_gz_sim'), 'launch', 'gz_sim.launch.py'])),
            launch_arguments={'gz_args': ['-r ', headless, PathJoinSubstitution([house, 'worlds', 'small_house.world'])]}.items()),
        IncludeLaunchDescription(
            AnyLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare('mirte_gazebo'), 'launch', 'spawn_mirte_master.launch.xml'])),
            launch_arguments={'depth_camera_enable': 'False', 'sonar_enable': 'False'}.items()),
        # Nav2 sends /cmd_vel; mirte's base controller takes it stamped.
        Node(package='twist_stamper', executable='twist_stamper', parameters=[sim_time],
             remappings=[('cmd_vel_in', '/cmd_vel'), ('cmd_vel_out', '/mirte_base_controller/reference')]),
        Node(package='ros_gz_bridge', executable='parameter_bridge', parameters=[sim_time],
             arguments=['/world/default/dynamic_pose/info@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V']),
        Node(package='awareness_gazebo', executable='localization', parameters=[sim_time]),
        Node(package='nav2_map_server', executable='map_server', name='map_server', parameters=[sim_time, {
            'yaml_filename': PathJoinSubstitution([house, 'maps', 'turtlebot3_waffle_pi', 'map.yaml'])}]),
        *[Node(package=package, executable=executable, name=executable, parameters=[params, sim_time], remappings=odometry)
          for package, executable in NAV2],
        RegisterEventHandler(OnShutdown(on_shutdown=[OpaqueFunction(function=stop_gazebo)])),
        Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager_navigation',
             parameters=[sim_time, {'autostart': True, 'node_names': ['map_server'] + [name for _, name in NAV2]}]),
    ])
