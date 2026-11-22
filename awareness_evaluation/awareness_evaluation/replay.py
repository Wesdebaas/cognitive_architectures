"""Step through a finished run: a window with the time, goal and what happened; RViz shows each step's picture.

ros2 run awareness_evaluation replay <events file> <places.csv>
rviz2 -d awareness_evaluation/view.rviz
"""

import signal
import sys

import rclpy
from python_qt_binding.QtCore import Qt
from python_qt_binding.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget
from rclpy.qos import DurabilityPolicy, QoSProfile
from visualization_msgs.msg import MarkerArray

from .picture import TOPIC, picture, read_places
from .steps import read, steps


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
    slider = QSlider(Qt.Horizontal)
    slider.setRange(0, len(run) - 1)
    back, forward = QPushButton('◀'), QPushButton('▶')
    back.clicked.connect(lambda: slider.setValue(slider.value() - 1))
    forward.clicked.connect(lambda: slider.setValue(slider.value() + 1))

    def show(number):
        step = run[number]
        header.setText(f"step {number} / {len(run) - 1}      t = {step['t']} s      goal: {step['goal'] or 'none'}")
        happened.setText(step['happened'])
        publisher.publish(picture(places, step))

    slider.valueChanged.connect(show)
    row = QHBoxLayout()
    for widget in (back, slider, forward):
        row.addWidget(widget)
    layout = QVBoxLayout(window)
    layout.addWidget(header)
    layout.addWidget(happened)
    layout.addLayout(row)

    show(0)
    window.resize(700, 120)
    window.show()
    app.exec_()
    node.destroy_node()
    rclpy.try_shutdown()
