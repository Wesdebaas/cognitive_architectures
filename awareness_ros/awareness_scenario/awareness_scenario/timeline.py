"""What happens when in a run: where every item is, and the timetable of goals and knowledge, read from a scenario's
folder. No ROS: the nodes and the evaluation share it."""

import csv
from pathlib import Path

import pyoxigraph as ox
import yaml

AM = 'http://example.org/awareness-manager#'

# What comes first when several things fall on the same second, as in the testbed.
NIGHT, ASSERTION, GOAL, END = range(4)


def settings(folder):
    """The scenario's run.yaml."""
    with open(Path(folder).parent / 'run.yaml') as f:
        return yaml.safe_load(f)


class World:
    """Where every item is, moved as world_events.csv says; each night everything goes back to world.ttl."""

    def __init__(self, folder):
        folder, run = Path(folder), settings(folder)
        store = ox.Store()
        store.load(path=str(folder / 'world.ttl'), format=ox.RdfFormat.TURTLE)
        self.start = {row['item'].value.split('#')[-1]: row['place'].value.split('#')[-1]
                      for row in store.query(f'SELECT ?item ?place WHERE {{ ?item <{AM}isAt> ?place }}')}
        self.where = dict(self.start)
        with open(folder / 'world_events.csv') as f:
            moves = sorted((float(row['t']), row['item'], row['place']) for row in csv.DictReader(f))
        # Every change of the whole run, in time order: (t, item, place), place '' = at no place; item None = night,
        # when everything goes back to where world.ttl says and the next day's moves follow.
        day = 24 * run['seconds_per_day_hour']
        self.changes = []
        for number in range(run['days']):
            self.changes += [(number * day + t, item, place) for t, item, place in moves]
            if number < run['days'] - 1:
                self.changes.append((number * day + run['run_length'], None, None))
        self.changes.sort(key=lambda change: change[0])

    def advance(self, t):
        """Make every change due at t. Returns the moves: [(item, place)]."""
        moved = []
        while self.changes and self.changes[0][0] <= t:
            _, item, place = self.changes.pop(0)
            due = [(item, self.start.get(item, '')) for item in sorted(set(self.where) | set(self.start))] \
                if item is None else [(item, place)]
            for item, place in due:
                if self.move(item, place):
                    moved.append((item, place))
        return moved

    def move(self, item, place):
        """False if the item is already there."""
        if self.where.get(item, '') == place:
            return False
        if place:
            self.where[item] = place
        else:
            del self.where[item]
        return True

    def inspect(self, target):
        """The items at the target."""
        return sorted(item for item, place in self.where.items() if place == target)


def timetable(folder):
    """(arrivals, entries): every goal arrival [(t, goal)], and [(t, kind, value)] in the order they happen: goals
    every day, knowledge on the first day only, a night after every day but the last, and the end of the run."""
    folder, run = Path(folder), settings(folder)
    with open(folder / 'goal_events.csv') as f:
        goals = [(float(row['t']), row['goal']) for row in csv.DictReader(f)]
    with open(folder / 'knowledge_events.csv') as f:
        assertions = [(float(row['t']), row['file']) for row in csv.DictReader(f)]
    day, days = 24 * run['seconds_per_day_hour'], run['days']
    arrivals = [(number * day + t, goal) for number in range(days) for t, goal in goals]
    entries = sorted(
        [(t, GOAL, goal) for t, goal in arrivals]
        + [(t, ASSERTION, name) for t, name in assertions]
        + [(number * day + run['run_length'], NIGHT, None) for number in range(days - 1)]
        + [((days - 1) * day + run['run_length'], END, None)], key=lambda entry: entry[:2])
    return arrivals, entries
