# Everything the awareness manager computed on one tick. Diagnostic only:

std_msgs/Header header
string mission                  # each goal and what it is worth right now
NamedValue[] epistemic_error    # per item type
NamedValue[] attention          # per item type
NamedValue[] priority           # per station
