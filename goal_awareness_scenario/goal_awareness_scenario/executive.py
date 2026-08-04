"""Executive: turn the awareness manager's ranking into drives and inspections."""

import argparse
import os

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.qos import DurabilityPolicy, QoSProfile
from rclpy.utilities import remove_ros_args

import yaml
from ament_index_python.packages import get_package_share_directory
from goal_awareness_msgs.msg import Goal, GoalSet
from goal_awareness_msgs.srv import NextStation
from goal_awareness_scenario.navigation import Inspector, drive, make_pose, settle
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

NEXT_STATION_SERVICE = '/awareness/next_station'
MISSION_TOPIC = '/scenario/mission'

# The mission is a state, not an event: a subscriber that joins late still needs
# the last one that was sent.
LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)

# The awareness manager refreshes its staleness from the KB when an inspection
# lands, and the executive hears about that inspection at the same moment, delay for timing.
SETTLE_SECONDS = 2.0


def mission(nav):
    """The scripted mission as [(goal, eta)], in sim seconds since the run started.

    A goal is dropped once a later one has started, so a finished goal stops
    drawing attention instead of competing with the one that replaced it.
    """
    goals = [(nav.get_parameter('active_goal').value, 0.0),
             (nav.get_parameter('next_goal').value,
              nav.get_parameter('next_goal_eta').value)]
    goals = [(goal, eta) for goal, eta in goals if goal]

    now = nav.get_clock().now().nanoseconds / 1e9
    started = max((eta for _, eta in goals if eta <= now), default=0.0)
    return [(goal, eta) for goal, eta in goals if eta >= started]


def publish_mission(nav, publisher):
    """Say what the mission is. The awareness manager decides what each is worth."""
    msg = GoalSet()
    msg.header.stamp = nav.get_clock().now().to_msg()
    for name, eta in mission(nav):
        goal = Goal()
        goal.name = name
        goal.eta.sec = int(eta)
        goal.eta.nanosec = int((eta % 1) * 1e9)
        msg.goals.append(goal)
    publisher.publish(msg)


def ask_next_station(nav, client, timeout=10.0):
    if not client.wait_for_service(timeout_sec=timeout):
        nav.get_logger().error(f'{NEXT_STATION_SERVICE} not available')
        return None

    future = client.call_async(NextStation.Request())
    rclpy.spin_until_future_complete(nav, future)
    answer = future.result()
    return answer if answer.available else None


def run(nav, inspector, client, publisher, frame_id, stations, limit):
    for cycle in range(1, limit + 1):
        publish_mission(nav, publisher)
        answer = ask_next_station(nav, client)
        if answer is None:
            nav.get_logger().info('nothing worth observing, stopping')
            return

        station, tag = answer.station, f'[{cycle}/{limit}] {answer.station}'
        if station not in stations:
            nav.get_logger().error(f'{tag}: no waypoint for this station, stopping')
            return

        nav.get_logger().info(f'{tag}: chosen at P={answer.priority:.3f}, driving')
        status, seconds = drive(nav, make_pose(nav, frame_id, stations[station]))
        if status != TaskResult.SUCCEEDED.name:
            nav.get_logger().error(f'{tag}: navigation {status}, skipping')
            continue

        nav.get_logger().info(f'{tag}: arrived in {seconds:.1f} s, inspecting')
        result = inspector.inspect(station)
        if result is None:
            nav.get_logger().error(f'{tag}: no result -- is inspection_node running?')
            continue

        found = ', '.join(f'{c.item}={c.quantity}' for c in result.contents)
        nav.get_logger().info(f'{tag}: found {found or "nothing"}')
        settle(nav, SETTLE_SECONDS)

    nav.get_logger().info(f'reached the {limit} inspection limit, stopping')


def main(args=None):
    rclpy.init(args=args)

    share = get_package_share_directory('goal_awareness_scenario')
    parser = argparse.ArgumentParser()
    parser.add_argument('--waypoints', default=os.path.join(share, 'config', 'waypoints.yaml'))
    parser.add_argument('--max-inspections', type=int, default=12,
                        help='stop after this many inspections (there is no goal yet)')
    options = parser.parse_args(remove_ros_args(args)[1:])

    with open(options.waypoints) as f:
        waypoints = yaml.safe_load(f)

    nav = BasicNavigator('executive')
    if not nav.get_parameter('use_sim_time').value:
        nav.get_logger().error('use_sim_time is false, durations would be wall clock')

    nav.declare_parameter('active_goal', 'prepare_dinner')
    nav.declare_parameter('next_goal', 'serve_guests')
    nav.declare_parameter('next_goal_eta', 300.0)

    inspector = Inspector(nav)
    client = nav.create_client(NextStation, NEXT_STATION_SERVICE)
    publisher = nav.create_publisher(GoalSet, MISSION_TOPIC, LATCHED)

    # Before the Nav2 wait, so the awareness manager has the mission
    # before it is asked to rank anything.
    publish_mission(nav, publisher)

    nav.get_logger().info('waiting for Nav2')
    nav.waitUntilNav2Active(localizer='map_server')

    try:
        run(nav, inspector, client, publisher, waypoints['frame_id'],
            waypoints['stations'], options.max_inspections)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        nav.destroy_node()
        rclpy.try_shutdown()
