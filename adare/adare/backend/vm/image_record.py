"""The record of a VM image: what a disk is, how it was built, what ran on it.

A VM image (a registered VM) is identified by its disk's sha256 and never
changes. Its record travels with it: a ``<disk stem>.image.yml`` sidecar next to
the disk, cached in ``Vm.build_record``, embedded as ``image:`` in a published
environment file, and copied into every run directory. It is a record, not a
recipe: nothing is rebuilt from it.

Schema (``record_version: 1``)::

    record_version: 1
    sha256: <disk sha256>              # the image's identity
    format: qcow2
    hypervisor: qemu
    os: {os, platform, distribution, version, language, architecture}
    build:                             # null when the origin is unknown
      method: playbook                 # install_mode: playbook | auto | manual | gui-auto | recipe
      installer: gui                   # subiquity | kickstart | ... (auto installs)
      created: 2026-10-24T13:25:00Z
      profile: ubuntu2604
      profile_sha256: <hash of the resolved OS profile>
      iso: {filename, sha256}
      setup: full                      # bare | base | full
      adare: {version, commit}
      qemu: 8.2.2
    packages: {count, sha256, file}    # guest package list next to the disk (Linux)
    published:                         # where it is hosted (sha256 differs for a compressed copy)
      - {url, sha256}
    checks:                            # runs on exactly this disk
      - {run: vm test, date: 2026-10-24T13:27:00Z, result: pass}
"""

import dataclasses
import hashlib
import json
import logging
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

RECORD_VERSION = 1

# Linux guests: "name version" per installed package, sorted. Empty output on a
# guest without dpkg or rpm.
PACKAGE_LIST_COMMAND = (
    "if command -v dpkg-query >/dev/null 2>&1; then dpkg-query -W -f='${Package} ${Version}\\n'; "
    "elif command -v rpm >/dev/null 2>&1; then rpm -qa --qf '%{NAME} %{VERSION}-%{RELEASE}\\n'; fi | sort"
)


def record_path(disk: Path) -> Path:
    return disk.with_name(f'{disk.stem}.image.yml')


def packages_path(disk: Path) -> Path:
    return disk.with_name(f'{disk.stem}.packages.txt')


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def write_packages(disk: Path, package_list: str) -> None:
    """Store the guest's package list next to *disk* (``<stem>.packages.txt``)."""
    lines = sorted(line.strip() for line in package_list.splitlines() if line.strip())
    packages_path(disk).write_text(''.join(f'{line}\n' for line in lines), encoding='utf-8')


def _packages_entry(disk: Path) -> dict | None:
    path = packages_path(disk)
    if not path.is_file():
        return None
    data = path.read_bytes()
    return {'count': data.count(b'\n'), 'sha256': hashlib.sha256(data).hexdigest(), 'file': path.name}


def adare_identity() -> dict:
    """ADARE's version, and the git commit when it runs from a checkout ('+dirty' if modified)."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        adare_version = version('adare')
    except PackageNotFoundError:
        adare_version = None
    commit = None
    source = Path(__file__).resolve().parent
    git = shutil.which('git')
    if git:
        try:
            head = subprocess.run(
                [git, '-C', str(source), 'rev-parse', '--short=12', 'HEAD'],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            ).stdout.strip()
            dirty = subprocess.run(
                [git, '-C', str(source), 'status', '--porcelain', '--untracked-files=no'],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            ).stdout.strip()
            commit = f'{head}+dirty' if dirty else head
        except (OSError, subprocess.SubprocessError):
            commit = None  # not a git checkout (an installed copy)
    return {'version': adare_version, 'commit': commit}


def qemu_version(architecture: str) -> str | None:
    """The host QEMU's version for *architecture* ('x86_64' / 'aarch64'), None if not found."""
    binary = shutil.which(f'qemu-system-{architecture}')
    if not binary:
        return None
    try:
        first = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=10).stdout.split('\n')[0]
    except (OSError, subprocess.SubprocessError):
        return None
    words = first.split()
    return words[words.index('version') + 1] if 'version' in words[:-1] else first or None


