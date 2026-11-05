"""Write a rosbag that RViz can replay, and the values an rqt panel shows next to it. Needs ROS sourced; the awareness
manager and testbed do not.

Each message on /awareness/view is one complete picture, as a MarkerArray. Positions are in metres, in frame map, as in
the scenario's places.csv. Next to the bag folder, <bag folder>.steps.json holds one entry per message: its exact time in
the bag, and what the panel shows at that step. The scenario needs a places.csv, because that is what draws the map.

Run:  python3 events_to_bag.py <scenario folder> <events file> <bag folder>
python3 events_to_bag.py ../../scenarios/household ../runs/household_day.events.jsonl ../runs/household_day_bag
"""

import csv
import json
import shutil
import sys
from pathlib import Path

import rosbag2_py
import yaml
from geometry_msgs.msg import Point
from rclpy.serialization import serialize_message
from visualization_msgs.msg import Marker, MarkerArray

TOPIC = '/awareness/view'

# Size of a place's box in metres. Chosen: narrower than the 1 m between the closest places.
BOX_X, BOX_Y, BOX_Z = 0.8, 0.5, 0.02

# Grey of a place's box: P at or above the threshold, P below it, and no P. Chosen: brightness differs under colour blindness,
# and the P on the box repeats the distinction against the threshold in the panel.
ABOVE_GREY, BELOW_GREY, NO_P_GREY = 0.6, 0.27, 0.45

# Height of a label's letters in metres, and how far above the box's centre it is drawn. Chosen: by looking at it in RViz.
LABEL_SIZE, LABEL_OFFSET = 0.13, 0.09

# Height of the letters of a place's P in metres, and how far below the box's centre it is drawn. Chosen: by looking at it in RViz.
P_SIZE, P_OFFSET = 0.11, 0.1

# Diameter of the robot's marker in metres, and how far above its place it is drawn, so that it does not hide the label.
# Chosen: by looking at it in RViz.
ROBOT_SIZE, ROBOT_OFFSET = 0.3, 0.4

# Thickness of the arrow to the chosen place in metres: shaft, head, and length of the head. Chosen: by looking at it in RViz.
ARROW_SHAFT, ARROW_HEAD, ARROW_HEAD_LENGTH = 0.05, 0.16, 0.22

# Height of an item name's letters in metres, and the distance between names stacked at one place.
# Chosen: by looking at it in RViz.
ITEM_SIZE, ITEM_GAP = 0.13, 0.17

# How far from its place the first name is: where an item really is goes below the place, where the robot last saw it above
# the place and the robot's marker. Chosen: by looking at it in RViz.
TRUE_OFFSET, KNOWN_OFFSET = -0.38, 0.68

# The colours of those names. Chosen: orange and sky blue differ under colour blindness, and position repeats the distinction.
TRUE_COLOUR, KNOWN_COLOUR = (0.9, 0.62, 0.0), (0.35, 0.7, 0.9)

# A bag's times start at this many seconds, so that no message is stamped 0.
FIRST_STAMP = 1

# Seconds between two messages whose events happened at the same time, because every message needs its own time.
SAME_TIME_GAP = 0.001


def read_places(scenario):
    """{place: (x, y)} from the scenario's places.csv."""
    with open(scenario / 'places.csv') as f:
        return {row['place']: (float(row['x']), float(row['y'])) for row in csv.DictReader(f)}


def read_events(file):
    """Every event of a run, in the order they happened."""
    with open(file) as f:
        return [json.loads(line) for line in f]


def read_settings(scenario):
    """The scenario's testbed settings, which say how to show time as a clock."""
    with open(scenario / 'testbed.yaml') as f:
        return yaml.safe_load(f)


def clock(t, settings):
    """The time of day at t seconds, as HH:MM."""
    hours, minutes = settings['day_start'].split(':')
    total = int(hours) * 60 + int(minutes) + int(t * 60 / settings['seconds_per_day_hour'])
    return f'{total // 60:02d}:{total % 60:02d}'


