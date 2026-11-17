"""One run of a scenario without Gazebo: the KB, the AM node, the world, the stand-in executor, the scenario and a
fast clock. Stops by itself when the run is over.

ros2 launch awareness_scenario run.launch.py [scenario:=household] [world:=day] [speed:=10.0]
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, IncludeLaunchDescription, RegisterEventHandler
from launch.event_handlers import OnProcessExit, OnProcessStart
from launch.events import Shutdown
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    scenario = LaunchConfiguration('scenario')
    world = PathJoinSubstitution([scenario, LaunchConfiguration('world')])
    places = PathJoinSubstitution([FindPackageShare('awareness_scenario'), scenario, 'places.csv'])
    robot = PathJoinSubstitution([FindPackageShare('awareness_scenario'), scenario, 'robot.yaml'])
    sim_time = {'use_sim_time': True}
    am = Node(package='awareness_node', executable='awareness_node', parameters=[sim_time, robot, {'places': places}])
    kb = IncludeLaunchDescription(AnyLaunchDescriptionSource(
        PathJoinSubstitution([FindPackageShare('awareness_kb'), 'launch', 'bringup.launch.xml'])))
    run = Node(package='awareness_scenario', executable='scenario', parameters=[sim_time, {'world': world}])
    return LaunchDescription([
        DeclareLaunchArgument('scenario', default_value='household'),
        DeclareLaunchArgument('world', default_value='day'),
        DeclareLaunchArgument('speed', default_value='10.0'),
        am,
        # The KB listens only to topics that have a publisher when it starts, so it starts after the AM node.
        RegisterEventHandler(OnProcessStart(target_action=am, on_start=[kb])),
        Node(package='awareness_scenario', executable='world', parameters=[sim_time, {'world': world}]),
        Node(package='awareness_scenario', executable='executor', parameters=[sim_time, robot, {'scenario': scenario}]),
        run,
        Node(package='awareness_scenario', executable='clock', parameters=[{'speed': LaunchConfiguration('speed')}]),
        RegisterEventHandler(OnProcessExit(target_action=run, on_exit=[EmitEvent(event=Shutdown(reason='run over'))])),
    ])
