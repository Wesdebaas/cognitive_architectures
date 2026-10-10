# cognitive_architectures

Intro

## Overview

Goal of repo

## Repository layout

Packages and descriptions

## Prerequisites

Ubuntu 24.04.4 LTS
ROS Jazzy

## Third-party dependencies

See [`workspace.repos`](workspace.repos) for the pinned versions.

## Reconstructing the workspace on a new machine

```bash
# 1. Create the workspace and clone this repo into src/
mkdir -p ~/ros2_ws/src && cd ~/ros2_ws/src
git clone git@github.com:Wesdebaas/cognitive_architectures.git

# 2. Import all pinned third-party sources listed in workspace.repos
cd ~/ros2_ws
vcs import src < src/cognitive_architectures/workspace.repos

# 3. Install system/ROS dependencies
rosdep install --from-paths src -y --ignore-src

# 4. Build
colcon build
source install/setup.bash
```

## Python virtual environment

TriplestarKB and YOLO perception need Python packages that
are **not** available from apt (`pydantic>=2`, `pyoxigraph`, `reasonable`,
and the CPU build of `torch`/`ultralytics`). They live in a virtual environment, `venv_cogarchs`, created with `--system-site-packages` so the ROS packages remain importable.

```bash
source ~/ros2_ws/venv_cogarchs/bin/activate
```

## Running

Each terminal first sources the workspace (`source ~/ros2_ws/install/setup.bash`, already in `~/.bashrc` here).

**Terminal 1 — simulation + perception** (Gazebo, the robot, and the YOLO
pipeline):

```bash
ros2 launch cognitive_nav mirte_house.launch.py
```

Control-C sometimes leaves a gazebo server running. Find/kill it with:

```bash
pgrep -af "gz sim" ; pkill -9 -f "gz sim"
```

**Terminal 2 — knowledge base** (TriplestarKB with the room-recognition config):

Wait until YOLO is publishing before starting the KB, otherwise the KB's 2 s
message-type autodetect times out and silently drops the detection subscriber.

```bash
ros2 launch room_recognition room_recognition_triplestar.launch.xml
```


**Terminal 3 — belief node** (polls the KB and maintains room beliefs):

```bash
ros2 run cognitive_nav knowledge_management_node --ros-args -p use_sim_time:=true
```


**Terminal 4 — teleop** (optional):

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

############ Scenario 2

Uses its own world and robot description to decrease computational load of simulation, both in `goal_awareness_scenario`:

- `worlds/scenario_house.world` — `max_step_size` 0.005 -> 0.01
- `urdf/scenario_mirte_master.xacro` — depth camera 60 Hz -> 5 Hz

Together these take the real-time factor from ~0.65 to >0.95. Physics was 60% of Gazebo's single-threaded loop.

**Terminal 1 — simulation:**

```bash
ros2 launch cognitive_nav mirte_house.launch.py \
  world:=$(ros2 pkg prefix goal_awareness_scenario)/share/goal_awareness_scenario/worlds/scenario_house.world \
  robot_xacro_path:=$(ros2 pkg prefix goal_awareness_scenario)/share/goal_awareness_scenario/urdf/scenario_mirte_master.xacro
```

**Terminal 2 — navigation:**

```bash
ros2 launch goal_awareness_scenario navigation.launch.py
```

**Terminal 3 — travel time measurement** (drives every ordered pair of stations, 3 samples each):

```bash
ros2 run goal_awareness_scenario travel_time_tour --ros-args -p use_sim_time:=true
```

`use_sim_time` is required, durations are read off the simulation clock. Every leg is appended to `goal_awareness_scenario/results/travel_times.csv` and saved to disk immediately, so if anything crashes you rerun the identical command and it resumes from what is already in the file. Options: `--repeats`, `--output`, `--waypoints`,
`--max-legs`.


Command to generate turtle file from SOMA owl files
```bash
java -jar ~/tools/robot/robot.jar merge \
  --catalog ~/ros2_ws/src/soma/owl/catalog-v001.xml \
  --input   ~/ros2_ws/src/soma/owl/SOMA-HOME.owl \
  convert --format ttl \
  --output  ~/ros2_ws/src/cognitive_architectures/scenario_independent_evaluation/sources/soma-home-2.1.0.ttl
```