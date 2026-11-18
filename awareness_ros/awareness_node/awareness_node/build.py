"""Builds the awareness manager with its sources and the robot's travel time. No ROS: the AM node and the evaluation share it."""

import csv
import math
from functools import partial
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory

from . import conceptnet
from .awareness_manager import AwarenessManager


def travel_time(coordinates, speed, start, end):
    """Whole seconds in a straight line; None if either has no coordinates."""
    if start == end:
        return 0.0
    if start not in coordinates or end not in coordinates:
        return None
    return float(round(math.dist(coordinates[start], coordinates[end]) / speed))


def awareness_manager(kb, places, speed, claim='present'):
    """places: the scenario's places.csv; speed: metres per second."""
    share = Path(get_package_share_directory('awareness_node'))
    with open(share / 'config' / 'parameters.yaml') as f:
        parameters = yaml.safe_load(f)
    with open(places) as f:
        coordinates = {row['place']: (float(row['x']), float(row['y'])) for row in csv.DictReader(f)}
    association = partial(conceptnet.located_at, path=share / 'data' / conceptnet.FILE)
    return AwarenessManager(kb, association, claim, partial(travel_time, coordinates, speed), parameters)
