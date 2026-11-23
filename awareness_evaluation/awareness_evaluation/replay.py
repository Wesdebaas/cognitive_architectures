"""Step through a finished run: a window with the time, goal, what happened, the items, why the robot chose its place
and how that place's P is made; RViz shows each step's picture.

ros2 run awareness_evaluation replay <condition or folder> [policy]
ros2 run awareness_evaluation replay <events file> <places.csv>
A condition is a folder of the evaluation, e.g. votes_960_2; the policy defaults to awareness_manager. Starts RViz too.
"""

import signal
import subprocess
import sys
from pathlib import Path

import rclpy
from python_qt_binding.QtCore import Qt, QTimer
from python_qt_binding.QtWidgets import (QApplication, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSlider, QTableWidget,
                                         QTableWidgetItem, QVBoxLayout, QWidget)
from rclpy.qos import DurabilityPolicy, QoSProfile
from visualization_msgs.msg import MarkerArray

from .paths import VIEW, condition
from .picture import TOPIC, picture, read_places
from .simulate import POLICIES
from .steps import read, steps

ITEM_COLUMNS = ['Item', 'Needed', 'Really at', 'Looks say', 'Last seen', '']
RANKING_COLUMNS = ['Place', 'P', 'C (s)', 'U', '']
BELIEF_COLUMNS = ['Item', 'E', 'A', 'Finds', 'Weight', 'E·A·weight']


def item_rows(step):
    """Per item: whether the goal needs it, where it really is, where the looks say, where and when last seen, and
    whether the looks are correct, wrong or say nothing."""
    rows = []
    for item in sorted(step['really'].keys() | step['says'].keys()):
        really, says = step['really'].get(item, '—'), step['says'].get(item)
        place, t = step['seen'].get(item, (None, None))
        state = 'unknown' if says is None else 'correct' if says == really else 'wrong'
        rows.append([item, '●' if item in step['needs'] else '', really, says or '—',
                     f'{place} at {t} s' if place else '—', state])
    return rows


def ranking_rows(step, threshold):
    """Every option of the last decision, in the AM's order: P >= threshold and reachable by highest U, then the rest by
    highest P; ties by name."""
    decision = step['decision']
    if decision is None:
        return []

    def considered(option):
        return option['priority'] >= threshold and option['reachable']

    rows = []
    for option in sorted(decision['options'], key=lambda o: (not considered(o),
                                                                -(o['utility'] if considered(o) else o['priority']),
                                                                o['target'])):
        if option['target'] == decision['chosen_target']:
            mark = 'chosen' if step['t'] == decision['t'] else 'driving there' if step['chosen'] else ''
        else:
            mark = '' if considered(option) else 'unreachable' if not option['reachable'] else 'below threshold'
        rows.append([option['target'], f"{option['priority']:.3f}", f"{option['cost']:.0f}",
                     f"{option['utility']:.4f}", mark])
    return rows


def belief_rows(step, place):
    """Every belief at the place that a weighted goal needs, at the last decision: E and the goal weights from the
    decision, A and finds from the last beliefs before it. The last column sums to the place's P."""
    decision, beliefs = step['decision'], step['beliefs']
    if decision is None or beliefs is None:
        return []
    weights = {weight['goal']: weight['value'] for weight in decision['goal_weights']}
    found = {(belief['item'], belief['target']): belief for belief in beliefs['beliefs']}
    rows = []
    for staleness in decision['stalenesses']:
        if staleness['target'] != place:
            continue
        belief = found[(staleness['item'], place)]
        e, a = staleness['value'], belief['relevance']
        weight = sum(weights.get(goal, 0.0) for goal in belief['needed_for'])
        rows.append([staleness['item'], f'{e:.3f}', f'{a:.3f}', str(belief['finds']), f'{weight:g}', f'{e * a * weight:.3f}'])
    return rows


