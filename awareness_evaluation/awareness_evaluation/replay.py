"""Step through a finished run: a window with the time, goal, what happened, the items and why the robot chose its
place; RViz shows each step's picture.

ros2 run awareness_evaluation replay <events file> <places.csv>
rviz2 -d awareness_evaluation/view.rviz
"""

import signal
import sys

import rclpy
from python_qt_binding.QtCore import Qt
from python_qt_binding.QtWidgets import (QApplication, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSlider, QTableWidget,
                                         QTableWidgetItem, QVBoxLayout, QWidget)
from rclpy.qos import DurabilityPolicy, QoSProfile
from visualization_msgs.msg import MarkerArray

from .picture import TOPIC, picture, read_places
from .steps import read, steps

ITEM_COLUMNS = ['Item', 'Needed', 'Really at', 'Looks say', 'Last seen', '']
RANKING_COLUMNS = ['Place', 'P', 'C (s)', 'U', '']


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


def main():
    events = read(sys.argv[1])
    run, places, threshold = steps(events), read_places(sys.argv[2]), events[0]['threshold']
    rclpy.init()
    node = rclpy.create_node('replay')
    # Transient local: RViz gets the current picture even if it starts later.
    publisher = node.create_publisher(MarkerArray, TOPIC, QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    signal.signal(signal.SIGINT, signal.SIG_DFL)   # Ctrl-C in the terminal closes the window

    app = QApplication(sys.argv[:1])
    window = QWidget()
    window.setWindowTitle('replay')
    header, happened, decided = QLabel(), QLabel(), QLabel()
    items, ranking = table(ITEM_COLUMNS), table(RANKING_COLUMNS)
    slider = QSlider(Qt.Horizontal)
    slider.setRange(0, len(run) - 1)
    back, forward = QPushButton('◀'), QPushButton('▶')
    back.clicked.connect(lambda: slider.setValue(slider.value() - 1))
    forward.clicked.connect(lambda: slider.setValue(slider.value() + 1))

    def show(number):
        step = run[number]
        header.setText(f"step {number} / {len(run) - 1}      t = {step['t']} s      goal: {step['goal'] or 'none'}")
        happened.setText(step['happened'])
        fill(items, item_rows(step))
        fill(ranking, ranking_rows(step, threshold))
        decision = step['decision']
        decided.setText('no decision yet' if decision is None else
                        f"decided at t = {decision['t']} s: {decision['chosen_target'] or 'wait'}")
        publisher.publish(picture(places, step))

    slider.valueChanged.connect(show)
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
    tables.addWidget(items)
    tables.addLayout(right)
    layout.addLayout(tables)

    show(0)
    window.resize(1200, 600)
    window.show()
    app.exec_()
    node.destroy_node()
    rclpy.try_shutdown()
