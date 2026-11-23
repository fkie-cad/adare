"""End to end: a playbook ``tests:`` entry evaluated host-side over a GuestFS.

The chain is the product's own, from the YAML text to the verdict:

``parse_playbook`` (custom tags) -> ``VariableResolver`` over the automatic + user variables,
built as ``PlaybookController._initialize_modules`` builds it -> ``TestActionsExecutor.execute_test``
in host mode: ``TestLoader.resolve_test_with_runtime_context`` (placeholders + ``_VARIABLE_METADATA``),
``normalize_test_parameters`` (archive dst), ``TestLoader.get_test_class`` +
``structure_host_test`` (cattrs with the union hook) -> ``HostsideTestExecutor.execute_test`` ->
the real testfunction on files extracted from the GuestFS -> ``TestResultProcessor``.

Stubbed (the narrowest layers that need a VM or an installed ADARE home):

- the GuestFS is a ``PatchedGuestFS`` (staged writes) over an empty base, instead of a disk image;
- the hostside session is a fake that hands out that GuestFS and drops the markers;
- ``STATE_DIR`` points to a directory whose ``testfunctions`` is the repository's built-in
  collections (an installation copies them to ``~/.adare/testfunctions``).
"""

import asyncio
import datetime
import io
import json
import sqlite3
import struct
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from adare.backend.experiment import test_loader
from adare.backend.experiment.execution import base as execution_base
from adare.backend.experiment.execution import test_actions
from adare.backend.experiment.variable_resolver import VariableResolver
from adare.backend.hostside.guestfs import GuestFileNotFound, GuestFS, PatchedGuestFS, StagedOp
from adare.backend.hostside.testing import GuestFSFileProxy, HostsideTestExecutor
from adare.types.playbook import ActionTestAction, parse_playbook
from adarelib.common.automatic_variables import AutomaticVariables
from adarelib.common.variables import Variable, VariableType
from adarelib.constants import StatusEnum
from adarelib.testset.testfunction import import_basictest_subclasses

pytestmark = pytest.mark.unit

TESTFUNCTIONS = Path(__file__).resolve().parents[5] / 'appdata' / 'testfunctions'

# 2024-01-02 03:04:05 UTC as Unix seconds and as a FILETIME (100 ns since 1601)
UNIX_S = 1704164645
FILETIME = (UNIX_S + 11644473600) * 10_000_000

DOC = {
    'items': [
        {'name': 'entry-1', 'ts': FILETIME, 'ms': UNIX_S * 1000},
        {'name': 'entry-22', 'ts': FILETIME + 10_000_000, 'ms': UNIX_S * 1000 + 1500},
        {'name': 'other', 'ts': FILETIME + 3600 * 10_000_000, 'ms': (UNIX_S + 3600) * 1000},
    ]
}


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _wal_database() -> tuple[bytes, bytes]:
    """(main file, -wal) of a WAL database: row 1 checkpointed, rows 2 and 3 only in the -wal."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / 'state.db'
        conn = sqlite3.connect(str(db))
        try:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA wal_autocheckpoint=0')
            conn.execute('CREATE TABLE items (id INTEGER, name TEXT)')
            conn.execute("INSERT INTO items VALUES (1, 'alpha')")
            conn.commit()
            conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            for i, name in ((2, 'beta'), (3, 'gamma')):  # one transaction each
                conn.execute('INSERT INTO items VALUES (?, ?)', (i, name))
                conn.commit()
            return db.read_bytes(), Path(f'{db}-wal').read_bytes()
        finally:
            conn.close()


WAL_DB, WAL_LOG = _wal_database()
# a container header: magic, u16be version, u32be record count
HEADER_BIN = b'CNTR' + struct.pack('>HI', 3, 42)

GUEST_FILES = {
    '/home/user/data/settings.json': json.dumps(DOC).encode(),
    '/home/user/logs/a.log': b'one\n',
    '/home/user/logs/b.log': b'two\n',
    '/home/user/logs/c.txt': b'not a log\n',
    '/home/user/notes.txt': b'secret token, another secret, SECRET',
    '/home/user/backup.zip': _zip(
        {
            'conf/app.json': json.dumps({'version': '2.4.1'}).encode(),
            'conf/stats.json': json.dumps({'first_ms': UNIX_S * 1000 + 1}).encode(),
        }
    ),
    '/home/user/data/settings.before.json': json.dumps({'items': DOC['items'][:2] + [{'ms': UNIX_S * 1000}]}).encode(),
    '/home/user/data/state.db': WAL_DB,
    '/home/user/data/state.db-wal': WAL_LOG,
    '/home/user/blobs.zip': _zip({'data/header.bin': HEADER_BIN}),
}

PLAYBOOK = """
variables:
  build: "2.4"
  cutoff: !timestamp {timestamp: '2024-01-02T03:00:00Z'}
  late_cutoff: !timestamp {timestamp: '2024-01-02T03:10:00Z'}
