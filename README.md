# cognitive_architectures

An awareness manager that decides what a household robot should look at next. MSc thesis, TU Delft.

## Layout

- `awareness_ros/`: the system: `awareness_node` (the AM), `awareness_kb`, `awareness_msgs`, `awareness_scenario`, `awareness_gazebo`
- `awareness_evaluation/`: the evaluation: runs the AM through a scenario without ROS nodes
- `awareness/`, `awareness_replay/`: the old testbed and its viewer
- `workspace.repos`: pinned third-party sources

The earlier Gazebo system is kept at tag `gazebo-proof-of-concept`.

## Architecture

![The run without Gazebo](docs/architecture/ros_architecture.png)

The run without Gazebo: six ROS nodes; the AM decides, the stand-in executor carries out its looks.

![Inside the AM node](docs/architecture/ros_architecture_am_zoomed.png)

Inside the AM node: the manager's parts compute P = Σ E·A·weight and choose the look with the highest U = P / C; they share state only through the KB.

## Setup

Ubuntu 24.04, ROS 2 Jazzy.

```bash
mkdir -p ~/ros2_ws/src && cd ~/ros2_ws/src
git clone git@github.com:Wesdebaas/cognitive_architectures.git
cd ~/ros2_ws
vcs import src < src/cognitive_architectures/workspace.repos

python3 -m venv --system-site-packages venv_cogarchs
source venv_cogarchs/bin/activate
pip install -r src/cognitive_architectures/requirements.txt

rosdep install -r --from-paths src -y --ignore-src --skip-keys \
  "python3-pyoxigraph-pip python3-reasonable-pip python3-oxrdflib-pip python3-opentelemetry-api-pip python3-opentelemetry-sdk-pip"
python3 -m colcon build --symlink-install
source install/setup.bash
```

`--skip-keys` skips packages that `requirements.txt` already installs in the venv

## Run

From `src/cognitive_architectures`:

```bash
ros2 launch awareness_scenario run.launch.py scenario:=kitchen   # six ROS nodes, 10x real time
ros2 launch awareness_gazebo run.launch.py                       # mirte drives to the kitchen's places in the AWS house
```

In Gazebo only the robot is simulated: the items are kept by the world node, as in the run without Gazebo, and are not
drawn. Only the kitchen scenario has places in the AWS house.

Work in progress, the evaluation, moving from the old testbed to `awareness_evaluation` (the AM on LocalKB, no ROS nodes):

```bash
ros2 run awareness_evaluation simulate awareness_ros/awareness_scenario/kitchen/day kitchen.log
python3 awareness/testbed/run.py awareness/scenarios/household awareness/scenarios/household/worlds/day
python3 awareness/testbed/regression.py
ros2 launch awareness/testbed/visualization/replay.launch.py scenario:=household run:=household_day
```

Knowledge base:

```bash
ros2 triplestar bringup launch awareness_kb
ros2 triplestar query call count_triples 
```

## SOMA

`soma-home-2.1.0.ttl` is SOMA-HOME merged with its imports into one Turtle file, made with the ontology tool [ROBOT](https://robot.obolibrary.org):

```bash
java -jar ~/tools/robot/robot.jar merge \
  --catalog ~/ros2_ws/src/soma/owl/catalog-v001.xml \
  --input   ~/ros2_ws/src/soma/owl/SOMA-HOME.owl \
  convert --format ttl \
  --output  ~/ros2_ws/src/cognitive_architectures/awareness_ros/awareness_kb/preload/soma-home-2.1.0.ttl
```
