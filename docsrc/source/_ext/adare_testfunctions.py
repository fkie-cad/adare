"""Sphinx directives that render testfunction reference content from the catalog + contracts.

The single source is the collection code (docstring: summary, "Use for:", ``Args:``) and its
``contract.yaml`` (asserts, features, not-for, outcomes, limits, allowed values, use cases,
examples); the same source feeds ``adare test info/search`` and the agent skill's references.

.. adare-testfunction:: binary.pair_count      the whole reference body of one function
.. adare-testfunction-collection:: binary      a collection's summary paragraph
.. adare-testfunction-features::               every shared feature, and the known gaps
"""

from docutils import nodes
from docutils.statemachine import StringList
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective
from sphinx.util.nodes import nested_parse_with_titles

_STATE: dict = {}


def _catalog():
    if 'entries' not in _STATE:
        from adare.backend.testfunction.catalog import bundled_sources, load_catalog
        from adare.backend.testfunction.contract import load_library

        _STATE['entries'] = load_catalog(bundled_sources())
        _STATE['library'] = load_library()
    return _STATE['entries'], _STATE['library']


class _RenderDirective(SphinxDirective):
    def render(self) -> str:
        raise NotImplementedError

    def run(self) -> list[nodes.Node]:
        text = self.render()
        container = nodes.section() if '\n---' in text else nodes.container()
        source = self.get_source_info()[0]
        lines = StringList(text.splitlines(), source=source)
        nested_parse_with_titles(self.state, lines, container)
        return container.children


class TestfunctionDirective(_RenderDirective):
    required_arguments = 1

    def render(self) -> str:
        from adare.backend.testfunction.catalog import find
        from adare.backend.testfunction.contract_render import function_rst

        entries, library = _catalog()
        entry = find(entries, self.arguments[0])
        if entry is None:
            raise self.error(f'unknown testfunction {self.arguments[0]}')
        return function_rst(entry, library)


class CollectionDirective(_RenderDirective):
    required_arguments = 1

    def render(self) -> str:
        from adare.backend.testfunction.contract_render import collection_rst

        entries, _ = _catalog()
        text = collection_rst(self.arguments[0], entries)
        if not text:
            raise self.error(f'no contract summary for collection {self.arguments[0]}')
        return text


class FeaturesDirective(_RenderDirective):
    def render(self) -> str:
        from adare.backend.testfunction.contract_render import features_rst

        entries, library = _catalog()
        return features_rst(entries, library)


def setup(app: Sphinx) -> dict:
    app.add_directive('adare-testfunction', TestfunctionDirective)
    app.add_directive('adare-testfunction-collection', CollectionDirective)
    app.add_directive('adare-testfunction-features', FeaturesDirective)
    return {'parallel_read_safe': True, 'parallel_write_safe': True}
