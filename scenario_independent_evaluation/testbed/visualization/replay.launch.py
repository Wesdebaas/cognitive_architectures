"""Replay a finished run: rebuild its bag from its event log, then start RViz, the bag player and the rqt panel. Closing RViz or
the panel stops everything. Does not run the scenario: run.py writes the event log.

Run:  ros2 launch replay.launch.py scenario:=<scenario> run:=<name of the run in testbed/runs>
ros2 launch replay.launch.py scenario:=household run:=household_day
ros2 launch replay.launch.py scenario:=household run:=household_day_round_robin
"""

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, RegisterEventHandler, Shutdown
from launch.event_handlers import OnProcessExit
from launch.substitutions import LaunchConfiguration

HERE = Path(__file__).resolve().parent
SCENARIOS = f"{HERE.parent.parent / 'scenarios'}/"
RUNS = f"{HERE.parent / 'runs'}/"
BAG = [RUNS, LaunchConfiguration('run'), '_bag']


def start_viewer(event, context):
    """Start the viewer if the bag was written. An older bag would not show the current run."""
    if event.returncode != 0:
        return Shutdown(reason='the bag could not be written')
    return [
        ExecuteProcess(cmd=['rviz2', '-d', str(HERE / 'replay.rviz')], output='screen', on_exit=Shutdown()),
        ExecuteProcess(cmd=['ros2', 'bag', 'play', BAG, '--start-paused'], output='screen'),
        ExecuteProcess(cmd=['rqt', '--standalone', 'awareness_replay', '--args', BAG], output='screen', on_exit=Shutdown()),
    ]


def generate_launch_description():
    make_bag = ExecuteProcess(cmd=['python3', str(HERE / 'events_to_bag.py'), [SCENARIOS, LaunchConfiguration('scenario')],
                                   [RUNS, LaunchConfiguration('run'), '.events.jsonl'], BAG], output='screen')
    return LaunchDescription([
        DeclareLaunchArgument('scenario', description='folder name in scenarios/'),
        DeclareLaunchArgument('run', description='name of the run in testbed/runs, without extension'),
        make_bag,
        RegisterEventHandler(OnProcessExit(target_action=make_bag, on_exit=start_viewer)),
    ])
