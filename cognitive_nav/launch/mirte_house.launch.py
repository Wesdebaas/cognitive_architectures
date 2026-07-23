# Copyright 2025 Gustavo Rezende Silva
# Modified 2026 Esther Aguado
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import IncludeLaunchDescription, ExecuteProcess, TimerAction
from launch_ros.actions import Node
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_xml.launch_description_sources import XMLLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
  # Use simulation time
  world = LaunchConfiguration('world')

  headless_arg = DeclareLaunchArgument(
    'headless',
    default_value='False',
    description='headless simulation'
  )

  use_sim_time_arg = DeclareLaunchArgument(
    'use_sim_time',
    default_value='true',
    description='Use simulation (Gazebo) clock if true'
  )

  world_path = PathJoinSubstitution([
    FindPackageShare('aws_robomaker_small_house_world'),
    'worlds',
    'small_house.world'
  ])
  world_arg = DeclareLaunchArgument(
    'world',
    default_value=world_path,
    description='Gazebo world'
  )

  gz_sim = IncludeLaunchDescription(
    PythonLaunchDescriptionSource(
      PathJoinSubstitution([
        FindPackageShare('ros_gz_sim'),
        'launch',
        'gz_sim.launch.py',
      ])
    ),
    launch_arguments={'gz_args' : ['-r ', world, ' --verbose']}.items(),
  )

  pkg_mirte_gazebo = get_package_share_directory(
        'mirte_gazebo')
  spawn_mirte_master_path = os.path.join(
      pkg_mirte_gazebo,
      'launch',
      'spawn_mirte_master.launch.xml')
  
  spawn_mirte_master = IncludeLaunchDescription(
    XMLLaunchDescriptionSource(spawn_mirte_master_path),
  )

 # Move arm out of the camera field of view
  park_arm = TimerAction(
    period=11.0,  # wait for robot and controllers to start
    actions=[
        ExecuteProcess(
            cmd=[
                'ros2', 'topic', 'pub', '--once',
                '/mirte_master_arm_controller/joint_trajectory',
                'trajectory_msgs/msg/JointTrajectory',
                """
                joint_names:
                - shoulder_pan_joint
                - shoulder_lift_joint
                - elbow_joint
                - wrist_joint

                points:
                - positions: [0.0, 0.0, 0.0, 0.0]
                  time_from_start:
                    sec: 2
                """
            ],
            output='screen'
        )
    ]
  )

  twist_stamped = Node(
    package="twist_stamper",
    executable="twist_stamper",
    name="twist_stamper",
    output="screen",
    parameters=[{
        "use_sim_time": True,
    }],
    remappings=[
        ('cmd_vel_in', '/cmd_vel'),
        ('cmd_vel_out', '/mirte_base_controller/reference'),
    ]
  )

  yolo = IncludeLaunchDescription(
    PythonLaunchDescriptionSource(
        PathJoinSubstitution([
            FindPackageShare('yolo_bringup'),
            'launch',
            'yolo.launch.py',
        ])
    ),
    launch_arguments={
        'input_image_topic': '/rgbd_camera/image',
        'input_depth_topic': '/rgbd_camera/depth_image',
        'input_depth_info_topic': '/rgbd_camera/camera_info',
        'target_frame': 'camera_link',
        'use_3d': 'True',
        'use_tracking': 'True',
        'device': 'cpu',
    }.items(),
  )

  camera_info_bridge = Node(
    package='ros_gz_bridge',
    executable='parameter_bridge',
    name='camera_info_bridge',
    arguments=[
        '/rgbd_camera/camera_info@sensor_msgs/msg/CameraInfo@gz.msgs.CameraInfo'
    ],
    output='screen',
  )

  return LaunchDescription([
    headless_arg,
    use_sim_time_arg,
    world_arg,
    gz_sim,
    spawn_mirte_master,
    park_arm,
    twist_stamped,
    camera_info_bridge,
    yolo
  ])
