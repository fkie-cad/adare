"""Static testfunction catalog: parsing, lookup, search and agent-facing shapes."""

import textwrap

import pytest

from adare.backend.testfunction.catalog import (
    bundled_sources,
    close_matches,
    find,
    load_catalog,
    parse_args_section,
    search,
)

pytestmark = pytest.mark.unit

COLLECTION = '''
from adarelib.testset.api import testfunction
from adarelib.testset.basictest import HostModeCategory


@testfunction(name='file_exists', description='tests if file exists', category=HostModeCategory.FILE_BASED)
def file_exists(ctx, dst: str = '', match_mode: str = "any", tags: list[str] | None = None):
    """Pass when the file exists.

    Args:
        dst: Guest path,
            globs allowed.
        match_mode: any or all.

    Example:
        function: demo.file_exists
    """


@testfunction(name='file_does_not_exist', description='tests if file does NOT exist')
def file_does_not_exist(ctx, dst: str):
    pass


@testfunction(name='visual.exists', description='Check if text is visible on screen',
              category=HostModeCategory.HOST_NATIVE, execute_on_host=True)
async def visual_exists(ctx, text: str = None):
    pass


def helper(x):
    return x
'''


@pytest.fixture()
def entries(tmp_path):
    installed = tmp_path / 'installed' / 'demo'
    installed.mkdir(parents=True)
    (installed / 'demo.py').write_text(COLLECTION)
    bundled = tmp_path / 'bundled' / 'winreg'
    bundled.mkdir(parents=True)
    (bundled / 'winreg.py').write_text(
        textwrap.dedent('''
        @testfunction(name='key_exists', description='tests if registry key exists (Windows only)')
        def key_exists(ctx, key_path: str):
            pass
    ''')
    )
    (bundled / 'not_the_collection.py').write_text(COLLECTION)  # filename != dirname: ignored
    return load_catalog([(tmp_path / 'installed', True), (tmp_path / 'bundled', False)])


def test_parses_signatures_exactly(entries):
    entry = find(entries, 'demo.file_exists')
    assert [(p.name, p.type, p.required, p.default) for p in entry.params] == [
        ('dst', 'str', False, ''),
        ('match_mode', 'str', False, 'any'),
        ('tags', 'list[str] | None', False, None),
    ]
    assert entry.category == 'FILE_BASED' and entry.installed
    assert entry.params[0].doc == 'Guest path, globs allowed.'
    assert (
        entry.signature() == "demo.file_exists(dst: str = '', match_mode: str = 'any', tags: list[str] | None = None)"
    )


def test_async_and_dotted_host_native_names(entries):
    entry = find(entries, 'visual.exists')
    assert entry.collection == 'demo' and entry.execute_on_host and entry.category == 'HOST_NATIVE'


def test_only_collection_files_and_os_inference(entries):
    assert {e.dotnotation for e in entries} == {
        'demo.file_exists',
        'demo.file_does_not_exist',
        'visual.exists',
        'winreg.key_exists',
    }
    assert find(entries, 'winreg.key_exists').os == 'windows'
    assert not find(entries, 'winreg.key_exists').installed


def test_find_accepts_legacy_project_prefix(entries):
    assert find(entries, 'myproject.demo.file_exists').name == 'file_exists'
    assert find(entries, 'demo.nope') is None


def test_close_matches_tolerates_typos(entries):
    assert close_matches(entries, 'demo.file_exsts')[0].dotnotation == 'demo.file_exists'


def test_negative_goal_prefers_inverse_function(entries):
    assert search(entries, 'verify the file was deleted')[0].dotnotation == 'demo.file_does_not_exist'
    assert search(entries, 'file exists')[0].dotnotation == 'demo.file_exists'


def test_search_filters(entries):
    assert [e.dotnotation for e in search(entries, 'key', os='windows')] == ['winreg.key_exists']
    assert search(entries, collection='winreg') == [find(entries, 'winreg.key_exists')]
    assert search(entries, 'screen visible')[0].dotnotation == 'visual.exists'


def test_example_marks_required_and_empty_defaults(entries):
    assert find(entries, 'demo.file_exists').example() == {
        'name': 'check_file_exists',
        'function': 'demo.file_exists',
        'parameter': {'dst': '<str>'},
    }
    assert find(entries, 'visual.exists').example() == {'name': 'check_exists', 'function': 'visual.exists'}


def test_compact_dict_is_small(entries):
    compact = find(entries, 'demo.file_exists').to_dict(compact=True)
    assert set(compact) == {'dotnotation', 'summary', 'signature', 'os', 'installed'}


def test_parse_args_section_stops_at_next_section():
    doc = 'Summary.\n\nArgs:\n    a (int): first\n        more\n    b: second\n\nReturns:\n    c: not an arg\n'
    assert parse_args_section(doc) == {'a': 'first more', 'b': 'second'}