def build_steps(events):
    """[{t, event, robot, chosen, decided, goal, arrived, items, known, last_seen, threshold, options, computed}]: one step for
    the start, each goal arrival, each telling, each item move, each finished look, and each decision made at a time when
    nothing else happened; any other decision joins the step before it. Each step holds what happened, and the state after it: where the
    robot is, the action it chose, whether it decided at this step, the active goal, a goal that arrived but is unknown to the
    robot, where every item really is, where the robot's last look at a place says it is, where and when each item was last
    seen, and P, C and U per action with the time they were computed. They are logged at decisions and goal arrivals; steps in
    between keep the last values.

    A look sees everything at its place: an item seen is known to be there, and an item known to be there but not seen no
    longer is, so the robot then does not know where it is."""
    steps = []
    robot, chosen, goal, items, known, last_seen = None, None, None, {}, {}, {}
    threshold, options, computed = None, [], None
    for event in events:
        arrived = None
        if event.get('options'):
            options, computed = event['options'], event['t']
        if event['event'] == 'start':
            robot, items, threshold = event['position'], dict(event['locations']), event['threshold']
            happened = 'start'
        elif event['event'] == 'goal':
            goal = event['active']
            if not event['known']:
                arrived = event['goal']
            happened = f"goal arrives: {event['goal']}"
        elif event['event'] == 'told':
            happened = f"told: {event['file']}"
        elif event['event'] == 'move':
            if event['place']:
                items[event['item']] = event['place']
            else:
                items.pop(event['item'], None)
            happened = f"item moves: {event['item']} -> {event['place'] or 'no place'}"
        elif event['event'] == 'look':
            robot, chosen = event['target'], None
            known = {item: place for item, place in known.items() if place != robot}
            known.update({item: robot for item in event['seen']})
            last_seen.update({item: (robot, event['t']) for item in event['seen']})
            happened = f"look ends: {event['target']}"
        elif event['event'] == 'decide':
            chosen = event['chosen']
            happened = f"decides: {chosen[1] if chosen else 'wait'}"
            if steps and steps[-1]['t'] == event['t']:
                steps[-1].update(chosen=chosen, decided=True, options=options, computed=computed)
                steps[-1]['event'] += f'; {happened}'
                continue
        steps.append({'t': event['t'], 'event': happened, 'robot': robot, 'chosen': chosen,
                      'decided': event['event'] == 'decide', 'goal': goal, 'arrived': arrived, 'items': dict(items),
                      'known': dict(known), 'last_seen': dict(last_seen), 'threshold': threshold, 'options': options,
                      'computed': computed})
    return steps


def ranking(step):
    """The actions as decide ranks them: at or above the threshold first, each part by highest U, ties by type and target. The
    action the robot is doing says chosen if it decided at this step, and on its way if it decided earlier. Each row holds the
    beliefs its P sums over."""
    def order(option):
        unreachable = option['C'] is None
        return (option['P'] < step['threshold'], unreachable, 0 if unreachable else -option['P'] / option['C'],
                option['type'], option['target'])

    rows = []
    for option in sorted(step['options'], key=order):
        doing = [option['type'], option['target']] == step['chosen']
        rows.append({'action': f"{option['type']} {option['target']}", 'P': option['P'], 'C': option['C'], 'U': option['U'],
                     'above': option['P'] >= step['threshold'], 'beliefs': option['beliefs'],
                     'mark': ('chosen' if step['decided'] else 'on its way') if doing else ''})
    return rows


def item_rows(step):
    """Per item, at this step: where it really is, where the robot's looks say it is, and where and when it was last seen. An
    item differs if the looks say a place and it is somewhere else."""
    rows = []
    for item in sorted({*step['items'], *step['known'], *step['last_seen']}):
        really, says = step['items'].get(item), step['known'].get(item)
        seen_at, seen_t = step['last_seen'].get(item, (None, None))
        rows.append({'item': item, 'really': really, 'says': says, 'seen_at': seen_at, 'seen_t': seen_t,
                     'differs': says is not None and says != really})
    return rows


