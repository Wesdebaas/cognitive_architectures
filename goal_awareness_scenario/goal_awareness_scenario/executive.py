"""Executive: turn the awareness manager's ranking into drives and inspections."""

import argparse
import json
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
from triplestar_msgs.srv import SelectQuery

NEXT_STATION_SERVICE = '/awareness/next_station'
MISSION_TOPIC = '/scenario/mission'

QUERY_SERVICE = '/triplestar/query/'
QUERIES = ('missing_items', 'satisfied_goals', 'item_locations')

# The mission is a state, not an event: a subscriber that joins late still needs
# the last one that was sent.
LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)

# The awareness manager refreshes its staleness from the KB when an inspection
# lands, and the executive hears about that inspection at the same moment, delay for timing.
SETTLE_SECONDS = 2.0


def short(uri):
    return uri.rsplit('#', 1)[-1]


def mission(nav, errands):
    """The mission as [(goal, eta)], in sim seconds since the run started."""
    phases = [(nav.get_parameter('active_goal').value, 0.0),
              (nav.get_parameter('next_goal').value,
               nav.get_parameter('next_goal_eta').value)]
    phases = [(goal, eta) for goal, eta in phases if goal]

    now = nav.get_clock().now().nanoseconds / 1e9
    started = max((eta for _, eta in phases if eta <= now), default=0.0)
    current = [(goal, eta) for goal, eta in phases if eta >= started]

    return current + sorted(errands.items())


def final_phase(nav):
    """The last phase in the script, and when it starts."""
    next_goal = nav.get_parameter('next_goal').value
    if next_goal:
        return next_goal, nav.get_parameter('next_goal_eta').value
    return nav.get_parameter('active_goal').value, 0.0


def publish_mission(nav, publisher, errands):
    """Say what the mission is. The awareness manager decides what each is worth."""
    msg = GoalSet()
    msg.header.stamp = nav.get_clock().now().to_msg()
    for name, eta in mission(nav, errands):
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


def select(nav, kb, query, timeout=10.0):
    """Run a knowledge base query."""
    client = kb[query]
    if not client.wait_for_service(timeout_sec=timeout):
        nav.get_logger().error(f'{query} not available')
        return []

    future = client.call_async(SelectQuery.Request())
    rclpy.spin_until_future_complete(nav, future)
    response = future.result()
    if not response.success:
        nav.get_logger().error(f'{query} failed: {response.error_message}')
        return []

    return json.loads(response.result)['results']['bindings']


def satisfied_goals(nav, kb):
    """The goals with nothing left to find."""
    return {short(row['goal']['value']) for row in select(nav, kb, 'satisfied_goals')}


def raise_errands(nav, kb, errands, satisfied):
    """Add a goal for every item the knowledge base reports as missing.

    The query answers with the goal that restores the item, so no station and
    no goal name is written here. Which station that goal leads to is left to
    attention."""
    now = nav.get_clock().now().nanoseconds / 1e9
    for row in select(nav, kb, 'missing_items'):
        goal, item = (short(row[key]['value']) for key in ('goal', 'item'))
        if goal not in errands and goal not in satisfied:
            errands[goal] = now
            nav.get_logger().info(f'{item} is missing, adding {goal} to the mission')


def report(nav, kb, frame_id, pose, goal):
    """Drive to the guests and tell them where the things they need are."""
    status, seconds = drive(nav, make_pose(nav, frame_id, pose))
    if status != TaskResult.SUCCEEDED.name:
        nav.get_logger().error(f'navigation to the front door {status}')
    else:
        nav.get_logger().info(f'at the front door in {seconds:.1f} s')

    answers = []
    for row in select(nav, kb, 'item_locations'):
        if short(row['goal']['value']) != goal:
            continue
        item, found, station = (short(row[key]['value']) for key in ('item', 'found', 'station'))
        answers.append(f'{item} in the {station}' if item == found
                       else f'no {item}, but {found} in the {station}')
    nav.get_logger().info(f'{goal}: ' + ('; '.join(answers) or 'nothing to report'))


def run(nav, inspector, next_station, kb, publisher, waypoints, limit):
    frame_id, stations = waypoints['frame_id'], waypoints['stations']
    errands = {}
    met = None

    for cycle in range(1, limit + 1):
        publish_mission(nav, publisher, errands)
        answer = ask_next_station(nav, next_station)
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

        # The wait is what lets the knowledge base finish inserting the result,
        # so the queries below see this inspection and not the one before it.
        settle(nav, SETTLE_SECONDS)

        satisfied = satisfied_goals(nav, kb)
        for goal in sorted(satisfied & set(errands)):
            del errands[goal]
            nav.get_logger().info(f'{goal} is satisfied, dropping it from the mission')

        raise_errands(nav, kb, errands, satisfied)

        goal, eta = final_phase(nav)
        elapsed = nav.get_clock().now().nanoseconds / 1e9
        if goal in satisfied:
            if met is None:
                met = elapsed
                nav.get_logger().info(f'{goal} satisfied at t={met:.1f} s')
            if elapsed >= eta:
                nav.get_logger().info(f'reporting at t={elapsed:.1f} s')
                report(nav, kb, frame_id, waypoints['front_door'], goal)
                return

    nav.get_logger().info(f'reached the {limit} inspection limit, stopping')


def main(args=None):
    rclpy.init(args=args)

    share = get_package_share_directory('goal_awareness_scenario')
    parser = argparse.ArgumentParser()
    parser.add_argument('--waypoints', default=os.path.join(share, 'config', 'waypoints.yaml'))
    parser.add_argument('--max-inspections', type=int, default=12,
                        help='give up after this many inspections if the goal is never met')
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
    next_station = nav.create_client(NextStation, NEXT_STATION_SERVICE)
    kb = {query: nav.create_client(SelectQuery, QUERY_SERVICE + query) for query in QUERIES}
    publisher = nav.create_publisher(GoalSet, MISSION_TOPIC, LATCHED)

    # Before the Nav2 wait, so the awareness manager has the mission
    # before it is asked to rank anything.
    publish_mission(nav, publisher, {})

    nav.get_logger().info('waiting for Nav2')
    nav.waitUntilNav2Active(localizer='map_server')

    try:
        run(nav, inspector, next_station, kb, publisher, waypoints,
            options.max_inspections)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        nav.destroy_node()
        rclpy.try_shutdown()
