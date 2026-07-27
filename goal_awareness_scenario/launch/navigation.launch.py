import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg = get_package_share_directory('goal_awareness_scenario')

    default_map = PathJoinSubstitution([
        FindPackageShare('aws_robomaker_small_house_world'),
        'maps', 'turtlebot3_waffle_pi', 'map.yaml'
    ])
    default_params = os.path.join(pkg, 'config', 'nav2_params.yaml')

    map_arg = DeclareLaunchArgument(
        'map', default_value=default_map,
        description='Occupancy map for map_server')
    params_arg = DeclareLaunchArgument(
        'params_file', default_value=default_params,
        description='Nav2 parameter file')
    rviz_arg = DeclareLaunchArgument(
        'use_rviz', default_value='true',
        description='Start RViz')
    world_arg = DeclareLaunchArgument(
        'gz_world', default_value='default',
        description='Gazebo world name, used to build the pose topic')

    map_yaml = LaunchConfiguration('map')
    params_file = LaunchConfiguration('params_file')
    use_rviz = LaunchConfiguration('use_rviz')
    gz_world = LaunchConfiguration('gz_world')

    sim_time = {'use_sim_time': True}

    pose_topic = ['/world/', gz_world, '/dynamic_pose/info']

    pose_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='gz_pose_bridge',
        arguments=[pose_topic + ['@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V']],
        parameters=[sim_time],
        output='screen',
    )

    localization = Node(
        package='goal_awareness_scenario',
        executable='ground_truth_localization',
        name='ground_truth_localization',
        parameters=[sim_time, {'pose_topic': pose_topic}],
        output='screen',
    )

    remaps = [('/odom', '/mirte_base_controller/odometry')]

    map_server = Node(
        package='nav2_map_server',
        executable='map_server',
        name='map_server',
        parameters=[sim_time, {'yaml_filename': map_yaml}],
        output='screen',
    )

    planner_server = Node(
        package='nav2_planner',
        executable='planner_server',
        name='planner_server',
        parameters=[params_file, sim_time],
        remappings=remaps,
        output='screen',
    )

    controller_server = Node(
        package='nav2_controller',
        executable='controller_server',
        name='controller_server',
        parameters=[params_file, sim_time],
        remappings=remaps,
        output='screen',
    )

    behavior_server = Node(
        package='nav2_behaviors',
        executable='behavior_server',
        name='behavior_server',
        parameters=[params_file, sim_time],
        remappings=remaps,
        output='screen',
    )

    bt_navigator = Node(
        package='nav2_bt_navigator',
        executable='bt_navigator',
        name='bt_navigator',
        parameters=[params_file, sim_time],
        remappings=remaps,
        output='screen',
    )

    lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_navigation',
        parameters=[sim_time, {
            'autostart': True,
            'node_names': [
                'map_server',
                'planner_server',
                'controller_server',
                'behavior_server',
                'bt_navigator',
            ],
        }],
        output='screen',
    )

    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        parameters=[sim_time],
        condition=IfCondition(use_rviz),
        output='screen',
    )

    return LaunchDescription([
        map_arg,
        params_arg,
        rviz_arg,
        world_arg,
        pose_bridge,
        localization,
        map_server,
        planner_server,
        controller_server,
        behavior_server,
        bt_navigator,
        lifecycle_manager,
        rviz,
    ])