def stamps(steps):
    """The bag time of each step, in nanoseconds: its t, spread out slightly where steps share a t."""
    times, same_time, previous = [], 0, None
    for step in steps:
        same_time = same_time + 1 if step['t'] == previous else 0
        previous = step['t']
        times.append(int((FIRST_STAMP + step['t'] + same_time * SAME_TIME_GAP) * 1e9))
    return times


def panel_steps(steps, times, settings):
    """What the rqt panel needs per step: the message's exact bag time, and the values it shows."""
    return [{'stamp': stamp, 't': step['t'], 'clock': clock(step['t'], settings), 'event': step['event'],
             'goal': step['goal'], 'arrived': step['arrived'], 'threshold': step['threshold'],
             'computed': step['computed'], 'ranking': ranking(step), 'item_rows': item_rows(step)}
            for step, stamp in zip(steps, times)]


def new_marker(marker_id, marker_type, namespace):
    """A marker in frame map, facing up, opaque. RViz can switch each namespace on and off."""
    marker = Marker()
    marker.header.frame_id = 'map'
    marker.ns = namespace
    marker.id = marker_id
    marker.type = marker_type
    marker.action = Marker.ADD
    marker.pose.orientation.w = 1.0
    marker.color.a = 1.0
    return marker


def place_box(marker_id, x, y, grey):
    """A flat grey box at the place."""
    box = new_marker(marker_id, Marker.CUBE, 'house')
    box.pose.position.x, box.pose.position.y = x, y
    box.scale.x, box.scale.y, box.scale.z = BOX_X, BOX_Y, BOX_Z
    box.color.r = box.color.g = box.color.b = grey
    return box


def place_label(marker_id, name, x, y):
    """The place's name in white, on its box."""
    label = new_marker(marker_id, Marker.TEXT_VIEW_FACING, 'house')
    label.pose.position.x, label.pose.position.y = x, y + LABEL_OFFSET
    label.pose.position.z = 0.1
    label.scale.z = LABEL_SIZE
    label.color.r = label.color.g = label.color.b = 1.0
    label.text = name
    return label


def box_grey(p, threshold):
    """The grey of a box whose place has this P; None means it has no P."""
    if p is None:
        return NO_P_GREY
    return ABOVE_GREY if p >= threshold else BELOW_GREY


def priority_label(marker_id, p, x, y):
    """A place's P in white, on its box."""
    label = new_marker(marker_id, Marker.TEXT_VIEW_FACING, 'priority')
    label.pose.position.x, label.pose.position.y = x, y - P_OFFSET
    label.pose.position.z = 0.1
    label.scale.z = P_SIZE
    label.color.r = label.color.g = label.color.b = 1.0
    label.text = f'P={p:.4f}'
    return label


def robot_marker(marker_id, x, y):
    """A blue ball just above the place the robot is at."""
    robot = new_marker(marker_id, Marker.SPHERE, 'robot')
    robot.pose.position.x, robot.pose.position.y = x, y + ROBOT_OFFSET
    robot.scale.x = robot.scale.y = robot.scale.z = ROBOT_SIZE
    robot.color.r, robot.color.g, robot.color.b = 0.0, 0.45, 0.7
    return robot


def arrow_marker(marker_id, start, end):
    """A blue arrow from one place to another, drawn at the height of the robot's marker."""
    arrow = new_marker(marker_id, Marker.ARROW, 'robot')
    arrow.points = [Point(x=start[0], y=start[1] + ROBOT_OFFSET), Point(x=end[0], y=end[1] + ROBOT_OFFSET)]
    arrow.scale.x, arrow.scale.y, arrow.scale.z = ARROW_SHAFT, ARROW_HEAD, ARROW_HEAD_LENGTH
    arrow.color.r, arrow.color.g, arrow.color.b = 0.0, 0.45, 0.7
    return arrow


