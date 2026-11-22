"""One step of a run drawn for RViz, seen from above: the places, the robot, where the items really are and where the
robot's looks say they are. Time, goal and what happened are text, shown outside the picture.

ros2 run awareness_evaluation picture <events file> <places.csv> <step number>
"""

import csv
import sys

import rclpy
from geometry_msgs.msg import Point
from rclpy.qos import DurabilityPolicy, QoSProfile
from visualization_msgs.msg import Marker, MarkerArray

from .steps import read, steps

TOPIC = '/awareness/view'

# Size of a place's box in metres. Chosen: smaller than the 0.7 m between the closest places.
BOX_X, BOX_Y = 0.5, 0.3

# Height of letters in metres, and the distance between item names stacked at one place. Chosen: by looking at it.
TEXT, GAP = 0.09, 0.11

# Orange: where an item really is, below its place. Sky blue: where the robot's looks say it is, above its place, and the
# robot. Chosen: the two differ under colour blindness, and below / above repeats the difference.
REALLY, SAYS = (0.9, 0.62, 0.0), (0.35, 0.7, 0.9)


def read_places(file):
    """{place: (x, y)} from a scenario's places.csv."""
    with open(file) as f:
        return {row['place']: (float(row['x']), float(row['y'])) for row in csv.DictReader(f)}


def marker(kind, x, y, colour=(1.0, 1.0, 1.0)):
    """A marker at (x, y) in frame map; ids are given when the picture is complete."""
    m = Marker(type=kind, action=Marker.ADD)
    m.header.frame_id = 'map'
    m.pose.position.x, m.pose.position.y = x, y
    m.pose.orientation.w = 1.0
    m.color.r, m.color.g, m.color.b, m.color.a = *colour, 1.0
    return m


def text(words, x, y, colour=(1.0, 1.0, 1.0)):
    m = marker(Marker.TEXT_VIEW_FACING, x, y, colour)
    m.scale.z, m.text = TEXT, words
    return m


def picture(places, step):
    """The step as a MarkerArray: everything RViz showed before is cleared first."""
    markers = [Marker(action=Marker.DELETEALL)]
    for name, (x, y) in places.items():
        box = marker(Marker.CUBE, x, y, (0.45, 0.45, 0.45))
        box.scale.x, box.scale.y, box.scale.z = BOX_X, BOX_Y, 0.02
        markers += [box, text(name, x, y)]
    for items, colour, direction in [(step['really'], REALLY, -1), (step['says'], SAYS, 1)]:
        for place, (x, y) in places.items():
            here = sorted(item for item, at in items.items() if at == place)
            for row, item in enumerate(here):
                markers.append(text(item, x, y + direction * (BOX_Y / 2 + GAP * (row + 0.5)), colour))
    x, y = places[step['robot']]
    robot = marker(Marker.SPHERE, x - BOX_X / 2, y, SAYS)
    robot.scale.x = robot.scale.y = robot.scale.z = 0.15
    markers.append(robot)
    if step['chosen'] and step['chosen'] != step['robot']:
        arrow = marker(Marker.ARROW, 0.0, 0.0, SAYS)
        arrow.points = [Point(x=x - BOX_X / 2, y=y), Point(x=places[step['chosen']][0], y=places[step['chosen']][1])]
        arrow.scale.x, arrow.scale.y, arrow.scale.z = 0.03, 0.08, 0.12
        markers.append(arrow)
    for number, m in enumerate(markers):
        m.id = number
    return MarkerArray(markers=markers)


def main():
    events, places, number = sys.argv[1], read_places(sys.argv[2]), int(sys.argv[3])
    rclpy.init()
    node = rclpy.create_node('picture')
    # Transient local: RViz gets the picture even if it starts later.
    publisher = node.create_publisher(MarkerArray, TOPIC, QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    step = steps(read(events))[number]
    publisher.publish(picture(places, step))
    print(f"step {number}: t = {step['t']} s, {step['goal'] or 'no goal'}, {step['happened']}; Ctrl-C to stop")
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
