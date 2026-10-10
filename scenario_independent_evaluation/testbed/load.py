"""Load a scenario folder's scenario.py. No ROS."""

import importlib.util
from pathlib import Path


def load_scenario(folder):
    """The scenario.py module of a scenario folder."""
    spec = importlib.util.spec_from_file_location('scenario', Path(folder) / 'scenario.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