def item_marker(marker_id, name, x, y, namespace, colour):
    """An item's name, at this position."""
    item = new_marker(marker_id, Marker.TEXT_VIEW_FACING, namespace)
    item.pose.position.x, item.pose.position.y = x, y
    item.pose.position.z = 0.1
    item.scale.z = ITEM_SIZE
    item.color.r, item.color.g, item.color.b = colour
    item.text = name
    return item


def item_markers(first_id, places, items, namespace, colour, offset):
    """Every item's name at its place, stacked away from the place where a place holds several."""
    markers, marker_id = [], first_id
    direction = 1 if offset > 0 else -1
    for place, (x, y) in places.items():
        here = sorted(item for item, location in items.items() if location == place)
        for row, item in enumerate(here):
            markers.append(item_marker(marker_id, item, x, y + offset + direction * row * ITEM_GAP, namespace, colour))
            marker_id += 1
    return markers


def picture_at(places, step):
    """One complete picture: clear whatever RViz is showing, then draw every place with its P, the robot, the arrow to the
    place it chose, where the items really are and where the robot's looks say they are. No arrow if it waits or stays where
    it is. A place shows the highest P of its actions; a place no action observes has no P."""
    clear = Marker()
    clear.action = Marker.DELETEALL
    picture = MarkerArray()
    picture.markers = [clear]
    priorities = {}
    for option in step['options']:
        priorities[option['target']] = max(option['P'], priorities.get(option['target'], 0))
    for index, (name, (x, y)) in enumerate(places.items()):
        picture.markers.append(place_box(2 * index, x, y, box_grey(priorities.get(name), step['threshold'])))
        picture.markers.append(place_label(2 * index + 1, name, x, y))
    picture.markers.append(robot_marker(2 * len(places), *places[step['robot']]))
    true_names = item_markers(2 * len(places) + 1, places, step['items'], 'world_truth', TRUE_COLOUR, TRUE_OFFSET)
    picture.markers.extend(true_names)
    picture.markers.extend(item_markers(2 * len(places) + 1 + len(true_names), places, step['known'], 'robot_knowledge',
                                        KNOWN_COLOUR, KNOWN_OFFSET))
    for index, (name, (x, y)) in enumerate(places.items()):
        if name in priorities:
            picture.markers.append(priority_label(index, priorities[name], x, y))
    if step['chosen'] and step['chosen'][1] != step['robot']:
        picture.markers.append(arrow_marker(len(picture.markers), places[step['robot']], places[step['chosen'][1]]))
    return picture


def write_bag(bag_folder, pictures):
    """Write [(time in nanoseconds, picture)] to a new bag, replacing an earlier bag in that folder."""
    if (bag_folder / 'metadata.yaml').exists():
        shutil.rmtree(bag_folder)
    writer = rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=str(bag_folder), storage_id='sqlite3'), rosbag2_py.ConverterOptions('', ''))
    writer.create_topic(rosbag2_py.TopicMetadata(id=0, name=TOPIC, type='visualization_msgs/msg/MarkerArray',
                                                 serialization_format='cdr'))
    for stamp, picture in pictures:
        writer.write(TOPIC, serialize_message(picture), stamp)


if __name__ == '__main__':
    scenario, events_file, bag_folder = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    places, settings = read_places(scenario), read_settings(scenario)
    steps = build_steps(read_events(events_file))
    times = stamps(steps)
    write_bag(bag_folder, list(zip(times, [picture_at(places, step) for step in steps])))
    steps_file = bag_folder.with_name(f'{bag_folder.name}.steps.json')
    steps_file.write_text(json.dumps(panel_steps(steps, times, settings)))
    print(f'{len(steps)} pictures: {bag_folder}')
    print(f'panel values: {steps_file}')
