"""Where the evaluation's files are, so the commands work from any folder."""

from pathlib import Path

# With --symlink-install this file is a link into the source; resolve() follows it there.
EVALUATION = Path(__file__).resolve().parents[1]
SCENARIO = EVALUATION / 'kitchen_30'
RUNS = EVALUATION / 'runs' / 'evaluation'
VIEW = EVALUATION / 'view.rviz'


def condition(name):
    """A path that exists as it is; otherwise the evaluation's folder of that name, e.g. conceptnet_mu960_seed2."""
    path = Path(name)
    return path if path.exists() else RUNS / name
