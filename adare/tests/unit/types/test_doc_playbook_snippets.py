"""Every complete playbook shown in the docs parses: no invented actions or keys.

A snippet counts as a complete playbook when it has top-level ``tests:`` and ``actions:``.
"""

import re
from pathlib import Path

import pytest

from adare.types.playbook import parse_playbook

pytestmark = pytest.mark.unit

DOCS = Path(__file__).resolve().parents[4] / 'docsrc' / 'source'
_YAML_BLOCK = re.compile(r'\.\. code-block:: yaml\n(?:   :[^\n]*\n)*\n((?:   [^\n]*\n|\n)+)')


def _playbook_snippets():
    for path in sorted(DOCS.rglob('*.rst')):
        for number, block in enumerate(_YAML_BLOCK.findall(path.read_text(encoding='utf-8')), 1):
            text = '\n'.join(line[3:] for line in block.split('\n'))
            if re.search(r'^tests:', text, re.M) and re.search(r'^actions:', text, re.M):
                yield pytest.param(text, id=f'{path.relative_to(DOCS)}#{number}')


SNIPPETS = list(_playbook_snippets())


def test_the_docs_have_playbook_snippets():
    assert len(SNIPPETS) >= 10


@pytest.mark.parametrize('text', SNIPPETS)
def test_playbook_snippet_parses(text, tmp_path):
    playbook = tmp_path / 'playbook.yml'
    playbook.write_text(text, encoding='utf-8')

    parse_playbook(playbook)  # raises ValueError naming the unknown action / key
