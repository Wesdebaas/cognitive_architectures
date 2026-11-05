"""Draw the graphs for one goal with Graphviz, saved in the scenario folder as <goal>_1.pdf, <goal>_2.pdf, ... No ROS.

Yellow = ConceptNet word, blue = SOMA class, orange = given by the scenario, white = derived (belief or action).

Run:  python3 draw.py <scenario folder> <goal>
python3 draw.py ../../scenarios/breakfast set_table
"""

import subprocess
import sys
from pathlib import Path

import graph

scenario, goal = sys.argv[1], sys.argv[2]
am = graph.load_scenario(scenario).awareness_manager()
kinds = graph.kinds(am.knowledge)
for number, build in [(1, graph.graph_1), (2, graph.graph_2), (3, graph.graph_3), (4, graph.graph_4)]:
    nodes, edges = build(am, goal)
    soma_classes = {end for start, label, end in edges if label in ('a', 'subClassOf')}
    actions = {end for start, label, end in edges if label == 'observed by'}
    lines = ['digraph {', '  node [style=filled];']
    for node in sorted(nodes):
        name = f'{node}\\n({kinds[node]})' if node in kinds else node
        if ' @ ' in node:
            lines.append(f'  "{node}" [label="{node}\\n(belief)", fillcolor="white"];')
        elif node in actions:
            lines.append(f'  "{node}" [label="{node}\\n(action)", fillcolor="white"];')
        elif node.startswith('word:'):
            lines.append(f'  "{node}" [label="{name}", fillcolor="#F0E442"];')
        elif node in soma_classes:
            lines.append(f'  "{node}" [label="{name}", fillcolor="#56B4E9"];')
        else:
            lines.append(f'  "{node}" [label="{name}", fillcolor="#E69F00"];')
    for start, label, end in edges:
        both = ', dir=both' if label == 'word' else ''
        lines.append(f'  "{start}" -> "{end}" [label="{label}"{both}];')
    lines.append('}')
    subprocess.run(['dot', '-Tpdf', '-o', str(Path(scenario) / f'{goal}_{number}.pdf')], input='\n'.join(lines), text=True, check=True)
