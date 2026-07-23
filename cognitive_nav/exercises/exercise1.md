# Exercise 1: Symbolic Reasoning: Inferring the Current Room

In this exercise, you will build a simple symbolic reasoning system that allows a robot to infer the type of room it is currently observing. The robot receives object detections from a YOLO-based perception system and inserts them into an OWL ontology. A reasoner then uses the semantic relationships defined in the ontology to classify the current room.

The objective is to demonstrate one of the key ideas behind symbolic cognitive architectures:

> Knowledge is represented explicitly and separately from the control code.

The robot does **not** know which room it is in. Instead, it must infer the room type from the objects it observes.

For example:

```text
Observed objects:
    Sofa
    TV
    Chair

Inference:
    LivingRoom
```

## Complete the Ontology

Open `ontology.py`. The ontology already contains all room classes and object classes. Complete the classification rules by specifying the conditions that characterize each room.

For example, a living room may be defined as:

```python
LivingRoom.equivalent_to.append(
    Room
    & contains.some(Sofa)
    & contains.some(TV)
)
```

Similarly, define rules for:

* `Bedroom`
* `Kitchen`
* `DiningRoom`

Try to make your rules sufficiently discriminative to distinguish between different room types.

## Running the Exercise

Start the house environment as described in the README.

```bash
source venv_cogarchs/bin/activate
ros2 launch cognitive_nav mirte_house.launch.py
```

Use keyboard teleoperation to move the robot:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

Then launch the symbolic reasoning node:

```bash
source venv_cogarchs/bin/activate
ros2 run cognitive_nav symbolic_node
```

The node will subscribe to object detections, populate the ontology, execute the reasoner, and report the inferred room type.

Move the robot through different rooms and observe how the inferred room changes according to the ontology rules you defined.

> Is the robot reasoning about what it currently observes, or about everything it has ever observed? How might this affect its conclusions?
