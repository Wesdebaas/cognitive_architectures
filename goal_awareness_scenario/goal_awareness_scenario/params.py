"""Awareness manager tuning constants, read from config/awareness_params.yaml."""

from pathlib import Path

import yaml

DEFAULT = Path(__file__).resolve().parents[1] / 'config' / 'awareness_params.yaml'


def load(path=DEFAULT):
    return yaml.safe_load(Path(path).read_text())
