# What one action observed at its target, as the awareness manager stores it in am:observations.

uint32 number      # observations are numbered 1, 2, ... in the order they were made
string action      # the action type, e.g. inspect
string target      # where it was done, e.g. table_1
string claim       # the claim it assessed, e.g. present
float64 t          # seconds on the run clock
bool complete      # true: every item at the target was assessed, so an item not reported has the claim false
Report[] reported  # the items it assessed
