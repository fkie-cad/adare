"""Tests for consumer-side ISO resolution (T14) and gate 5.

`resolve_byo_iso` is the only thing standing between a published recipe and
"cannot find the ISO", so its search order and its error text are the whole
user-facing experience of a BYO environment.
"""

import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from adare.backend.environment.exceptions import EnvironmentLoadFailed
from adare.backend.vm import recipe_iso
from adare.backend.vm.recipe_iso import ISO_DIR_ENV, resolve_byo_iso, verify_iso
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition
from adare.types.environment import Recipe

ISO_NAME = 'Win11_25H2_English_Arm64_v2.iso'


# --- Helpers ---

def _os_def(**overrides) -> OsDefinition:
    defaults = dict(
        name='windows11arm64', display_name='Windows 11 (ARM64)', platform='windows',
        distribution='windows', version='11', iso_url='', iso_sha256='',
        iso_filename='', default_disk_size='160G', default_ram_mb=8192,
        default_cpus=4, architecture='aarch64',
        iso_notes='Download from microsoft.com/software-download/windows11',
    )
    defaults.update(overrides)
    return OsDefinition(**defaults)


def _recipe(**overrides) -> Recipe:
    defaults = dict(
        profile='windows11arm64', iso_sha256='a' * 64, iso_name=ISO_NAME,
    )
    defaults.update(overrides)
    return Recipe(**defaults)


def _write_iso(directory: Path, name: str = ISO_NAME, content: bytes = b'ISO BYTES') -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(content)
    return path


