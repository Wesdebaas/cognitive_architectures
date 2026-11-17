# That an item has a claim at a target, with its A and how A was derived.

string item          # e.g. cup_1
string claim         # e.g. present
string target        # e.g. cupboard_1
float64 relevance    # A
float64 votes        # w
string[] votes_from  # the classes the votes came from, as IRIs
float64 discount
uint32 finds         # how often the item was found at the target
Edge[] edges         # the association edges behind w
string[] needed_for  # the goals that need it
