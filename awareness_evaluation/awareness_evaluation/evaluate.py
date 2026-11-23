"""Every condition of the evaluation: per placement, persistence and seed, a copy of the scenario with its own world,
run by every policy and scored. Prints the means per condition and writes every run's score to results.csv.

ros2 run awareness_evaluation evaluate [scenario folder] [output folder]
Defaults: awareness_evaluation/kitchen_30 and awareness_evaluation/runs/evaluation.
"""

import csv
import re
import shutil
import sys
from multiprocessing import Pool
from pathlib import Path

import yaml

from .draw_moves import PLACEMENTS, write_world
from .paths import RUNS, SCENARIO
from .score import result
from .simulate import POLICIES, run
from .steps import read

# Mean seconds an item stays where it is, set as every item's am:persistence. Chosen: halving and doubling around
# 480 s, from about one move per round robin round (244 s over 24 places) to one per eight rounds.
PERSISTENCES = [240, 480, 960, 1920]

# Chosen: 5, enough to see whether one policy wins in most seeds; every seed's score is in results.csv.
SEEDS = [1, 2, 3, 4, 5]

COLUMNS = ['placement', 'persistence', 'seed', 'policy', 'correct', 'wrong', 'unknown', 'all items']


def condition(job):
    """Makes the condition's scenario copy, draws its world, runs every policy. Returns one row per policy."""
    scenario, out, placement, persistence, seed = job
    folder = out / f'{placement}_mu{persistence}_seed{seed}'
    shutil.rmtree(folder, ignore_errors=True)
    shutil.copytree(scenario, folder)
    with open(folder / 'run.yaml') as f:
        knowledge = yaml.safe_load(f)['knowledge']
    changed = 0
    for name in knowledge:
        turtle, n = re.subn(r'am:persistence\s+[\d.]+', f'am:persistence {persistence}', (folder / name).read_text())
        (folder / name).write_text(turtle)
        changed += n
    assert changed, f'no am:persistence in {knowledge}'
    write_world(folder, seed, placement)
    rows = []
    for policy in POLICIES:
        events = folder / f'{policy}.events.jsonl'
        with open(events, 'w') as f:
            run(folder / 'day', f, policy)
        share = result(read(events))
        rows.append([placement, persistence, seed, policy] + [round(share[column], 1) for column in COLUMNS[4:]])
    return rows


def main():
    scenario = Path(sys.argv[1]) if len(sys.argv) > 1 else SCENARIO
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else RUNS
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(scenario, out, placement, persistence, seed)
            for placement in PLACEMENTS for persistence in PERSISTENCES for seed in SEEDS]
    with Pool() as pool:
        rows = [row for rows in pool.map(condition, jobs) for row in rows]
    with open(out / 'results.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)

    am = POLICIES[0]
    print(f'needed items correct, mean of {len(SEEDS)} seeds; {am} - round robin, and in how many seeds the AM is higher')
    print(f"{'placement':>10s}{'persistence':>12s}" + ''.join(f'{policy:>25s}' for policy in POLICIES)
          + ''.join(f'{"AM - " + policy.removeprefix("round_robin_"):>20s}' for policy in POLICIES[1:]))
    for placement in PLACEMENTS:
        for persistence in PERSISTENCES:
            correct = {policy: {row[2]: row[4] for row in rows if row[:2] == [placement, persistence] and row[3] == policy}
                       for policy in POLICIES}
            line = f'{placement:>10s}{persistence:>12d}'
            line += ''.join(f'{sum(correct[policy].values()) / len(SEEDS):24.1f}%' for policy in POLICIES)
            for policy in POLICIES[1:]:
                gap = sum(correct[am][seed] - correct[policy][seed] for seed in SEEDS) / len(SEEDS)
                wins = sum(correct[am][seed] > correct[policy][seed] for seed in SEEDS)
                line += f'{gap:+12.1f}  ({wins}/{len(SEEDS)})'
            print(line)
    print(f'every run: {out / "results.csv"}')
