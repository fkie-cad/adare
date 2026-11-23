"""Contract parsing, checks, example files, rendering and the agent search on a synthetic collection."""

import gzip
import io
import zipfile
from pathlib import Path

import pytest

from adare.backend.testfunction.catalog import load_catalog
from adare.backend.testfunction.contract import (
    ContractError,
    example_dict,
    example_yaml,
    load_library,
    parse_contract,
    read_contract_file,
)
from adare.backend.testfunction.contract_checks import collection_problems
from adare.backend.testfunction.contract_examples import build_bytes, local_path, rewrite_paths
from adare.backend.testfunction.contract_render import function_markdown, function_rst, markdown_files
from adare.backend.testfunction.search_cards import facet_filter, result_dict, search_goal

pytestmark = pytest.mark.unit

LIBRARY = """
asserts: {exists: present, absent: gone, value: a value, count: how many}
formats: {file: any file, json: JSON}
features:
  archive_dst: {title: Archives, summary: members via !}
  glob_dst: {title: Globs, summary: globs in dst}
  regex_tag: {title: Regex, summary: '!re values'}
  count_comparison: {title: Counts, summary: expected_count}
gaps:
  - id: evtx
    summary: No event log parser.
    keywords: [event log, evtx]
    instead: Export to XML first.
"""

CODE = """
@testfunction(name='key_exists', description='tests if a JSON key exists', category=HostModeCategory.FILE_CONTENT)
def key_exists(ctx, dst: str, key_path: str):
    '''Pass when the key exists.

    Use for: a JSON setting was written.

    Args:
        dst: Guest path.
        key_path: Dot path.
    '''

@testfunction(name='key_count', description='tests how often a JSON key occurs', category=HostModeCategory.FILE_CONTENT)
def key_count(ctx, dst: str, key_path: str, expected_count: int, mode: str = 'any'):
    '''Pass when the count matches.

    Use for: counting keys; a key that is gone (``expected_count: 0``).

    Args:
        dst: Guest path.
        key_path: Dot path.
        expected_count: Count.
        mode: any or all.
    '''
"""

CONTRACT = """
collection: {title: Demo, summary: Demo JSON files.}
functions:
  key_exists:
    asserts: [exists]
    formats: [json]
    features: [archive_dst, glob_dst]
    not_for:
      - goal: a key is absent or gone
        use: demo.key_count
    outcomes: {passed: the key exists, failed: the key is missing, error: [no such file]}
    examples:
      - title: key present
        files: {/home/u/a.json: {json: {a: 1}}}
        parameter: {dst: /home/u/a.json, key_path: a}
  key_count:
    asserts: [count, absent]
    formats: [json]
    features: [archive_dst, count_comparison]
    unsupported: {glob_dst: 'one file only'}
    choices: {mode: [any, all]}
    examples:
      - title: gone
        parameter: {dst: /home/u/a.json, key_path: b, expected_count: 0, mode: any}
      - title: timed
        parameter: {dst: /home/u/a.json, key_path: !re '^b', expected_count: 1}
"""


@pytest.fixture()
def demo(tmp_path):
    root = tmp_path / 'tf'
    (root / 'demo').mkdir(parents=True)
    (root / 'demo' / 'demo.py').write_text(CODE)
    (root / 'demo' / 'contract.yaml').write_text(CONTRACT)
    (root / 'library.yaml').write_text(LIBRARY)
    entries = load_catalog([(root, False)])
    return root, entries, load_library(root)


def test_contract_loads_into_catalog_entries(demo):
    _, entries, _ = demo
    by_name = {e.dotnotation: e for e in entries}
    assert by_name['demo.key_exists'].contract.not_for[0].use == 'demo.key_count'
    assert by_name['demo.key_count'].contract.unsupported == {'glob_dst': 'one file only'}
    assert by_name['demo.key_exists'].collection_info.title == 'Demo'
    # the documented example replaces the placeholder example
    assert by_name['demo.key_exists'].example()['parameter'] == {'dst': '/home/u/a.json', 'key_path': 'a'}
    assert by_name['demo.key_exists'].to_dict()['contract']['outcomes']['error'] == ['no such file']


def test_examples_keep_tags_as_written(demo):
    _, entries, _ = demo
    timed = next(e for e in entries if e.name == 'key_count').contract.examples[1]
    assert "key_path: !re '^b'" in example_yaml('demo.key_count', timed)
    assert example_dict(timed)['parameter']['key_path'] == "!re '^b'"


@pytest.mark.parametrize(
    ('body', 'message'),
    [
        ({'asserts': ['value'], 'colour': 1}, 'unknown key'),
        ({'examples': [{'title': 't', 'expect': 'maybe'}]}, 'not one of'),
        ({'outcomes': {'ok': 'x'}}, 'keys are'),
        ({'not_for': [{'goal': 'x'}]}, 'needs `use:'),
        ({'choices': {'mode': []}}, 'non-empty list'),
    ],
)
def test_schema_errors(body, message):
    with pytest.raises(ContractError, match=message):
        parse_contract(body, 'demo')


