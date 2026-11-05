"""An rqt panel to step through a recorded run: it moves the paused bag, so RViz draws that step, and shows the step's values.

The bag and <bag folder>.steps.json are written by testbed/visualization/events_to_bag.py.

Run:  ros2 launch replay.launch.py scenario:=<scenario> run:=<run>    (in testbed/visualization)
"""

import json
from pathlib import Path

import rclpy
from builtin_interfaces.msg import Time
from python_qt_binding.QtCore import Qt, QTimer
from python_qt_binding.QtWidgets import (QAbstractItemView, QFormLayout, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                                         QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from qt_gui.plugin import Plugin
from rosbag2_interfaces.srv import PlayNext, Seek

# How often the panel checks whether the bag player and RViz have started, in milliseconds.
PLAYER_CHECK = 500

# The topic RViz draws.
TOPIC = '/awareness/view'

# The columns of the three tables.
RANKING_COLUMNS = ['Action', 'P', 'C (s)', 'U', '']
BELIEF_COLUMNS = ['Item', 'Last observed at t', 'T (s)', 'E', 'A', 'E x A']
ITEM_COLUMNS = ['Item', 'Really at', "Robot's looks say", 'Last seen at', 'At t', '']

# Least width of each table and height of a table row, in pixels. Chosen: by looking at the panel, so that no column is cut off.
RANKING_WIDTH, BELIEF_WIDTH, ITEM_WIDTH, ROW_HEIGHT = 430, 560, 700, 26


def fit(table, width, rows):
    """Make a table at least this wide, and tall enough for this many rows and its header."""
    table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
    table.setMinimumWidth(width)
    table.setMinimumHeight((rows + 2) * ROW_HEIGHT)


def new_table(columns):
    """A read-only table with these columns, each as wide as its content."""
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.NoSelection)
    table.setFocusPolicy(Qt.NoFocus)
    return table


def set_row(table, index, cells, bold=False):
    """Fill one table row with these texts."""
    for column, text in enumerate(cells):
        item = QTableWidgetItem(text)
        font = item.font()
        font.setBold(bold)
        item.setFont(font)
        table.setItem(index, column, item)


def text(value):
    """A value as table text, a dash if there is none."""
    return '-' if value is None else str(value)