def table(columns):
    widget = QTableWidget(0, len(columns))
    widget.setHorizontalHeaderLabels(columns)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    widget.verticalHeader().hide()
    widget.setEditTriggers(QTableWidget.NoEditTriggers)
    return widget


def fill(widget, rows):
    widget.setRowCount(len(rows))
    for row, cells in enumerate(rows):
        for column, cell in enumerate(cells):
            widget.setItem(row, column, QTableWidgetItem(cell))


def files(args):
    """(events file, places.csv) from the command line."""
    if len(args) == 2 and Path(args[0]).is_file():
        return Path(args[0]), Path(args[1])
    folder = condition(args[0])
    policy = args[1] if len(args) > 1 else POLICIES[0]
    return folder / f'{policy}.events.jsonl', folder / 'places.csv'


def main():
    events_file, places_file = files(sys.argv[1:])
    events = read(events_file)
    run, places, threshold = steps(events), read_places(places_file), events[0]['threshold']
    rviz = subprocess.Popen(['rviz2', '-d', str(VIEW)])
    rclpy.init()
    node = rclpy.create_node('replay')
    # Transient local: RViz gets the current picture even if it starts later.
    publisher = node.create_publisher(MarkerArray, TOPIC, QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))

    app = QApplication(sys.argv[:1])
    # Ctrl-C, kill and timeout close the window, and so RViz. Python handles a signal only when it runs, so a timer
    # lets it run every 0.2 s.
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda *_: app.quit())
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(200)
    window = QWidget()
    window.setWindowTitle(f"replay: {events_file.parent.name}, {events[0]['policy']}")
    header, happened, decided, explained = QLabel(), QLabel(), QLabel(), QLabel()
    items, ranking, beliefs = table(ITEM_COLUMNS), table(RANKING_COLUMNS), table(BELIEF_COLUMNS)
    slider = QSlider(Qt.Horizontal)
    slider.setRange(0, len(run) - 1)
    back, forward = QPushButton('◀'), QPushButton('▶')
    back.clicked.connect(lambda: slider.setValue(slider.value() - 1))
    forward.clicked.connect(lambda: slider.setValue(slider.value() + 1))

    def explain(place):
        """Fill Beliefs for one place of the current step's ranking."""
        step = run[slider.value()]
        rows = belief_rows(step, place)
        explained.setText(f"Beliefs at {place}, P = {sum(float(cells[-1]) for cells in rows):.3f}" if place else '')
        fill(beliefs, rows)

    def show(number):
        step = run[number]
        header.setText(f"step {number} / {len(run) - 1}      t = {step['t']} s      goal: {step['goal'] or 'none'}")
        happened.setText(step['happened'])
        fill(items, item_rows(step))
        fill(ranking, ranking_rows(step, threshold))
        decision = step['decision']
        decided.setText('no decision yet' if decision is None else
                        f"decided at t = {decision['t']} s: {decision['chosen_target'] or 'wait'}")
        explain(ranking.item(0, 0).text() if ranking.rowCount() else None)
        publisher.publish(picture(places, step))

    slider.valueChanged.connect(show)
    ranking.cellClicked.connect(lambda row, column: explain(ranking.item(row, 0).text()))
    row = QHBoxLayout()
    for widget in (back, slider, forward):
        row.addWidget(widget)
    layout = QVBoxLayout(window)
    layout.addWidget(header)
    layout.addWidget(happened)
    layout.addLayout(row)
    tables, right = QHBoxLayout(), QVBoxLayout()
    right.addWidget(decided)
    right.addWidget(ranking)
    right.addWidget(explained)
    right.addWidget(beliefs)
    tables.addWidget(items)
    tables.addLayout(right)
    layout.addLayout(tables)

    show(0)
    window.resize(1200, 800)
    window.show()
    app.exec_()
    rviz.terminate()
    rviz.wait()
    node.destroy_node()
    rclpy.try_shutdown()
