"""Plot a run log: P of every action, with the idle threshold. No ROS.

Run:  python3 plot_run.py <log csv> <idle threshold> [last second to show]
python3 plot_run.py ../runs/drinks_serve_guests.csv 0.2
"""

import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

log_file, threshold = Path(sys.argv[1]), float(sys.argv[2])
until = int(sys.argv[3]) if len(sys.argv) > 3 else None

with open(log_file) as f:
    rows = [row for row in csv.DictReader(f) if until is None or int(row['t']) <= until]
t = [int(row['t']) for row in rows]
actions = [c for c in rows[0] if c.startswith('P ') and any(float(row[c]) > 0 for row in rows)]

for column, line in zip(actions, ['-', '--', ':']):
    plt.step(t, [float(row[column]) for row in rows], line, where='post', label=column[2:])
plt.axhline(threshold, color='grey', linestyle=':', label='threshold')
plt.xlabel('time (s)')
plt.ylabel('P')
plt.legend()

out = log_file.with_suffix('') if until is None else log_file.with_name(f'{log_file.stem}_until_{until}')
plt.savefig(out.with_suffix('.pdf'), bbox_inches='tight')
plt.savefig(out.with_suffix('.png'), dpi=150, bbox_inches='tight')
