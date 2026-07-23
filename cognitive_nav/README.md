# Cognitive architectures introduction

In session, we will build a simple cognitive system for a robot operating inside a house. The robot perceives objects using YOLO and acts based on its understanding of the room it is currently observing. The cognitive pipeline is organized as follows:

* **Perception:** YOLO detects objects in the environment.
* **Representation:** Detected objects are inserted into an OWL ontology.
* **Reasoning:** An OWL reasoner infers the type of room from the observed objects.
* **Action:** The robot executes a simple room-dependent action.

## Install

Install all the required dependencies by running:

```bash
chmod +x install.sh
./install.sh
```

The script adds the repositories required for the cognitive architecture tutorial to the ROS 2 workspace created during the previous ROS 2 session.

If you do **NOT** already have the simulator installed, also run:

```bash
wget https://raw.githubusercontent.com/IntelligentRoboticsLabs/docker_infrastructure/main/docker/installation_scripts/simulator.sh
chmod +x simulator.sh
./simulator.sh
```

## Tutorial


The tutorial consists of three guided exercises that progressively build a simple cognitive architecture:

- [Exercise 1: Symbolic Reasoning](https://github.com/estherag/intro_cognitive_architectures/blob/main/exercises/exercise1.md)
- [Exercise 2: Knowledge Management Under Uncertainty](https://github.com/estherag/intro_cognitive_architectures/blob/main/exercises/exercise2.md)
- [Exercise 3: Goal Management and Decision Making](https://github.com/estherag/intro_cognitive_architectures/blob/main/exercises/exercise3.md)

## Solutions

Reference implementations for all exercises are available in the [`solutions`](https://github.com/estherag/intro_cognitive_architectures/tree/main/solutions) directory.

## Setup

## Test setup

Start the simulated house environment:

```bash
source venv_cogarchs/bin/activate
ros2 launch cognitive_nav mirte_house.launch.py
```

This will launch the robot and the simulated environment containing different rooms and objects.

Use keyboard teleoperation to explore the environment:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

Navigate through different rooms and observe how the inferred room type changes as different objects become visible.

To inspect the raw detections produced by the perception system:

```bash
ros2 topic echo /yolo/detections_3d
```

You may also visualize the annotated camera image:

```bash
ros2 run rqt_image_view rqt_image_view /yolo/dbg_image
```

Compare the detected objects with the room classification reported by the cognitive node.

## Troubleshooting: Arm in the camera field of view

If the arm does not move out of the camera field of view during launch, YOLO detections may be degraded because the robot sees its own arm instead of the environment. You can manually move the arm to a neutral position using:

```bash
ros2 topic pub --once \
/mirte_master_arm_controller/joint_trajectory \
trajectory_msgs/msg/JointTrajectory "
joint_names:
- shoulder_pan_joint
- shoulder_lift_joint
- elbow_joint
- wrist_joint

points:
- positions: [0.0, 0.0, 0.0, 0.0]
  time_from_start:
    sec: 2
"
```

## Troubleshooting: YOLO Stuck During Startup

If the launch process stops after:

```text
[yolo_node] Activating...
```

and no detections are published, the YOLO model file may be corrupted.

Activate the Python environment and try loading the model manually:

```bash
source venv_cogarchs/bin/activate

python - <<EOF
from ultralytics import YOLO
YOLO("yolov8m.pt")
print("MODEL OK")
EOF
```

If the model is installed correctly, the command should finish with:

```text
MODEL OK
```

If not found, ultralytics will automatically download a copy of the model.