class Replay(Plugin):

    def __init__(self, context):
        super().__init__(context)
        self.setObjectName('Replay')
        bag_folder = Path(context.argv()[0])
        self.steps = json.loads(bag_folder.with_name(f'{bag_folder.name}.steps.json').read_text())
        self.node = context.node
        self.seek = context.node.create_client(Seek, '/rosbag2_player/seek')
        self.play_next = context.node.create_client(PlayNext, '/rosbag2_player/play_next')
        self.wanted = 0       # the step on screen in this panel
        self.sent = None      # the step last sent to the player
        self.sending = False  # a step is on its way to the player

        self.widget = QWidget()
        self.widget.setWindowTitle('Replay')
        context.add_widget(self.widget)
        self.build_panel()

        self.timer = QTimer()
        self.timer.timeout.connect(self.send)
        self.timer.start(PLAYER_CHECK)
        self.show(0)

    def build_panel(self):
        """The buttons and the values, with Qt's standard widgets."""
        self.back_button = QPushButton('Back')
        self.next_button = QPushButton('Next')
        self.step_box = QSpinBox()
        self.step_box.setRange(1, len(self.steps))
        self.step_box.setKeyboardTracking(False)
        self.back_button.clicked.connect(lambda: self.show(self.wanted - 1))
        self.next_button.clicked.connect(lambda: self.show(self.wanted + 1))
        self.step_box.valueChanged.connect(lambda value: self.show(value - 1))
        self.t_box = QSpinBox()
        self.t_box.setRange(0, self.steps[-1]['t'])
        self.t_box.setKeyboardTracking(False)
        self.t_box.setButtonSymbols(QSpinBox.NoButtons)
        self.t_box.valueChanged.connect(self.go_to_t)

        controls = QHBoxLayout()
        controls.addWidget(self.back_button)
        controls.addWidget(self.next_button)
        controls.addWidget(QLabel(f'Step (of {len(self.steps)}):'))
        controls.addWidget(self.step_box)
        controls.addWidget(QLabel('t (s), type to go there:'))
        controls.addWidget(self.t_box)
        controls.addStretch()

        self.clock_value, self.goal_value, self.arrived_value = QLabel(), QLabel(), QLabel()
        self.event_value, self.threshold_value, self.computed_value, self.player_value = QLabel(), QLabel(), QLabel(), QLabel()
        self.player_value.setWordWrap(True)
        values = QFormLayout()
        values.addRow('Clock:', self.clock_value)
        values.addRow('What happened:', self.event_value)
        values.addRow('Active goal:', self.goal_value)
        values.addRow('Arrived, unknown to the robot:', self.arrived_value)
        values.addRow('Threshold:', self.threshold_value)
        values.addRow('P, C, U computed at t (s):', self.computed_value)
        values.addRow('Bag player:', self.player_value)

        self.ranking_table = new_table(RANKING_COLUMNS)
        self.ranking_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ranking_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ranking_table.cellClicked.connect(lambda row, column: self.select_action(row))
        self.belief_table, self.item_table = new_table(BELIEF_COLUMNS), new_table(ITEM_COLUMNS)
        self.belief_title = QLabel()
        fit(self.ranking_table, RANKING_WIDTH, max(len(step['ranking']) for step in self.steps) + 1)
        fit(self.belief_table, BELIEF_WIDTH, max((len(row['beliefs']) for step in self.steps for row in step['ranking']), default=0) + 1)
        fit(self.item_table, ITEM_WIDTH, max(len(step['item_rows']) for step in self.steps))

        top_left = QVBoxLayout()
        top_left.addLayout(controls)
        top_left.addLayout(values)
        top_left.addStretch()
        top_right = QVBoxLayout()
        top_right.addWidget(self.belief_title)
        top_right.addWidget(self.belief_table)
        top_right.addStretch()
        bottom_left = QVBoxLayout()
        bottom_left.addWidget(QLabel('Ranking (click an action to see its beliefs)'))
        bottom_left.addWidget(self.ranking_table)
        bottom_right = QVBoxLayout()
        bottom_right.addWidget(QLabel('Items'))
        bottom_right.addWidget(self.item_table)

        layout = QGridLayout(self.widget)
        layout.addLayout(top_left, 0, 0)
        layout.addLayout(top_right, 0, 1)
        layout.addLayout(bottom_left, 1, 0)
        layout.addLayout(bottom_right, 1, 1)
        layout.setRowStretch(1, 1)
        layout.setColumnStretch(1, 1)

    def go_to_t(self, t):
        """Go to the first step at or after time t."""
        self.show(next(index for index, step in enumerate(self.steps) if step['t'] >= t))

    def show_ranking(self, ranking):
        """One table row per action, in the order of the ranking, with a row where the threshold falls. The row of the action
        the robot is doing is bold and says so, and shows its beliefs; if there is none, the top action does."""
        self.ranking_rows = []
        if ranking:
            self.ranking_rows = [row for row in ranking if row['above']] + [None] + [row for row in ranking if not row['above']]
        self.ranking_table.clearSpans()
        self.ranking_table.clearContents()
        self.ranking_table.setRowCount(len(self.ranking_rows))
        for index, row in enumerate(self.ranking_rows):
            if row is None:
                self.ranking_table.setSpan(index, 0, 1, len(RANKING_COLUMNS))
                item = QTableWidgetItem('below the threshold')
                item.setFlags(Qt.ItemIsEnabled)
                self.ranking_table.setItem(index, 0, item)
                continue
            set_row(self.ranking_table, index, [row['action'], f"{row['P']:.4f}", '-' if row['C'] is None else f"{row['C']:g}",
                                                '-' if row['U'] is None else f"{row['U']:.4f}", row['mark']], bool(row['mark']))
        actions = [index for index, row in enumerate(self.ranking_rows) if row]
        marked = [index for index in actions if self.ranking_rows[index]['mark']]
        self.belief_title.setText('Beliefs')
        self.belief_table.setRowCount(0)
        if actions:
            self.select_action((marked or actions)[0])

    def select_action(self, index):
        """Show the beliefs of the action in this row of the ranking: the sum that makes its P. The threshold row has none."""
        row = self.ranking_rows[index]
        if row is None:
            return
        self.ranking_table.selectRow(index)
        self.belief_title.setText(f"Beliefs of {row['action']}")
        self.belief_table.setRowCount(len(row['beliefs']) + 1)
        for number, belief in enumerate(row['beliefs']):
            set_row(self.belief_table, number, [belief['item'], text(belief['observed']), text(belief['T']), f"{belief['E']:.4f}",
                                                f"{belief['A']:.4f}", f"{belief['E'] * belief['A']:.4f}"])
        set_row(self.belief_table, len(row['beliefs']), ['P', '', '', '', '', f"{row['P']:.4f}"], True)

    def show_items(self, rows):
        """One table row per item: where it really is next to what the robot knows. A row that differs is bold and says so."""
        self.item_table.clearContents()
        self.item_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            set_row(self.item_table, index, [row['item'], text(row['really']), text(row['says']), text(row['seen_at']),
                                             text(row['seen_t']), 'differs' if row['differs'] else ''], row['differs'])

    def show(self, index):
        """Show this step's values, and ask the player for its picture."""
        self.wanted = max(0, min(len(self.steps) - 1, index))
        step = self.steps[self.wanted]
        self.step_box.blockSignals(True)
        self.step_box.setValue(self.wanted + 1)
        self.step_box.blockSignals(False)
        self.t_box.blockSignals(True)
        self.t_box.setValue(step['t'])
        self.t_box.blockSignals(False)
        self.back_button.setEnabled(self.wanted > 0)
        self.next_button.setEnabled(self.wanted < len(self.steps) - 1)
        self.clock_value.setText(step['clock'])
        self.event_value.setText(step['event'])
        self.goal_value.setText(step['goal'] or 'none')
        self.arrived_value.setText(step['arrived'] or '-')
        self.threshold_value.setText(str(step['threshold']))
        self.computed_value.setText('-' if step['computed'] is None else str(step['computed']))
        self.show_ranking(step['ranking'])
        self.show_items(step['item_rows'])
        self.send()

    def send(self):
        """Send the wanted step to the player, unless a step is still on its way; that one's answer sends the wanted step.

        Goes to the message's exact time, then plays that one message, so going back works just like going forward. Waits
        until RViz listens, because a picture published before that is lost.
        """
        if not rclpy.ok():   # rqt is shutting down
            self.timer.stop()
            return
        player_ready = self.seek.service_is_ready() and self.play_next.service_is_ready()
        rviz_ready = self.node.count_subscribers(TOPIC) > 0
        if not player_ready:
            self.player_value.setText('not found: start ros2 bag play <bag folder> --start-paused')
        elif not rviz_ready:
            self.player_value.setText('waiting for RViz')
        else:
            self.player_value.setText('running')
        if not (player_ready and rviz_ready):
            self.sent = None
            return
        if self.sending or self.sent == self.wanted:
            return
        self.sending, self.sent = True, self.wanted
        stamp = self.steps[self.sent]['stamp']
        request = Seek.Request(time=Time(sec=stamp // 10**9, nanosec=stamp % 10**9))
        self.seek.call_async(request).add_done_callback(self.seek_done)

    def seek_done(self, future):
        self.play_next.call_async(PlayNext.Request()).add_done_callback(self.play_done)

    def play_done(self, future):
        self.sending = False

    def shutdown_plugin(self):
        self.timer.stop()