def test_bundled_catalog_is_complete():
    bundled = load_catalog(bundled_sources())
    collections = {e.collection for e in bundled}
    assert {'standard', 'visual', 'windows', 'linux'} <= collections
    assert find(bundled, 'visual.exists').installed  # host-native: always available, never synced
    assert len(bundled) >= 40


def test_find_bare_name_means_standard_like_runtime(tmp_path):
    root = tmp_path / 'standard'
    root.mkdir()
    (root / 'standard.py').write_text(
        "@testfunction(name='file_exists', description='tests if file exists')\ndef file_exists(ctx, dst: str):\n    pass\n"
    )
    entries = load_catalog([(tmp_path, True)])
    assert find(entries, 'file_exists').dotnotation == 'standard.file_exists'


def test_undocumented_installed_copy_borrows_docs_only_when_code_is_identical(tmp_path):
    code = "def file_exists(ctx, dst: str):\n{doc}    return dst\n"
    doc = '    """Pass when it exists.\n\n    Args:\n        dst: Guest path.\n    """\n'
    for root, body in (('installed', code.format(doc='')), ('bundled', code.format(doc=doc))):
        (tmp_path / root / 'same').mkdir(parents=True)
        (tmp_path / root / 'same' / 'same.py').write_text("@testfunction(name='file_exists', description='d')\n" + body)
    changed = code.format(doc='').replace('return dst', 'return None')
    (tmp_path / 'installed' / 'diff').mkdir()
    (tmp_path / 'installed' / 'diff' / 'diff.py').write_text(
        "@testfunction(name='file_exists', description='d')\n" + changed
    )
    (tmp_path / 'bundled' / 'diff').mkdir()
    (tmp_path / 'bundled' / 'diff' / 'diff.py').write_text(
        "@testfunction(name='file_exists', description='d')\n" + code.format(doc=doc)
    )
    entries = load_catalog([(tmp_path / 'installed', True), (tmp_path / 'bundled', False)])
    same, diff = find(entries, 'same.file_exists'), find(entries, 'diff.file_exists')
    assert same.installed and same.params[0].doc == 'Guest path.' and same.doc.startswith('Pass when')
    assert diff.installed and diff.params[0].doc == '' and diff.doc == ''
    assert 'code_sha' not in same.to_dict()


def test_skill_catalog_reference_is_fresh():
    """skills/adare-testfunction/references/catalog.md must match the bundled sources.

    Regenerate with: adare test catalog --markdown > skills/adare-testfunction/references/catalog.md
    """
    from pathlib import Path

    from adare.frontend.terminal.testfunction_catalog import catalog_markdown

    reference = Path(__file__).resolve().parents[5] / 'skills' / 'adare-testfunction' / 'references' / 'catalog.md'
    assert reference.read_text(encoding='utf-8') == catalog_markdown(load_catalog(bundled_sources())), (
        'stale catalog.md: run `adare test catalog --markdown > skills/adare-testfunction/references/catalog.md`'
    )


def _write_collection(root, name, body):
    (root / name).mkdir(parents=True, exist_ok=True)
    path = root / name / f'{name}.py'
    path.write_text(body)
    return path


def _bump_mtime(path):
    import os

    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))


def test_load_catalog_is_cached_until_a_source_changes(tmp_path, monkeypatch):
    from adare.backend.testfunction import catalog

    parsed = []
    real_parse = catalog.parse_collection
    monkeypatch.setattr(
        catalog, 'parse_collection', lambda path, installed: parsed.append(path) or real_parse(path, installed)
    )
    one = "@testfunction(name='{n}', description='d')\ndef {n}(ctx, dst: str):\n    pass\n"
    path = _write_collection(tmp_path, 'demo', one.format(n='aaa'))
    sources = [(tmp_path, True)]

    first = load_catalog(sources)
    assert load_catalog(sources) == first
    assert len(parsed) == 1  # second call served from the cache

    # Edited in place (same size: only the mtime shows it).
    path.write_text(one.format(n='bbb'))
    _bump_mtime(path)
    assert [e.name for e in load_catalog(sources)] == ['bbb']

    # A new collection appears.
    _write_collection(tmp_path, 'extra', one.format(n='ccc'))
    assert [e.name for e in load_catalog(sources)] == ['bbb', 'ccc']

    # A collection is removed.
    path.unlink()
    assert [e.name for e in load_catalog(sources)] == ['ccc']
    assert len(parsed) == 1 + 1 + 2 + 1


def test_load_catalog_returns_a_fresh_list(tmp_path):
    _write_collection(tmp_path, 'demo', "@testfunction(name='x', description='d')\ndef x(ctx):\n    pass\n")
    entries = load_catalog([(tmp_path, True)])
    entries.clear()
    assert len(load_catalog([(tmp_path, True)])) == 1
