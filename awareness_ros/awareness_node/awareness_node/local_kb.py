"""The KB inside this program, without ROS, for evaluation: the same preload files, templates and pyoxigraph store
as the TriplestarKB, reached by a direct call instead of over ROS."""

from pathlib import Path

import pyoxigraph as ox
import yaml
from ament_index_python.packages import get_package_share_directory
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from triplestar_core.subscriptions.subscriber_manager import _rdf_filter

from .kb import TOPICS


class LocalKB:

    def __init__(self, bringup='awareness_kb'):
        share = Path(get_package_share_directory(bringup))
        with open(share / 'config' / 'triplestar.yaml') as f:
            config = yaml.safe_load(f)
        self.base_iri = config['knowledge_base']['base_iri']
        self.store = ox.Store()
        for name in config['knowledge_base']['preload_files']:
            self.store.load(path=str(share / 'preload' / name), format=ox.RdfFormat.TURTLE, base_iri=self.base_iri)
        templates = Environment(loader=FileSystemLoader(share / 'templates'), autoescape=False, undefined=StrictUndefined)
        templates.filters['rdf'] = _rdf_filter   # triplestar's own, so values are written exactly as it writes them
        by_topic = {sub['topic']: templates.get_template(sub['template']) for sub in config['insertion_subscribers']}
        self.templates = {kind: by_topic[topic] for kind, topic in TOPICS.items()}

    def query(self, sparql):
        return self.store.query(sparql, base_iri=self.base_iri)

    def write(self, msg, check=None):
        """No check needed: the update is done when this returns."""
        self.store.update(self.templates[type(msg)].render(msg=msg), base_iri=self.base_iri)
