"""Select the ConceptNet edges we use from the full ConceptNet 5.7.0 dump. No ROS.

Reads the dump on stdin and writes one line per selected edge on stdout: relation, start, end, weight, dataset.
The dump is streamed, never stored: it is larger than the disk space we have.

Run:  curl -s https://s3.amazonaws.com/conceptnet/downloads/2019/edges/conceptnet-assertions-5.7.0.csv.gz | gunzip | python3 select_conceptnet.py > conceptnet-5.7.0-selected.tsv
"""

import json
import sys

RELATIONS = {'/r/AtLocation', '/r/CapableOf', '/r/HasA', '/r/PartOf', '/r/UsedFor'}
LANGUAGE = '/c/en/'


for line in sys.stdin:
    assertion, relation, start, end, info = line.rstrip('\n').split('\t')
    if relation in RELATIONS and start.startswith(LANGUAGE) and end.startswith(LANGUAGE):
        info = json.loads(info)
        print(relation, start, end, float(info['weight']), info['dataset'], sep='\t')
