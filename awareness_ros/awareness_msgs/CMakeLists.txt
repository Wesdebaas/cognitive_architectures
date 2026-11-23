cmake_minimum_required(VERSION 3.10)
project(awareness_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/ActiveGoal.msg"
  "msg/Assertion.msg"
  "msg/Assessment.msg"
  "msg/Belief.msg"
  "msg/Beliefs.msg"
  "msg/Decision.msg"
  "msg/Edge.msg"
  "msg/ExpectedGoal.msg"
  "msg/GoalWeight.msg"
  "msg/Observation.msg"
  "msg/Option.msg"
  "msg/Report.msg"
  "msg/Staleness.msg"
  "srv/AssertKnowledge.srv"
  "srv/ExpectGoal.srv"
  "srv/Inspect.srv"
  "srv/SetActiveGoal.srv"
  "action/Execute.action"
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