def test_broken_contract_file_is_reported(tmp_path):
    path = tmp_path / 'contract.yaml'
    path.write_text('functions:\n  a:\n    limits: Something: with a colon\n')
    with pytest.raises(ContractError):
        read_contract_file(path)


def test_consistent_contract_has_no_problems(demo):
    root, entries, library = demo
    assert collection_problems(root / 'demo' / 'demo.py', entries, library) == []


def test_checks_catch_wrong_claims(demo):
    root, _, library = demo
    (root / 'demo' / 'contract.yaml').write_text(
        CONTRACT.replace('features: [archive_dst, glob_dst]', 'features: [archive_dst, teleport]')
        .replace('use: demo.key_count', 'use: demo.nope')
        .replace('choices: {mode: [any, all]}', 'choices: {mode: [all], colour: [red]}')
        .replace('key_path: a}', 'key_path: a, extra: 1}')
    )
    entries = load_catalog([(root, False)])
    problems = '\n'.join(collection_problems(root / 'demo' / 'demo.py', entries, library))
    assert 'unknown features teleport' in problems
    assert 'does not declare `glob_dst`' in problems
    assert 'demo.nope` is no known testfunction' in problems
    assert "default 'any' of \"mode\" is not in its choices" in problems
    assert 'choices for unknown parameter "colour"' in problems
    assert 'unknown parameter "extra"' in problems
    assert "mode='any' is not one of" in problems


def test_search_follows_not_for_redirects(demo):
    _, entries, library = demo
    result = search_goal(entries, 'json key is gone', library=library)
    assert result.hits[0].entry.dotnotation == 'demo.key_count'
    data = result_dict(result, 'json key is gone')
    assert data['match'] == 'good'
    assert data['results'][0]['does_not_support'] == {'glob_dst': 'one file only'}


def test_search_says_when_nothing_fits_and_names_gaps(demo):
    _, entries, library = demo
    data = result_dict(search_goal(entries, 'parse the windows event log', library=library), 'q')
    assert data['match'] == 'weak'
    assert data['known_gaps'] == [{'gap': 'No event log parser.', 'instead': 'Export to XML first.'}]
    assert 'advice' in data


def test_facet_filters(demo):
    _, entries, _ = demo
    assert [e.name for e in facet_filter(entries, asserts='absent')] == ['key_count']
    assert [e.name for e in facet_filter(entries, feature='glob_dst')] == ['key_exists']
    assert facet_filter(entries, fmt='file') == []


def test_markdown_and_rst_render_the_same_sections(demo):
    _, entries, library = demo
    entry = next(e for e in entries if e.name == 'key_count')
    markdown = function_markdown(entry, library)
    rst = function_rst(entry, library, docs_root=Path('/nonexistent'))
    for text in ('Does not support', 'one file only', 'Allowed: `any`, `all`'):
        assert text in markdown
    for text in ('What it does not do', 'one file only', 'Allowed: ``any``, ``all``', '.. code-block:: yaml'):
        assert text in rst
    files = markdown_files(entries, library)
    assert set(files) == {'catalog/index.md', 'catalog/demo.md', 'features.md'}
    assert '`demo.key_count` [count, absent · json]' in files['catalog/index.md']
    assert 'No event log parser.' in files['features.md']


def test_file_specs():
    assert build_bytes({'concat': [{'text': 'AB'}, {'u16be': 1}, {'hex': 'ff'}]}) == b'AB\x00\x01\xff'
    assert gzip.decompress(build_bytes({'gzip': {'text': 'x'}})) == b'x'
    with zipfile.ZipFile(io.BytesIO(build_bytes({'zip': {'d/a.json': {'json': {'a': 1}}}}))) as archive:
        assert archive.read('d/a.json') == b'{"a": 1}'
    assert build_bytes({'text': 'é', 'encoding': 'utf-16-le'}) == 'é'.encode('utf-16-le')


def test_guest_paths_map_into_the_temp_root(tmp_path):
    assert local_path(tmp_path, 'C:\\Users\\u\\a.json') == tmp_path / 'C' / 'Users' / 'u' / 'a.json'
    files = {'/home/u/b.zip': {}, 'C:\\Users\\u\\a.json': {}}
    params = rewrite_paths({'dst': '/home/u/b.zip!/x/y.json', 'other': 'C:\\Users\\u\\*.json', 'n': 3}, files, tmp_path)
    assert params['dst'] == f'{tmp_path.as_posix()}/home/u/b.zip!/x/y.json'
    assert params['other'] == f'{tmp_path.as_posix()}/C/Users/u/*.json'
    assert params['n'] == 3


def test_playbook_check_warns_on_disallowed_values_and_reads_tags(demo):
    from adare.types.playbook_test_checks import check_playbook_tests

    _, entries, _ = demo
    playbook = """
tests:
  - name: t1
    function: demo.key_count
    parameter: {dst: /a.json, key_path: !re '^b', expected_count: 0, mode: some}
actions:
  - test: t1
"""
    errors, warnings = check_playbook_tests(playbook, entries)
    assert errors == []
    assert any("mode='some' is not allowed" in w for w in warnings)
