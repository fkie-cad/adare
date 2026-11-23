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
    # counts, sizes and content collections (rounds 1-3), phrased as goals
    ('file is empty', 'standard.file_size'),
    ('file size is at least 1 kb', 'standard.file_size'),
    ('how many files are in the folder', 'standard.file_count'),
    ('exactly 3 log files were written', 'standard.file_count'),
    ('number of files matching a glob', 'standard.file_count'),
    ('value was wiped from cache', 'text.occurrence_count'),
    ('a word occurs n times', 'text.occurrence_count'),
    ('how often a word occurs in a file', 'text.occurrence_count'),
    ('string occurs in a binary file utf-16', 'text.occurrence_count'),
    ('number of lines containing a string', 'text.line_count'),
    ('count lines in a text log', 'text.line_count'),
    ('count csv rows', 'csv.row_count'),
    ('csv row no longer present', 'csv.row_count'),
    ('compare csv against a reference file', 'csv.compare_files'),
    ('sqlite row count', 'sqlite.row_count'),
    ('number of records in a database table', 'sqlite.row_count'),
    ('count excel rows', 'excel.row_count'),
    ('docx author', 'xml.element_text_matches'),
    ('xml element text value', 'xml.element_text_matches'),
    ('count xml elements', 'xml.element_count'),
    ('how many json values at a key', 'json.value_count'),
    ('json key is absent', 'json.value_count'),
    ('jsonl line with type login exists', 'jsonl.line_matches'),
    ('field value in any jsonl line', 'jsonl.value_in_any_line'),
    ('ini section exists', 'ini.section_exists'),
    ('ini setting value', 'ini.value_matches'),
    ('duplicate ini keys count', 'ini.value_count'),
    ('plist preference value', 'plist.value_matches'),
    ('binary plist contains key', 'plist.contains_key'),
    ('yaml config value', 'yaml.value_matches'),
    ('how many yaml entries', 'yaml.value_count'),
    ('toml setting value', 'toml.value_matches'),
    ('toml key exists', 'toml.contains_key'),
    ('photo exif metadata', 'image.exif_value_matches'),
    ('gps location stripped from photo', 'image.exif_value_count'),
    ('png text chunk value', 'image.png_text_matches'),
    ('image width and height', 'image.dimensions_match'),
    ('find a string in a binary database file', 'text.occurrence_count'),
    ('utf-16 encoded string', 'text.occurrence_count'),
    ('timestamp stored as unix epoch in sqlite', 'sqlite.query_result'),
    # ordered comparisons and values_compare
    ('created date earlier than modified date in the same XML file', 'xml.values_compare'),
    ('two timestamps in one JSON file within 5 seconds', 'json.values_compare'),
    ('EXIF date taken after a given day', 'image.exif_value_matches'),
    # binary containers
    ('read a number at an offset of a binary file', 'binary.struct_value_matches'),
    ('count a byte pattern in a region of a binary file', 'binary.pattern_count'),
    ('key value pair in a binary metadata block', 'binary.pair_value_matches'),
    # sqlite write-ahead log
    ('changes not yet checkpointed in the sqlite wal', 'sqlite.wal_frame_count'),
    ('number of transactions in the wal file', 'sqlite.wal_frame_count'),
    ('row only in the write-ahead log, not in the main database file', 'sqlite.row_count'),
    # round 2: before/after, deleted data, order
    ('value in a JSON file larger than in a copy taken before the action', 'json.values_compare'),
    ('deleted row text still recoverable in sqlite free pages', 'sqlite.free_space_pattern_count'),
    ('row count in the current database compared to the main file', 'sqlite.values_compare'),
    ('lines of a log file appear in a given order', 'text.lines_in_order'),
    ('json lines events logged in order', 'jsonl.lines_in_order'),
]


TOP1_FLOOR = 0.9


@pytest.fixture(scope='module')
def catalog():
    return load_catalog(bundled_sources())


@pytest.mark.parametrize(('goal', 'expected'), GOLDEN, ids=[g for g, _ in GOLDEN])
def test_goal_finds_expected_in_top3(catalog, goal, expected):
    assert expected in [e.dotnotation for e in search(catalog, goal, limit=3)]


def test_top1_accuracy(catalog):
    hits = sum(search(catalog, goal, limit=1)[0].dotnotation == expected for goal, expected in GOLDEN)
    # 61/66 when last raised; raise the floor when the ranking improves, never lower it.
    assert hits / len(GOLDEN) >= TOP1_FLOOR, f'top-1 accuracy dropped to {hits}/{len(GOLDEN)}'
