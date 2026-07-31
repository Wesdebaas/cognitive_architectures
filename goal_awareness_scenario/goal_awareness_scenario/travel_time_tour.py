import argparse
import csv
import os
from collections import Counter

import rclpy
from rclpy.utilities import remove_ros_args

import yaml
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

FIELDS = ['from_station', 'to_station', 'status', 'sim_seconds', 'recoveries']
RESULTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
    'results', 'travel_times.csv')


def make_pose(nav, frame_id, station):
    pose = PoseStamped()
    pose.header.frame_id = frame_id
    pose.header.stamp = nav.get_clock().now().to_msg()
    pose.pose.position.x = station['x']
    pose.pose.position.y = station['y']
    pose.pose.orientation.z = station['qz']
    pose.pose.orientation.w = station['qw']
    return pose


def read_samples(path):
    """Count successful samples per ordered pair so a crashed run can resume."""
    counts = Counter()
    if os.path.exists(path):
        with open(path, newline='') as f:
            for row in csv.DictReader(f):
                if row['status'] == 'SUCCEEDED':
                    counts[(row['from_station'], row['to_station'])] += 1
    return counts


def drive(nav, pose):
    """Send one goal, block until it finishes, return status and sim-clock duration."""
    if not nav.goToPose(pose):
        return 'REJECTED', 0.0, 0

    feedback = None
    while not nav.isTaskComplete():
        feedback = nav.getFeedback() or feedback

    status = nav.getResult().name
    if feedback is None:
        return status, 0.0, 0
    seconds = feedback.navigation_time.sec + feedback.navigation_time.nanosec / 1e9
    return status, seconds, feedback.number_of_recoveries


def run_tour(nav, frame_id, stations, counts, options, handle, writer):
    names = list(stations)
    pairs = [(a, b) for a in names for b in names if a != b]

    current = names[0]
    nav.get_logger().info(f'positioning at {current}')
    drive(nav, make_pose(nav, frame_id, stations[current]))

    for leg in range(options.max_legs):
        if all(counts[p] >= options.repeats for p in pairs):
            nav.get_logger().info('every pair has enough samples')
            return

        target = min((n for n in names if n != current),
                     key=lambda n: counts[(current, n)])
        nav.get_logger().info(
            f'leg {leg + 1}: {current} -> {target} '
            f'(sample {counts[(current, target)] + 1} of {options.repeats})')

        status, seconds, recoveries = drive(
            nav, make_pose(nav, frame_id, stations[target]))
        writer.writerow({
            'from_station': current,
            'to_station': target,
            'status': status,
            'sim_seconds': round(seconds, 2),
            'recoveries': recoveries,
        })
        handle.flush()
        os.fsync(handle.fileno())

        if status == TaskResult.SUCCEEDED.name:
            counts[(current, target)] += 1
        else:
            nav.get_logger().warn(f'{status}, repositioning at {target}')
            retry = drive(nav, make_pose(nav, frame_id, stations[target]))
            if retry[0] != TaskResult.SUCCEEDED.name:
                nav.get_logger().error('could not reposition, stopping')
                return
        current = target

    nav.get_logger().warn(f'reached max_legs ({options.max_legs})')


def main(args=None):
    rclpy.init(args=args)

    share = get_package_share_directory('goal_awareness_scenario')
    parser = argparse.ArgumentParser()
    parser.add_argument('--waypoints', default=os.path.join(share, 'config', 'waypoints.yaml'))
    parser.add_argument('--output', default=RESULTS)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--max-legs', type=int, default=300)
    options = parser.parse_args(remove_ros_args(args)[1:])

    with open(options.waypoints) as f:
        waypoints = yaml.safe_load(f)
    counts = read_samples(options.output)

    os.makedirs(os.path.dirname(options.output), exist_ok=True)
    fresh = not os.path.exists(options.output) or os.path.getsize(options.output) == 0
    handle = open(options.output, 'a', newline='')
    writer = csv.DictWriter(handle, fieldnames=FIELDS)
    if fresh:
        writer.writeheader()

    nav = BasicNavigator()
    if not nav.get_parameter('use_sim_time').value:
        nav.get_logger().error('use_sim_time is false, durations would be wall clock')
    nav.get_logger().info(f'writing to {options.output}')
    nav.waitUntilNav2Active(localizer='map_server')

    try:
        run_tour(nav, waypoints['frame_id'], waypoints['stations'],
                 counts, options, handle, writer)
    except KeyboardInterrupt:
        pass
    finally:
        handle.close()
        nav.destroy_node()
        rclpy.try_shutdown()
