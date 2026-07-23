# Exercise 3: Goal Management and Decision Making

In Exercises 1 and 2, the robot was capable to infer its current room using symbolic reasoning and to maintain beliefs about its location over time.

It can now answer the question:

> Where am I, and how strongly do I believe it?

The remaining component of many cognitive architectures is an **executive system**, responsible for selecting, monitoring and completing goals. In this exercise, you will implement a simple goal manager. The robot is given a sequence of symbolic goals:

```text
Go to the Kitchen.
Then go to the Bedroom.
```

The robot must use its belief state to determine when each goal has been achieved before moving on to the next one.

## Goal Manager

The Knowledge Management node from Exercise 2 publishes the current belief state on `/knowledge/beliefs`. Complete `goal_manager_node.py`.

The node already subscribes to the published beliefs. Your task is to implement a simple executive that monitors the current goal and decides when to activate the next one.

## 1. Define a Goal Sequence

Create a list describing the order in which the robot should visit rooms.

Example:

```python
GOALS = [
    "Kitchen",
    "Bedroom",
]
```

The robot should pursue one goal at a time.

## 2. Detect Goal Completion

At every cognitive cycle:

* Read the current belief state.
* Retrieve the current goal.
* Check whether its belief exceeds a threshold.

Example:

```python
GOAL_THRESHOLD = 1.5
```

If the threshold is reached:

* report that the goal has been achieved,
* activate the next goal.

Otherwise, continue pursuing the current goal.

When all goals have been completed, report that the mission has finished.

## 3. Report the Executive State

At each cognitive cycle, report:

* the current goal,
* the current belief values,
* whether the goal has been achieved.

## Running the Exercise

Start the house environment:

```bash
source venv_cogarchs/bin/activate
ros2 launch cognitive_nav mirte_house.launch.py
```

Use keyboard teleoperation to move the robot:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```


Launch all three nodes:

```bash
# Terminal 1
source venv_cogarchs/bin/activate
ros2 run cognitive_nav symbolic_node

# Terminal 2
source venv_cogarchs/bin/activate
ros2 run cognitive_nav knowledge_management_node

# Terminal 3
source venv_cogarchs/bin/activate
ros2 run cognitive_nav goal_manager_node
```

Navigate the robot through the house in the order defined by your goal sequence. Observe how the active goal changes as the robot moves between rooms.