actions: []
tests:
  - name: json_count_regex
    function: json.value_count
    parameter:
      dst: /home/user/data/settings.json
      key_path: items[*].name
      expected_value: !re 'entry-\\d+'
      expected_count: 2
  - name: json_count_regex_mismatch
    function: json.value_count
    parameter:
      dst: /home/user/data/settings.json
      key_path: items[*].name
      expected_value: !re 'entry-\\d+'
      expected_count: 3
  - name: json_count_filetime
    function: json.value_count
    parameter:
      dst: /home/user/data/settings.json
      key_path: items[*].ts
      expected_value: !timestamp {timestamp: '1704164645', tolerance: 5, epoch: 1601, unit: 100ns}
      expected_count: 2
  - name: json_count_unix_ms
    function: json.value_count
    parameter:
      dst: /home/user/data/settings.json
      key_path: items[*].ms
      expected_value: !timestamp {timestamp: '1704164645', tolerance: [-1, 1], epoch: 1970, unit: ms}
      expected_count: 1
  - name: json_count_regex_with_variable
    function: json.value_count
    parameter:
      dst: /home/user/backup.zip!/conf/app.json
      key_path: version
      expected_value: !re '{{ build }}\\.\\d+'
      expected_count: 1
  - name: file_count_glob
    function: standard.file_count
    parameter:
      dst: /home/user/logs/*.log
      expected_count: 2
  - name: file_count_glob_mismatch
    function: standard.file_count
    parameter:
      dst: /home/user/logs/*
      expected_count: 2
  - name: occurrences
    function: text.occurrence_count
    parameter:
      dst: /home/user/notes.txt
      content: secret
      expected_count: 2
  - name: occurrences_caseless
    function: text.occurrence_count
    parameter:
      dst: /home/user/notes.txt
      content: secret
      case_sensitive: false
      expected_count: 3
  - name: archive_member
    function: json.value_matches
    parameter:
      dst: /home/user/backup.zip!/conf/app.json
      key_path: version
      expected_value: 2.4.1
  - name: archive_member_mapping
    function: json.value_matches
    parameter:
      dst: {archive: /home/user/backup.zip, member: conf/app.json}
      key_path: version
      expected_value: 9.9.9
  - name: archive_member_missing
    function: json.value_matches
    parameter:
      dst: /home/user/backup.zip!/conf/gone.json
      key_path: version
      expected_value: 2.4.1
  - name: missing_file
    function: json.value_count
    parameter:
      dst: /home/user/data/gone.json
      key_path: items[*]
      expected_count: 3
  - name: missing_archive
    function: json.value_matches
    parameter:
      dst: /home/user/gone.zip!/conf/app.json
      key_path: version
      expected_value: 2.4.1
  - name: saved_variable_ordered
    function: json.value_matches
    parameter:
      dst: /home/user/data/settings.json
      key_path: items[0].ms
      expected_value: "{{ ms_before }}"
      comparison_type: greater
  - name: saved_timestamp_ordered
    function: json.value_matches
    parameter:
      dst: /home/user/data/settings.json
      key_path: items[0].ms
      expected_value: "{{ started }}"
      comparison_type: greater
      timestamp_epoch: 1970
      timestamp_unit: ms
  - name: declared_timestamp_ordered
    function: json.value_matches
    parameter:
      dst: /home/user/data/settings.json
      key_path: items[0].ts
      expected_value: "{{ cutoff }}"
      comparison_type: greater
      timestamp_epoch: 1601
      timestamp_unit: 100ns
  - name: declared_timestamp_ordered_later
    function: json.value_matches
    parameter:
      dst: /home/user/data/settings.json
      key_path: items[0].ts
      expected_value: "{{ late_cutoff }}"
      comparison_type: greater
      timestamp_epoch: 1601
      timestamp_unit: 100ns
  - name: values_compare_other_dst
    function: json.values_compare
    parameter:
      dst: /home/user/data/settings.json
      key_path: items[2].ms
      other_dst: /home/user/data/settings.before.json
      other_key_path: items[2].ms
      comparison_type: greater
  - name: values_compare_other_archive_member
    function: json.values_compare
    parameter:
      dst: /home/user/data/settings.json
      key_path: items[0].ms
      other_dst: /home/user/backup.zip!/conf/stats.json
      other_key_path: first_ms
      comparison_type: less
  - name: sqlite_wal_added
    function: sqlite.row_count
    parameter:
      dst: /home/user/data/state.db
      query: SELECT id FROM items
      view: wal_added
      expected_count: 2
  - name: sqlite_main_file
    function: sqlite.row_count
    parameter:
      dst: /home/user/data/state.db
      query: SELECT id FROM items
      view: main_file
      expected_count: 1
  - name: wal_frames_of_the_wal_itself
    function: sqlite.wal_frame_count
    parameter:
      dst: /home/user/data/state.db-wal
      frames: commits
      expected_count: 2
  - name: struct_value_in_archive_member
    function: binary.struct_value_matches
    parameter:
      dst: /home/user/blobs.zip!/data/header.bin
      offset: 6
      value_format: u32be
      expected_value: 40
      comparison_type: greater
"""


class _EmptyGuestFS(GuestFS):
    """A base image with nothing in it: every path is missing."""

    origin = 'empty'

    def stat(self, path, follow=True):
        raise GuestFileNotFound(path)

    def listdir(self, path):
        raise GuestFileNotFound(path)

    def open(self, path):
        raise GuestFileNotFound(path)


class _Session:
    """What ``HostsideTestExecutor`` asks of a ``HostsideSession``."""

    def __init__(self, fs):
        self.fs = fs
        self.markers = SimpleNamespace(marker=lambda *args, **kwargs: None)

    def fs_for_test(self, test_name):
        return self.fs

    def state_of(self, test_name):
        return 'final'


@pytest.fixture(scope='module')
def collection():
    return import_basictest_subclasses(directory=TESTFUNCTIONS)


@pytest.fixture
def chain(tmp_path, monkeypatch, collection):
    """Run one playbook test by name through the host-mode chain; return the ActionResult."""
    state_dir = tmp_path / 'state'
    state_dir.mkdir()
    (state_dir / 'testfunctions').symlink_to(TESTFUNCTIONS, target_is_directory=True)
    monkeypatch.setattr('adare.config.configdirectory.STATE_DIR', state_dir)

    experiment_dir = tmp_path / 'experiment'
    experiment_dir.mkdir()
    (experiment_dir / 'playbook.yml').write_text(PLAYBOOK)
    playbook = parse_playbook(experiment_dir / 'playbook.yml')

    # as PlaybookController._initialize_modules: automatic variables merged into the user's, and
    # a Jinja environment with the registry's filters (the controller's _create_jinja_environment)
    automatic = AutomaticVariables.get_automatic_variables('linux', 'user')
    playbook.variables = AutomaticVariables.merge_with_user_variables(automatic, playbook.variables)
    jinja_env = test_loader.TestLoader(experiment_dir, tmp_path, playbook=playbook)._create_jinja_environment()
    resolver = VariableResolver(variable_registry=playbook.variables, jinja_env=jinja_env)
    loader = test_loader.TestLoader(experiment_dir, tmp_path, playbook=playbook, variable_resolver=resolver)

    fs = PatchedGuestFS(base=_EmptyGuestFS(), ops=[StagedOp('write', p, content=c) for p, c in GUEST_FILES.items()])
    executor = HostsideTestExecutor(_Session(fs), collection)
    actions = test_actions.TestActionsExecutor(experiment_run_directory=tmp_path, playbook=playbook)
    actions.set_test_loader(loader)
    actions.set_test_execution_mode(execution_base.TestExecutionMode.HOST)
    actions.set_guest_to_host_test_executor(executor)

    def run(name, context=None, saved_timestamps=None):
        """``context``: what save_variable / command capture put in the execution context;
        ``saved_timestamps``: {variable: unix seconds} saved as execute_save_timestamp saves them."""
        context = dict(context or {})
        for variable, unix_s in (saved_timestamps or {}).items():
            context[variable] = unix_s
            moment = datetime.datetime.fromtimestamp(unix_s, datetime.UTC)
            playbook.variables.add(variable, Variable(moment, VariableType.TIMESTAMP, metadata={'timezone': 'UTC'}))
        return asyncio.run(actions.execute_test(ActionTestAction(name=name), None, None, execution_context=context))

    yield run
    executor.cleanup()


def _status(result):
    assert result.data is not None, result.message
    return result.data['result']['status']


@pytest.mark.parametrize(
    ('name', 'status'),
    [
        ('json_count_regex', StatusEnum.SUCCESS),
        ('json_count_regex_mismatch', StatusEnum.FAILED),
        ('json_count_filetime', StatusEnum.SUCCESS),
        ('json_count_unix_ms', StatusEnum.SUCCESS),
        ('file_count_glob', StatusEnum.SUCCESS),
        ('file_count_glob_mismatch', StatusEnum.FAILED),
        ('occurrences', StatusEnum.SUCCESS),
        ('occurrences_caseless', StatusEnum.SUCCESS),
        ('archive_member', StatusEnum.SUCCESS),
        ('archive_member_mapping', StatusEnum.FAILED),
        ('archive_member_missing', StatusEnum.ERROR),
        ('missing_file', StatusEnum.ERROR),
        ('missing_archive', StatusEnum.ERROR),
        ('declared_timestamp_ordered', StatusEnum.SUCCESS),
        ('declared_timestamp_ordered_later', StatusEnum.FAILED),
        ('values_compare_other_dst', StatusEnum.SUCCESS),
        ('values_compare_other_archive_member', StatusEnum.SUCCESS),
        ('sqlite_wal_added', StatusEnum.SUCCESS),
        ('sqlite_main_file', StatusEnum.SUCCESS),
        ('wal_frames_of_the_wal_itself', StatusEnum.SUCCESS),
        ('struct_value_in_archive_member', StatusEnum.SUCCESS),
    ],
)
def test_playbook_test_verdict(chain, name, status):
    result = chain(name)

    assert _status(result) == status, result.message
    assert result.success is (status == StatusEnum.SUCCESS)


def test_variable_inside_regex_is_resolved(chain):
    # build = "2.4", so the pattern {{ build }}\.\d+ should match the member's version "2.4.1"
    assert _status(chain('json_count_regex_with_variable')) == StatusEnum.SUCCESS


def test_placeholder_metadata_reaches_the_testfunction(tmp_path, monkeypatch, chain):
    """The !re tag arrives as a ``{{ placeholder }}`` plus metadata, not as a literal string."""
    seen = {}
    original = HostsideTestExecutor.execute_test

    async def spy(self, test_name, test_function, test_instance):
        seen['expected_value'] = test_instance.parameter.expected_value
        seen['metadata'] = dict(test_instance.variable_metadata or {})
        return await original(self, test_name, test_function, test_instance)

    monkeypatch.setattr(HostsideTestExecutor, 'execute_test', spy)

    assert _status(chain('json_count_filetime')) == StatusEnum.SUCCESS
    placeholder = seen['expected_value'].strip('{} ')
    assert seen['metadata'][placeholder]['type'] == 'timestamp'
    assert seen['metadata'][placeholder]['epoch'] == 1601
    assert seen['metadata'][placeholder]['unit'] == '100ns'


def test_file_count_reports_guest_paths(chain):
    result = chain('file_count_glob')

    details = ' '.join(result.data['result']['details'])
    assert '/home/user/logs/a.log, /home/user/logs/b.log' in details
    assert 'adare_count_' not in details and 'adare_hostside_test_' not in details


def test_missing_file_is_named_in_the_error(chain):
    details = ' '.join(chain('missing_file').data['result']['details'])

    assert 'gone.json' in details


def test_dst_is_restored_after_the_run(chain, monkeypatch):
    """The executor rewrites dst to its local copy and must put the guest path back."""
    instances = []
    original = HostsideTestExecutor.execute_test

    async def spy(self, test_name, test_function, test_instance):
        instances.append(test_instance)
        return await original(self, test_name, test_function, test_instance)

    monkeypatch.setattr(HostsideTestExecutor, 'execute_test', spy)

    chain('archive_member')
    chain('occurrences')

    assert [i.parameter.dst for i in instances] == ['/home/user/backup.zip!/conf/app.json', '/home/user/notes.txt']


def _guest_access(monkeypatch):
    """Record the guest paths pulled and probed through the GuestFS proxy."""
    seen = {'pulled': [], 'probed': []}
    original_pull = GuestFSFileProxy.pull_file
    original_exists = GuestFSFileProxy.file_exists

    async def pull_file(self, guest_path, force=False):
        seen['pulled'].append(guest_path)
        return await original_pull(self, guest_path, force=force)

    async def file_exists(self, guest_path):
        seen['probed'].append(guest_path)
        return await original_exists(self, guest_path)

    monkeypatch.setattr(GuestFSFileProxy, 'pull_file', pull_file)
    monkeypatch.setattr(GuestFSFileProxy, 'file_exists', file_exists)
    return seen


def test_wal_view_pulls_the_database_and_its_wal_once(chain, monkeypatch):
    seen = _guest_access(monkeypatch)

    assert _status(chain('sqlite_wal_added')) == StatusEnum.SUCCESS
    assert sorted(seen['pulled']) == ['/home/user/data/state.db', '/home/user/data/state.db-wal']


def test_wal_given_as_dst_has_no_companion_probes(chain, monkeypatch):
    seen = _guest_access(monkeypatch)

    assert _status(chain('wal_frames_of_the_wal_itself')) == StatusEnum.SUCCESS
    assert seen['pulled'] == ['/home/user/data/state.db-wal']
    assert not [p for p in seen['probed'] if p.endswith(('-wal-wal', '-wal-journal'))]


def test_values_compare_pulls_both_files(chain, monkeypatch):
    seen = _guest_access(monkeypatch)

    result = chain('values_compare_other_dst')

    assert _status(result) == StatusEnum.SUCCESS, result.message
    assert sorted(seen['pulled']) == ['/home/user/data/settings.before.json', '/home/user/data/settings.json']


def test_other_dst_is_restored_after_the_run(chain, monkeypatch):
    instances = []
    original = HostsideTestExecutor.execute_test

    async def spy(self, test_name, test_function, test_instance):
        instances.append(test_instance)
        return await original(self, test_name, test_function, test_instance)

    monkeypatch.setattr(HostsideTestExecutor, 'execute_test', spy)

    chain('values_compare_other_archive_member')

    assert instances[0].parameter.other_dst == '/home/user/backup.zip!/conf/stats.json'


def test_values_compare_details_name_guest_paths(chain):
    details = ' '.join(chain('values_compare_other_archive_member').data['result']['details'])

    assert '/home/user/data/settings.json' in details and '/home/user/backup.zip!/conf/stats.json' in details
    assert 'adare_hostside_test_' not in details


def test_saved_variable_reaches_an_ordered_comparison(chain):
    """save_variable / capture values are filled in before the test runs; unset is an ERROR."""
    assert _status(chain('saved_variable_ordered', {'ms_before': UNIX_S * 1000 - 1})) == StatusEnum.SUCCESS
    assert _status(chain('saved_variable_ordered', {'ms_before': UNIX_S * 1000})) == StatusEnum.FAILED
    unset = chain('saved_variable_ordered')  # never saved: the template cannot be rendered, the test is ERROR
    assert unset.data['test_status'] == 'ERROR'
    assert 'ms_before' in unset.data['result']['details'][0]


def test_saved_timestamp_reaches_an_ordered_comparison(chain, monkeypatch):
    """A save_timestamp variable arrives as a placeholder with timestamp metadata and is compared in order."""
    seen = {}
    original = HostsideTestExecutor.execute_test

    async def spy(self, test_name, test_function, test_instance):
        seen['expected_value'] = test_instance.parameter.expected_value
        seen['metadata'] = dict(test_instance.variable_metadata or {})
        return await original(self, test_name, test_function, test_instance)

    monkeypatch.setattr(HostsideTestExecutor, 'execute_test', spy)

    before = chain('saved_timestamp_ordered', saved_timestamps={'started': UNIX_S - 60})
    after = chain('saved_timestamp_ordered', saved_timestamps={'started': UNIX_S + 60})

    assert _status(before) == StatusEnum.SUCCESS, before.data['result']['details']
    assert _status(after) == StatusEnum.FAILED, after.data['result']['details']
    placeholder = seen['expected_value'].strip('{} ')
    assert seen['metadata'][placeholder]['type'] == 'timestamp'
