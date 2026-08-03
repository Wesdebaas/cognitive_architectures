"""Executive: turn the awareness manager's ranking into drives and inspections."""

import argparse
import os

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.utilities import remove_ros_args

import yaml
from ament_index_python.packages import get_package_share_directory
from goal_awareness_msgs.srv import NextStation
from goal_awareness_scenario.navigation import Inspector, drive, make_pose, settle
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

NEXT_STATION_SERVICE = '/awareness/next_station'

# The awareness manager refreshes its staleness from the KB when an inspection
# lands, and the executive hears about that inspection at the same moment, delay for timing.
SETTLE_SECONDS = 2.0


def ask_next_station(nav, client, timeout=10.0):
    if not client.wait_for_service(timeout_sec=timeout):
        nav.get_logger().error(f'{NEXT_STATION_SERVICE} not available')
        return None

    future = client.call_async(NextStation.Request())
    rclpy.spin_until_future_complete(nav, future)
    answer = future.result()
    return answer if answer.available else None


def run(nav, inspector, client, frame_id, stations, limit):
    for cycle in range(1, limit + 1):
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

    inspector = Inspector(nav)
    client = nav.create_client(NextStation, NEXT_STATION_SERVICE)

    nav.get_logger().info('waiting for Nav2')
    nav.waitUntilNav2Active(localizer='map_server')

    try:
        run(nav, inspector, client, waypoints['frame_id'],
            waypoints['stations'], options.max_inspections)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        nav.destroy_node()
        rclpy.try_shutdown()
