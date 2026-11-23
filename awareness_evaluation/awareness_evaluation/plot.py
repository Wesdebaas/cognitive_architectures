"""The evaluation's two figures from results.csv: correct.png, the needed items correct per persistence, and states.png,
the shares correct, wrong and unknown per policy.

ros2 run awareness_evaluation plot [results.csv]
Default: awareness_evaluation/runs/evaluation/results.csv; the figures are written next to it.
"""

import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')   # files only, no window
import matplotlib.pyplot as plt  # noqa: E402

from .draw_moves import PLACEMENTS  # noqa: E402
from .paths import RUNS  # noqa: E402
from .simulate import POLICIES  # noqa: E402

LABELS = {'awareness_manager': 'awareness manager', 'round_robin_item_places': 'round robin, item places',
          'round_robin_all_places': 'round robin, all places'}
BAR_LABELS = {'awareness_manager': 'awareness\nmanager', 'round_robin_item_places': 'round robin,\nitem places',
              'round_robin_all_places': 'round robin,\nall places'}

# Colour, marker, line style per policy. Chosen: Okabe and Ito's colour-blind safe colours; marker and line style
# repeat the difference without colour.
STYLES = {'awareness_manager': ('#0072B2', 'o', '-'), 'round_robin_item_places': ('#E69F00', 's', '--'),
          'round_robin_all_places': ('#009E73', '^', ':')}

# Fill and hatch per state. Chosen: greys and a hatch, so they never look like a policy's colour and read in print.
STATES = {'correct': ('0.35', ''), 'wrong': ('white', '//'), 'unknown': ('0.8', '')}


def read(file):
    with open(file) as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for column in ('persistence', 'seed'):
            row[column] = int(row[column])
        for column in ('correct', 'wrong', 'unknown', 'all items'):
            row[column] = float(row[column])
    return rows


def mean(values):
    return sum(values) / len(values)


def correct(rows, file):
    """One panel per placement: the mean over seeds as a line, every seed as a dot."""
    figure, axes = plt.subplots(1, len(PLACEMENTS), sharey=True, figsize=(9, 4))
    for axis, placement in zip(axes, PLACEMENTS):
        for shift, policy in zip((-0.06, 0, 0.06), POLICIES):   # dots of the three policies side by side
            colour, marker, line = STYLES[policy]
            runs = [row for row in rows if row['placement'] == placement and row['policy'] == policy]
            persistences = sorted({row['persistence'] for row in runs})
            axis.plot(persistences, [mean([row['correct'] for row in runs if row['persistence'] == p])
                                     for p in persistences],
                      color=colour, marker=marker, linestyle=line, label=LABELS[policy])
            axis.scatter([row['persistence'] * 2 ** shift for row in runs], [row['correct'] for row in runs],
                         color=colour, marker=marker, s=10, alpha=0.4)
        axis.set_xscale('log', base=2)
        axis.set_xticks(persistences, [str(p) for p in persistences])
        axis.minorticks_off()
        axis.set_title(f'placement: {placement}')
        axis.set_xlabel('persistence μ (s)')
    axes[0].set_ylabel('needed items correct (% of goal time)')
    axes[0].legend()
    figure.tight_layout()
    figure.savefig(file, dpi=150)


def states(rows, file):
    """One panel per placement: per policy, the mean shares correct, wrong and unknown over every run."""
    figure, axes = plt.subplots(1, len(PLACEMENTS), sharey=True, figsize=(9, 4))
    for axis, placement in zip(axes, PLACEMENTS):
        bottom = [0.0] * len(POLICIES)
        for state, (fill, hatch) in STATES.items():
            heights = [mean([row[state] for row in rows if row['placement'] == placement and row['policy'] == policy])
                       for policy in POLICIES]
            axis.bar([BAR_LABELS[policy] for policy in POLICIES], heights, bottom=bottom,
                     color=fill, hatch=hatch, edgecolor='black', label=state)
            bottom = [b + h for b, h in zip(bottom, heights)]
        axis.set_title(f'placement: {placement}')
    axes[0].set_ylabel('needed items (% of goal time)')
    axes[-1].legend(loc='center left', bbox_to_anchor=(1, 0.5))   # beside the bars, not over them
    figure.tight_layout()
    figure.savefig(file, dpi=150)


def main():
    file = Path(sys.argv[1]) if len(sys.argv) > 1 else RUNS / 'results.csv'
    rows = read(file)
    correct(rows, file.parent / 'correct.png')
    states(rows, file.parent / 'states.png')
    print(f"{file.parent / 'correct.png'}\n{file.parent / 'states.png'}")
