# Exercise 2: Knowledge Management Under Uncertainty

In Exercise 1, the robot used an OWL ontology and a symbolic reasoner to infer the type of room from the objects it observed. The reasoner could determine which room categories were logically consistent with the current observations.

However, symbolic reasoning alone has an important limitation. It does not represent uncertainty or remember how strongly previous observations support a particular hypothesis.

In this exercise, you will extend the symbolic reasoning system with two additional cognitive capabilities:

1. **Belief management**, allowing the robot to maintain confidence values for different room hypotheses.
2. **Memory decay**, allowing the robot to gradually forget outdated observations.

The objective is to demonstrate another key idea behind cognitive architectures:

> Symbolic reasoning determines which hypotheses are possible, while a belief system represents how strongly each hypothesis is supported.

## Knowledge Management Node

The symbolic reasoning node from Exercise 1 publishes the inferred room category on `/symbolic/room_inference`.

Complete `knowledge_management_node.py` to maintain and update the robot's belief state.

The node already stores one belief value for each room:

```python
room_beliefs = {
    "LivingRoom": 0.0,
    "Bedroom": 0.0,
    "Kitchen": 0.0,
    "DiningRoom": 0.0,
}
```

## 1. Update the Belief State

Whenever the symbolic reasoner infers a room category, increase the corresponding belief value.

For example:

```text
Symbolic inference:
    LivingRoom

Belief update:
    LivingRoom += 1
```

Complete the `update_beliefs()` function.

## 2. Forget Old Evidence

Without forgetting, beliefs continue accumulating evidence even after the robot moves to another room.

Implement a simple memory decay mechanism by multiplying every belief value by a constant factor at each cognitive cycle.

Example:

```python
DECAY = 0.8

for room in room_beliefs:
    room_beliefs[room] *= DECAY
```

Complete the `apply_decay()` function.

Experiment with different values of `DECAY`.

| Decay factor | Behaviour                                               |
| ------------ | ------------------------------------------------------- |
| 0.95         | Slow forgetting; stable beliefs                         |
| 0.80         | Balanced adaptation                                     |
| 0.50         | Rapid forgetting; reacts mainly to current observations |

## 3. Publish the Belief State

Instead of making a decision, publish the complete belief state so that it can be used by other cognitive components.

For simplicity, publish the belief dictionary as a JSON string on `/knowledge/beliefs`. Complete the `publish_beliefs()` function.

Example:

```text
{
    "LivingRoom": 1.80,
    "Kitchen": 0.30,
    "Bedroom": 0.00,
    "DiningRoom": 0.00
}
```

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

Launch the symbolic reasoning node:

```bash
source venv_cogarchs/bin/activate
ros2 run cognitive_nav symbolic_node
```

Then launch the knowledge management node:

```bash
source venv_cogarchs/bin/activate
ros2 run cognitive_nav knowledge_management_node
```

Move the robot through different rooms and observe how the belief values evolve as the robot explores the environment.

Experiment with different decay factors and compare how quickly the robot adapts after moving between rooms.

