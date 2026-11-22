"""Step through a finished run: a window with the time, goal and what happened; RViz shows each step's picture.

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


def main():
    run, places = steps(read(sys.argv[1])), read_places(sys.argv[2])
    rclpy.init()
    node = rclpy.create_node('replay')
    # Transient local: RViz gets the current picture even if it starts later.
    publisher = node.create_publisher(MarkerArray, TOPIC, QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    signal.signal(signal.SIGINT, signal.SIG_DFL)   # Ctrl-C in the terminal closes the window

    app = QApplication(sys.argv[:1])
    window = QWidget()
    window.setWindowTitle('replay')
    header, happened = QLabel(), QLabel()
    items = QTableWidget(0, len(ITEM_COLUMNS))
    items.setHorizontalHeaderLabels(ITEM_COLUMNS)
    items.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    items.verticalHeader().hide()
    items.setEditTriggers(QTableWidget.NoEditTriggers)
    slider = QSlider(Qt.Horizontal)
    slider.setRange(0, len(run) - 1)
    back, forward = QPushButton('◀'), QPushButton('▶')
    back.clicked.connect(lambda: slider.setValue(slider.value() - 1))
    forward.clicked.connect(lambda: slider.setValue(slider.value() + 1))

    def show(number):
        step = run[number]
        header.setText(f"step {number} / {len(run) - 1}      t = {step['t']} s      goal: {step['goal'] or 'none'}")
        happened.setText(step['happened'])
        rows = item_rows(step)
        items.setRowCount(len(rows))
        for row, cells in enumerate(rows):
            for column, cell in enumerate(cells):
                items.setItem(row, column, QTableWidgetItem(cell))
        publisher.publish(picture(places, step))

    slider.valueChanged.connect(show)
    row = QHBoxLayout()
    for widget in (back, slider, forward):
        row.addWidget(widget)
    layout = QVBoxLayout(window)
    layout.addWidget(header)
    layout.addWidget(happened)
    layout.addLayout(row)
    layout.addWidget(items)

    show(0)
    window.resize(700, 400)
    window.show()
    app.exec_()
    node.destroy_node()
    rclpy.try_shutdown()
