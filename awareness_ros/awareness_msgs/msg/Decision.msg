# What the AM weighed at time t and what it chose. Stored in am:decisions.

uint32 number              # 1, 2, ... in order
float64 t                  # seconds on the run clock
string position            # where the robot was, e.g. dock
string goal                # the active goal, empty if none
string chosen_action       # e.g. inspect, empty for a wait
string chosen_target       # e.g. table_1, empty for a wait
Option[] options           # every action it could do
GoalWeight[] goal_weights  # every goal with weight
Staleness[] stalenesses    # E of every belief those goals need