def profile_sha256(os_def: Any) -> str:
    """Hash of the resolved OS profile (ISO, steps, templates ...), whatever file it came from."""
    content = json.dumps(dataclasses.asdict(os_def), sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()


def build_entry(
    *, os_def: Any, setup_level: Any, iso_filename: str | None, iso_sha256: str | None, method: str | None = None
) -> dict:
    """The ``build:`` entry for a disk built here from *os_def*."""
    return {
        'method': method or os_def.install_mode,
        'installer': os_def.installer,
        'created': now(),
        'profile': os_def.name,
        'profile_sha256': profile_sha256(os_def),
        'iso': {'filename': iso_filename, 'sha256': iso_sha256},
        'setup': setup_level.name.lower(),
        'adare': adare_identity(),
        'qemu': qemu_version(os_def.architecture),
    }


def new_record(
    *, disk: Path, sha256: str, hypervisor: str, os_block: dict, build: dict | None, disk_format: str | None = None
) -> dict:
    return {
        'record_version': RECORD_VERSION,
        'sha256': sha256,
        'format': disk_format or disk.suffix.lstrip('.') or None,
        'hypervisor': hypervisor,
        'os': os_block,
        'build': build,
        'packages': _packages_entry(disk),
        'published': [],
        'checks': [],
    }


def write_record(disk: Path, record: dict) -> Path:
    """Write *record* as the sidecar of *disk*; returns its path."""
    path = record_path(disk)
    path.write_text(yaml.safe_dump(record, sort_keys=False), encoding='utf-8')
    return path


def read_record(disk: Path) -> dict | None:
    path = record_path(disk)
    if not path.is_file():
        return None
    try:
        record = yaml.safe_load(path.read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError) as e:
        log.warning(f'Could not read image record {path}: {e}')
        return None
    return record if isinstance(record, dict) else None


def to_json(record: dict | None) -> str | None:
    return json.dumps(record, sort_keys=False) if record is not None else None


def from_json(text: str | None) -> dict | None:
    if not text:
        return None
    try:
        record = json.loads(text)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def store(vm_id: str, disk: Path | None, record: dict) -> None:
    """Persist *record* for a registered image: in the database, and as the disk's sidecar."""
    from adare.backend.vm import database as vm_database

    vm_database.set_vm_build_record(vm_id, to_json(record))
    if disk is not None and disk.parent.is_dir():
        try:
            write_record(disk, record)
        except OSError as e:
            log.warning(f'Could not write image record next to {disk}: {e}')


def record_of(vm_ref: str) -> tuple[dict, dict] | None:
    """The registered image *vm_ref* (name, id or hash) and its record.

    An image registered without a record (loaded before records existed, or from
    a disk of unknown origin) gets a minimal one from its row: ``build: null``.
    """
    from adare.backend.vm import database as vm_database

    image = vm_database.get_image(vm_ref)
    if image is None:
        return None
    record = from_json(image['build_record']) or new_record(
        disk=Path(image['file']), sha256=image['hash'], hypervisor=image['hypervisor'], os_block=image['os'], build=None
    )
    return image, record


def add_published(vm_ref: str, url: str, sha256: str) -> dict | None:
    """Record that the image *vm_ref* is hosted at *url* (as bytes hashing to *sha256*); returns the record."""
    found = record_of(vm_ref)
    if found is None:
        return None
    image, record = found
    published = [entry for entry in record.get('published') or [] if entry.get('url') != url]
    record['published'] = [*published, {'url': url, 'sha256': sha256}]
    store(image['id'], Path(image['file']), record)
    return record


def for_published_disk(record: dict, sha256: str, disk_format: str | None) -> dict:
    """The record to embed for a published disk: a compressed copy is a new image derived from *record*'s."""
    if sha256 == record.get('sha256'):
        return record
    derived = {**record, 'sha256': sha256, 'format': disk_format or record.get('format'), 'checks': []}
    derived['derived_from'] = {'sha256': record.get('sha256'), 'by': 'zstd compression'}
    return derived


def import_from_environment(vm_id: str, record: dict) -> None:
    """Adopt the ``image:`` record of a loaded environment file for its registered disk.

    Only when it describes these bytes and the image has no record of its own.
    """
    from adare.backend.vm import database as vm_database

    image = vm_database.get_image(vm_id)
    if image is None or image['build_record']:
        return
    if record.get('sha256') != image['hash']:
        log.warning(
            f"Ignoring the environment's image record: it describes disk {str(record.get('sha256'))[:12]}..., "
            f"not the registered {image['hash'][:12]}..."
        )
        return
    store(vm_id, Path(image['file']), record)


def add_check(vm_ref: str, run: str, passed: bool) -> None:
    """Append a check on a registered image (e.g. ``vm test``) to its record."""
    found = record_of(vm_ref)
    if found is None:
        return
    image, record = found
    record.setdefault('checks', []).append({'run': run, 'date': now(), 'result': 'pass' if passed else 'fail'})
    store(image['id'], Path(image['file']), record)


def run_snapshot(environment_ulid: str) -> dict:
    """What a run ran on: its environment version and that version's image record."""
    from adare.database.api.environment import EnvironmentDbApi

    with EnvironmentDbApi() as db:
        env = db.get_environment_by_ulid(environment_ulid)
        if env is None:
            return {'environment': {'id': environment_ulid}, 'image': None}
        environment = {'name': env.name, 'id': env.id, 'file_sha256': env.sha256hash, 'vm_hash': env.vm_hash}
        vm_id = env.vm_id
    found = record_of(vm_id) if vm_id else None
    return {'environment': environment, 'image': found[1] if found else None}


def write_run_snapshot(path: Path, environments: dict[str | None, str | None]) -> None:
    """Write ``image.yml`` of a run: per machine, its environment version and image record."""
    machines = [{'machine': key, **run_snapshot(ulid)} for key, ulid in environments.items() if ulid]
    path.write_text(
        yaml.safe_dump({'record_version': RECORD_VERSION, 'machines': machines}, sort_keys=False), encoding='utf-8'
    )
