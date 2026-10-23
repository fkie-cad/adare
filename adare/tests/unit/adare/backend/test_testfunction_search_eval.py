"""Discovery eval: realistic goals must find the function an expert would pick.

Guards the catalog search (and the bundled docs it ranks on) against regressions.
Add a case whenever an agent or user picked the wrong testfunction.
"""

import pytest

from adare.backend.testfunction.catalog import bundled_sources, load_catalog, search

pytestmark = pytest.mark.unit

GOLDEN = [
    ('the deleted file is gone', 'standard.file_does_not_exist'),
    ('file was created', 'standard.file_exists'),
    ('folder was removed', 'standard.dir_does_not_exist'),
    ('directory exists', 'standard.dir_exists'),
    ('file contains a string', 'standard.file_content_contains'),
    ('file content matches a regular expression', 'standard.file_content_matches_regex'),
    ('sha256 of the file', 'standard.file_hash_matches'),
    ('modification time of the file', 'standard.file_timestamps'),
    ('file permissions are 600', 'standard.file_permissions'),
    ('registry value was set', 'windows.registry_value_matches'),
    ('registry key exists', 'windows.registry_key_exists'),
    ('sqlite query returns rows', 'sqlite.query_result'),
    ('icon visible on screen', 'visual.exists'),
    ('text no longer shown on screen', 'visual.not_exists'),
    ('json key has value', 'json.value_matches'),
    ('json array contains element', 'json.array_contains'),
    ('xml element exists', 'xml.element_exists'),
    ('xpath result', 'xml.xpath_result_matches'),
    ('excel cell value', 'excel.cell_value_matches'),
    ('spreadsheet sheet exists', 'excel.sheet_exists'),
    ('csv contains a row', 'csv.contains_line'),
    ('jsonl line count', 'jsonl.line_count'),
    ('service is running', 'linux.system_service_status'),
    ('process is running', 'linux.process_running'),
    ('user account exists', 'linux.user_exists'),
    ('log entry written', 'linux.log_entry_exists'),
]


@pytest.fixture(scope='module')
def catalog():
    return load_catalog(bundled_sources())


@pytest.mark.parametrize(('goal', 'expected'), GOLDEN, ids=[g for g, _ in GOLDEN])
def test_goal_finds_expected_in_top3(catalog, goal, expected):
    assert expected in [e.dotnotation for e in search(catalog, goal, limit=3)]


def test_top1_accuracy(catalog):
    hits = sum(search(catalog, goal, limit=1)[0].dotnotation == expected for goal, expected in GOLDEN)
    assert hits >= len(GOLDEN) - 4, f'top-1 accuracy dropped to {hits}/{len(GOLDEN)}'
