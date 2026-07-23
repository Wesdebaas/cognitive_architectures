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

Maybe add venv step here or at run?


## Running

Commands to run simulations 

```bash
ros2 launch room_recognition room_recognition_triplestar.launch.xml
```