@pytest.fixture
def iso_dirs(tmp_path, monkeypatch):
    """Isolate all five search locations under tmp_path."""
    dirs = {
        'env': tmp_path / 'env-iso-dir',
        'iso': tmp_path / 'dot-adare-isos',
        'base': tmp_path / 'environment-file-dir',
        'cache': tmp_path / 'qemu-cache',
        'explicit': tmp_path / 'explicit',
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(recipe_iso, 'ISO_DIR', dirs['iso'])
    monkeypatch.setattr(recipe_iso, 'QEMU_CACHE_DIR', dirs['cache'])
    monkeypatch.delenv(ISO_DIR_ENV, raising=False)
    return dirs


# --- T14: search order, first existing file wins ---

def test_explicit_iso_file_wins(iso_dirs):
    """--iso FILE is honoured whatever it is named; the digest decides correctness."""
    explicit = _write_iso(iso_dirs['explicit'], 'renamed-by-the-user.iso')
    _write_iso(iso_dirs['iso'])
    found = resolve_byo_iso(_recipe(), _os_def(), iso_override=explicit,
                            base_dir=iso_dirs['base'])
    assert found == explicit


def test_explicit_iso_directory_is_searched_by_name(iso_dirs):
    expected = _write_iso(iso_dirs['explicit'])
    _write_iso(iso_dirs['iso'])
    found = resolve_byo_iso(_recipe(), _os_def(), iso_override=iso_dirs['explicit'],
                            base_dir=iso_dirs['base'])
    assert found == expected


def test_env_var_dir_beats_iso_dir(iso_dirs, monkeypatch):
    monkeypatch.setenv(ISO_DIR_ENV, str(iso_dirs['env']))
    expected = _write_iso(iso_dirs['env'])
    _write_iso(iso_dirs['iso'])
    assert resolve_byo_iso(_recipe(), _os_def(), base_dir=iso_dirs['base']) == expected


def test_iso_dir_beats_environment_file_dir(iso_dirs):
    expected = _write_iso(iso_dirs['iso'])
    _write_iso(iso_dirs['base'])
    assert resolve_byo_iso(_recipe(), _os_def(), base_dir=iso_dirs['base']) == expected


def test_environment_file_dir_beats_cache(iso_dirs):
    """Matches how a local relative `recipe.iso` path already resolves."""
    expected = _write_iso(iso_dirs['base'])
    _write_iso(iso_dirs['cache'])
    assert resolve_byo_iso(_recipe(), _os_def(), base_dir=iso_dirs['base']) == expected


def test_qemu_cache_is_the_last_resort(iso_dirs):
    """A consumer who already built the URL form of this ISO gets a hit."""
    expected = _write_iso(iso_dirs['cache'])
    assert resolve_byo_iso(_recipe(), _os_def(), base_dir=iso_dirs['base']) == expected


def test_missing_explicit_override_falls_through_to_the_search(iso_dirs):
    """A bad --iso must not shadow an ISO that IS present in a standard location."""
    expected = _write_iso(iso_dirs['iso'])
    found = resolve_byo_iso(_recipe(), _os_def(),
                            iso_override=iso_dirs['explicit'] / 'nope.iso',
                            base_dir=iso_dirs['base'])
    assert found == expected


def test_no_base_dir_is_tolerated(iso_dirs):
    expected = _write_iso(iso_dirs['iso'])
    assert resolve_byo_iso(_recipe(), _os_def(), base_dir=None) == expected


def test_a_lone_unrelated_iso_in_iso_dir_is_not_used(iso_dirs):
    """Never guess. Silently building from the wrong ISO must not be possible."""
    _write_iso(iso_dirs['iso'], 'some-other-windows.iso')
    with pytest.raises(EnvironmentLoadFailed):
        resolve_byo_iso(_recipe(), _os_def(), base_dir=iso_dirs['base'])


# --- T14: traversal rejected before touching the filesystem ---

@pytest.mark.parametrize('bad_name', [
    '../../etc/passwd',
    '../Win11.iso',
    'sub/dir/w.iso',
    'sub\\dir\\w.iso',
    '/absolute/Win11.iso',
    'C:\\ISO\\Win11.iso',
    'https://example.com/Win11.iso',
    'Win11.img',
    'Win11',
    '',
    '   ',
    '.iso',
    '-leading-dash.iso',
    'x' * 250 + '.iso',
])
def test_invalid_iso_name_is_rejected(iso_dirs, bad_name):
    with pytest.raises(EnvironmentLoadFailed, match='bare ISO filename'):
        resolve_byo_iso(_recipe(iso_name=bad_name), _os_def(), base_dir=iso_dirs['base'])


def test_traversal_is_rejected_before_any_filesystem_access(iso_dirs, monkeypatch):
    """The name check must precede path construction, not follow it."""
    def _explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError('filesystem was touched for an invalid iso_name')

    monkeypatch.setattr(Path, 'is_file', _explode)
    monkeypatch.setattr(Path, 'is_dir', _explode)
    with pytest.raises(EnvironmentLoadFailed):
        resolve_byo_iso(_recipe(iso_name='../../etc/passwd'), _os_def(),
                        base_dir=iso_dirs['base'])


@pytest.mark.parametrize('good_name', [
    'Win11_25H2_English_Arm64_v2.iso',
    'ubuntu-24.04.4-live-server-arm64.iso',
    'a.iso',
    'X+Y_1.2.3-final.iso',
])
def test_valid_bare_filenames_are_accepted(iso_dirs, good_name):
    expected = _write_iso(iso_dirs['iso'], good_name)
    found = resolve_byo_iso(_recipe(iso_name=good_name), _os_def(),
                            base_dir=iso_dirs['base'])
    assert found == expected


# --- T14: the not-found error is the whole UX ---

def test_not_found_error_names_the_file_digest_profile_and_every_path(iso_dirs, monkeypatch):
    monkeypatch.setenv(ISO_DIR_ENV, str(iso_dirs['env']))
    with pytest.raises(EnvironmentLoadFailed) as excinfo:
        resolve_byo_iso(_recipe(iso_sha256='b' * 64), _os_def(),
                        base_dir=iso_dirs['base'])
    message = str(excinfo.value)
    assert ISO_NAME in message
    assert 'b' * 64 in message
    assert 'windows11arm64' in message
    for directory in (iso_dirs['env'], iso_dirs['iso'], iso_dirs['base'], iso_dirs['cache']):
        assert str(directory / ISO_NAME) in message


def test_not_found_error_uses_the_publishers_iso_notes(iso_dirs):
    recipe = _recipe(iso_notes='Get it from the intranet share \\\\fileserver\\isos')
    with pytest.raises(EnvironmentLoadFailed) as excinfo:
        resolve_byo_iso(recipe, _os_def(), base_dir=iso_dirs['base'])
    assert 'intranet share' in str(excinfo.value)


def test_not_found_error_falls_back_to_the_profile_iso_notes(iso_dirs):
    """A publisher who omitted iso_notes must not leave the consumer with nothing."""
    with pytest.raises(EnvironmentLoadFailed) as excinfo:
        resolve_byo_iso(_recipe(iso_notes=''), _os_def(), base_dir=iso_dirs['base'])
    assert 'microsoft.com/software-download/windows11' in str(excinfo.value)


def test_not_found_error_suggests_all_three_supply_routes(iso_dirs):
    with pytest.raises(EnvironmentLoadFailed) as excinfo:
        resolve_byo_iso(_recipe(), _os_def(), base_dir=iso_dirs['base'])
    solutions = ' '.join(getattr(excinfo.value, 'possible_solutions', []))
    assert str(iso_dirs['iso']) in solutions
    assert '--iso' in solutions
    assert ISO_DIR_ENV in solutions
    assert 'shasum -a 256' in solutions


# --- digest verification ---

def test_verify_iso_accepts_a_matching_digest(tmp_path):
    content = b'the real iso bytes'
    iso = tmp_path / ISO_NAME
    iso.write_bytes(content)
    verify_iso(_recipe(iso_sha256=hashlib.sha256(content).hexdigest()), iso)


def test_verify_iso_accepts_an_uppercase_declared_digest(tmp_path):
    """Normalized on read, so an uppercase digest is buildable rather than a trap."""
    content = b'the real iso bytes'
    iso = tmp_path / ISO_NAME
    iso.write_bytes(content)
    verify_iso(_recipe(iso_sha256=hashlib.sha256(content).hexdigest().upper()), iso)


def test_verify_iso_rejects_a_mismatch_and_names_both_digests(tmp_path):
    content = b'the wrong iso'
    iso = tmp_path / ISO_NAME
    iso.write_bytes(content)
    with pytest.raises(EnvironmentLoadFailed) as excinfo:
        verify_iso(_recipe(iso_sha256='c' * 64), iso)
    message = str(excinfo.value)
    assert 'c' * 64 in message
    assert hashlib.sha256(content).hexdigest() in message


def test_empty_iso_sha256_hard_fails_even_on_an_existing_file(tmp_path):
    """`verify_iso_hash` returns True for an empty expectation.

    Reaching it with no declared digest would therefore "verify" any file at all,
    so the missing-digest check must come first.
    """
    iso = tmp_path / ISO_NAME
    iso.write_bytes(b'anything')
    with pytest.raises(EnvironmentLoadFailed, match='iso_sha256'):
        verify_iso(_recipe(iso_sha256=''), iso)


def test_missing_file_is_reported_as_missing(tmp_path):
    with pytest.raises(EnvironmentLoadFailed, match='not found'):
        verify_iso(_recipe(), tmp_path / 'absent.iso')


# --- gate 5: BYO is Windows-only on the consumer side too ---

def test_byo_over_a_linux_profile_is_rejected_at_consume_time(tmp_path):
    """An honestly-declared Linux BYO recipe is refused: publish the ISO instead."""
    from adare.backend.vm.recipe import build_or_reuse_recipe_vm
    from adare.types.environment import EnvironmentMetadata, OsInfo

    metadata = EnvironmentMetadata(
        vm_type='recipe',
        recipe=Recipe(profile='ubuntu2404', iso_sha256='d' * 64,
                      iso_name='ubuntu-24.04-live-server-amd64.iso'),
        os=OsInfo(os='Ubuntu', platform='linux', distribution='ubuntu'),
    )
    with pytest.raises(EnvironmentLoadFailed) as excinfo:
        build_or_reuse_recipe_vm(metadata, base_dir=tmp_path)
    message = str(excinfo.value)
    assert 'Windows profiles only' in message
    # The error names the exact URL to use, not merely that BYO is forbidden.
    assert 'releases.ubuntu.com' in message


def test_spoofed_windows_platform_over_a_linux_profile_is_rejected_at_consume_time(tmp_path):
    """The spoof that gets past server ingest dies on every consumer.

    Gate 4 (server) cannot resolve profile -> platform — it has no OS catalog — so
    a publisher can claim `os.platform: windows` over `profile: ubuntu2404` and be
    ingested. Gate 5 catches it here, so the spoof buys an environment nobody can
    build. It is caught by the platform-mismatch rule rather than the BYO rule,
    which is the more precise complaint.
    """
    from adare.backend.vm.recipe import build_or_reuse_recipe_vm
    from adare.types.environment import EnvironmentMetadata, OsInfo

    metadata = EnvironmentMetadata(
        vm_type='recipe',
        recipe=Recipe(profile='ubuntu2404', iso_sha256='d' * 64,
                      iso_name='ubuntu-24.04-live-server-amd64.iso'),
        os=OsInfo(os='Ubuntu', platform='windows', distribution='ubuntu'),
    )
    with pytest.raises(EnvironmentLoadFailed, match='does not build'):
        build_or_reuse_recipe_vm(metadata, base_dir=tmp_path)


def test_platform_mismatch_is_rejected_at_consume_time(tmp_path):
    """The file must not describe a system it does not build."""
    from adare.backend.vm.recipe import build_or_reuse_recipe_vm
    from adare.types.environment import EnvironmentMetadata, OsInfo

    metadata = EnvironmentMetadata(
        vm_type='recipe',
        recipe=Recipe(profile='ubuntu2404', iso_sha256='d' * 64,
                      iso='https://releases.ubuntu.com/24.04/x.iso'),
        os=OsInfo(os='Windows 11', platform='windows', distribution='Home'),
    )
    with pytest.raises(EnvironmentLoadFailed, match='does not build'):
        build_or_reuse_recipe_vm(metadata, base_dir=tmp_path)


def test_a_local_iso_path_is_fine_for_a_consumer(tmp_path, monkeypatch):
    """`publishing=False` on consume: only publishing insists on a URL."""
    from adare.services.recipe_contract import check_recipe_publish_contract

    recipe = Recipe(profile='windows11arm64', iso_sha256='e' * 64,
                    iso='/Users/someone/ISO/Win11.iso')
    check_recipe_publish_contract(recipe, 'windows', publishing=False)
    with pytest.raises(Exception, match='http'):
        check_recipe_publish_contract(recipe, 'windows', publishing=True)


def test_a_non_canonical_digest_is_fine_for_a_consumer_but_not_for_a_publisher(tmp_path):
    """Consumers normalize on read; publishers must emit canonical form.

    The server stores `iso_sha256` verbatim and older clients compare it
    case-sensitively, so an uppercase digest is buildable here and unbuildable
    for whoever downloads it.
    """
    from adare.services.recipe_contract import check_recipe_publish_contract

    recipe = Recipe(profile='windows11arm64', iso_sha256='E' * 64,
                    iso='https://files.example.org/Win11.iso')
    check_recipe_publish_contract(recipe, 'windows', publishing=False)
    with pytest.raises(Exception, match='canonical'):
        check_recipe_publish_contract(recipe, 'windows', publishing=True)
