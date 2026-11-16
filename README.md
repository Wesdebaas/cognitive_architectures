# cognitive_architectures

An awareness manager that decides what a household robot should look at next. MSc thesis, TU Delft.

## Layout

- `awareness/`: the awareness manager and a testbed that runs it without ROS
- `awareness_replay/`: rqt panel to step through a testbed run
- `awareness_ros/awareness_kb/`: TriplestarKB bringup with the household knowledge
- `workspace.repos`: pinned third-party sources

The earlier Gazebo system is kept at tag `gazebo-proof-of-concept`.

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
  --output  ~/ros2_ws/src/cognitive_architectures/awareness/sources/soma-home-2.1.0.ttl
```
