"""The whole scenario. Watch it from a second terminal:

    ros2 run goal_awareness_scenario awareness_monitor

Needs the venv:
    source ~/ros2_ws/venv_cogarchs/bin/activate
    cogenv
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_xml.launch_description_sources import XMLLaunchDescriptionSource

# Seconds after launch. Needed for timing node startups.
NAV_DELAY = 15.0
INSPECTION_DELAY = 22.0
KB_DELAY = 28.0
AWARENESS_DELAY = 38.0
EXECUTIVE_DELAY = 45.0


def generate_launch_description():
    scenario = get_package_share_directory('goal_awareness_scenario')
    sim_time = {'use_sim_time': True}

    simulator = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('cognitive_nav'),
            'launch', 'mirte_house.launch.py')),
        launch_arguments={
            'world': os.path.join(scenario, 'worlds', 'scenario_house.world'),
            'robot_xacro_path': os.path.join(
                scenario, 'urdf', 'scenario_mirte_master.xacro'),
            # The robot drives to waypoints that are already known, and facts
            # reach the knowledge base from /scenario/inspection_result rather
            # than from a detection, so nothing here consumes object detection.
            # Disabled to speed up the simulation. 
            'use_yolo': 'false',
        }.items(),
    )

    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            scenario, 'launch', 'navigation.launch.py')),
        launch_arguments={'use_rviz': LaunchConfiguration('use_rviz')}.items(),
    )

    inspection = Node(
        package='goal_awareness_scenario',
        executable='inspection_node',
        name='inspection_node',
        parameters=[sim_time],
        output='screen',
    )

    knowledge_base = IncludeLaunchDescription(
        XMLLaunchDescriptionSource(os.path.join(
            get_package_share_directory('goal_awareness_kb'),
            'launch', 'goal_awareness_kb_triplestar.launch.xml')),
    )

    awareness = Node(
        package='goal_awareness_scenario',
        executable='awareness_manager',
        name='awareness_manager',
        parameters=[sim_time, {
            'use_anticipatory_horizon': ParameterValue(
                LaunchConfiguration('use_anticipatory_horizon'), value_type=bool),
        }],
        output='screen',
    )

    executive = Node(
        package='goal_awareness_scenario',
        executable='executive',
        name='executive',
        parameters=[sim_time],
        arguments=['--max-inspections', LaunchConfiguration('max_inspections')],
        output='screen',
    )

    return LaunchDescription([
        DeclareLaunchArgument('use_rviz', default_value='true'),
        DeclareLaunchArgument(
            'max_inspections', default_value='15',
            description='The executive stops after this many; there is no goal yet'),
        DeclareLaunchArgument(
            'use_anticipatory_horizon', default_value='true'),
        simulator,
        TimerAction(period=NAV_DELAY, actions=[navigation]),
        TimerAction(period=INSPECTION_DELAY, actions=[inspection]),
        TimerAction(period=KB_DELAY, actions=[knowledge_base]),
        TimerAction(period=AWARENESS_DELAY, actions=[awareness]),
        TimerAction(period=EXECUTIVE_DELAY, actions=[executive]),
    ])
