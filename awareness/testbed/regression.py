"""Check that the awareness manager still decides exactly as before: rerun every recorded run and compare its log. No ROS.

Each run is repeated in a temporary folder, so runs/ is never touched, and the SHA-256 of its event log is compared
with the one recorded below. A change that must not alter behaviour keeps every hash. A change that is meant to alter
it changes them: check the new run, then record its hash here.

Run:  python3 regression.py
"""

import contextlib
import hashlib
import io
import sys
import tempfile
from pathlib import Path

from load import load_scenario
from run import run

SCENARIOS = Path(__file__).resolve().parent.parent / 'scenarios'

# (scenario, world, policy, SHA-256 of the event log). Recorded with K, V, S and G: beliefs derived again after each
# telling and each find; an item is present at one place at a time; announced goals are weighed before they arrive.
RECORDED = [
    ('household', 'day', 'am', '00f1642d5de997b77ef3249af153d9a3b7c46989ad54c9965dcc4cb21e94569c'),
    ('household', 'day', 'round_robin', '3d23199fe48e83b2b02cf9541d45ccabbc43d0cb07a155150ddfa37cb2d4726c'),
]


def main():
    changed = 0
    with tempfile.TemporaryDirectory() as folder:
        for scenario, world, policy, expected in RECORDED:
            events_file = Path(folder) / f'{scenario}_{world}_{policy}.events.jsonl'
            with contextlib.redirect_stdout(io.StringIO()):
                run(load_scenario(SCENARIOS / scenario), SCENARIOS / scenario / 'worlds' / world, events_file, policy)
            found = hashlib.sha256(events_file.read_bytes()).hexdigest()
            changed += found != expected
            print(f'{"same   " if found == expected else "CHANGED"}  {scenario} {world} {policy:<12} {found}')
    print('all logs as recorded' if not changed else f'{changed} logs differ from the recorded ones')
    return 1 if changed else 0


if __name__ == '__main__':
    sys.exit(main())
