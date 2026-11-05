"""Plot a run log as a trace: P of every action, the idle threshold, a strip with the action the robot was doing,
and numbered markers at chosen times. No ROS.

Run:  python3 plot_trace.py <log csv> <idle threshold> [t:number ...]
python3 plot_trace.py ../runs/breakfast_d14.csv 0.2 0:1 15:2 232:3 263:4 349:5 420:6
"""

import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

log_file, threshold = Path(sys.argv[1]), float(sys.argv[2])
markers = [(int(t), label) for t, label in (arg.split(':') for arg in sys.argv[3:])]

with open(log_file) as f:
    rows = list(csv.DictReader(f))
t = [int(row['t']) for row in rows]
actions = [c[2:] for c in rows[0] if c.startswith('P ')]

# Okabe-Ito colours, one per action, and a line style each, so colour is never the only cue.
colours = ['#0072B2', '#E69F00', '#009E73', '#CC79A7', '#56B4E9', '#D55E00']
styles = ['-', '--', ':', '-.']
look = {a: (colours[i % len(colours)], styles[i % len(styles)]) for i, a in enumerate(actions)}

fig, (strip, ax) = plt.subplots(2, 1, sharex=True, figsize=(10, 4.5), gridspec_kw={'height_ratios': [1, 6]})

# Strip: the running action, one segment per stretch of ticks; the target's name is written in wide segments.
start = 0
for i in range(1, len(rows) + 1):
    if i == len(rows) or rows[i]['running'] != rows[start]['running']:
        action = rows[start]['running']
        if action:
            colour = look[action][0]
            strip.axvspan(t[start], t[i - 1] + 1, color=colour, alpha=0.8)
            if t[i - 1] + 1 - t[start] >= 10:
                strip.text((t[start] + t[i - 1] + 1) / 2, 0.5, action.split()[-1].split('_')[0],
                           ha='center', va='center', fontsize=7, rotation=90)
        start = i
strip.set_yticks([])
strip.set_ylabel('doing', rotation=0, ha='right', va='center')

for action in actions:
    colour, style = look[action]
    ax.step(t, [float(row[f'P {action}']) for row in rows], style, color=colour, where='post', label=action)
ax.axhline(threshold, color='grey', linewidth=2, alpha=0.5, label=f'threshold {threshold:g}')

for when, label in markers:
    for axis in (strip, ax):
        axis.axvline(when, color='black', linewidth=0.6)
    strip.annotate(label, (when, 1), xytext=(0, 4), textcoords='offset points', ha='center', va='bottom',
                   fontsize=9, bbox=dict(boxstyle='circle,pad=0.2', facecolor='white', edgecolor='black'))

ax.set_xlabel('time (s)')
ax.set_ylabel('P')
ax.set_xlim(t[0], t[-1])
ax.legend(fontsize=8, loc='upper right')

out = log_file.with_name(f'{log_file.stem}_trace')
fig.savefig(out.with_suffix('.pdf'), bbox_inches='tight')
fig.savefig(out.with_suffix('.png'), dpi=150, bbox_inches='tight')
print(out.with_suffix('.png'))
