"""Content-hash versioned agent wheels and the guest skip-installation check."""

import shutil
import subprocess
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from adare.backend.experiment import agent_installer, agent_wheels

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[6]


def _package(root: Path, name: str, version: str = '0.1.1', extra: str = '') -> Path:
    pkg = root / name
    (pkg / name).mkdir(parents=True)
    (pkg / name / '__init__.py').write_text('VALUE = 1\n')
    (pkg / 'README.md').write_text(name)
    (pkg / 'pyproject.toml').write_text(
        f'[project]\nname = "{name}"\nversion = "{version}"\nreadme = "README.md"\n'
        f'requires-python = ">=3.10"\n{extra}\n'
        '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    )
    return pkg


class TestSourceHash:
    def test_stable_for_identical_trees(self, tmp_path):
        a = _package(tmp_path / 'a', 'adarelib')
        b = _package(tmp_path / 'b', 'adarelib')
        assert agent_wheels.source_hash(a) == agent_wheels.source_hash(b)

    def test_changes_with_content(self, tmp_path):
        pkg = _package(tmp_path, 'adarelib')
        before = agent_wheels.source_hash(pkg)
        (pkg / 'adarelib' / '__init__.py').write_text('VALUE = 2\n')
        assert agent_wheels.source_hash(pkg) != before

    def test_changes_with_file_name(self, tmp_path):
        pkg = _package(tmp_path, 'adarelib')
        before = agent_wheels.source_hash(pkg)
        (pkg / 'adarelib' / '__init__.py').rename(pkg / 'adarelib' / 'other.py')
        assert agent_wheels.source_hash(pkg) != before

    def test_ignores_caches_and_build_output(self, tmp_path):
        pkg = _package(tmp_path, 'adarelib')
        before = agent_wheels.source_hash(pkg)
        for junk in ('__pycache__/x.cpython-313.pyc', '.venv/lib/x.py', 'dist/x.whl', 'x.egg-info/PKG-INFO'):
            (pkg / junk).parent.mkdir(parents=True, exist_ok=True)
            (pkg / junk).write_text('junk')
        (pkg / 'adarelib' / 'stray.pyc').write_bytes(b'\0')
        (pkg / '.DS_Store').write_bytes(b'\0')
        assert agent_wheels.source_hash(pkg) == before


class TestVersions:
    def test_expected_version_is_base_plus_hash(self, tmp_path):
        pkg = _package(tmp_path, 'adarevm', version='0.2.0')
        digest = agent_wheels.source_hash(pkg)[: agent_wheels.HASH_LENGTH]
        assert agent_wheels.expected_version(pkg) == f'0.2.0+g{digest}'

    def test_wheel_versions_parses_local_versions(self, tmp_path):
        (tmp_path / 'adarelib-0.1.1+gabc123def456-py3-none-any.whl').touch()
        (tmp_path / 'adarevm-0.1.1-py3-none-any.whl').touch()
        assert agent_wheels.wheel_versions(tmp_path) == {'adarelib': '0.1.1+gabc123def456', 'adarevm': '0.1.1'}

    def test_wheel_versions_missing_dir(self, tmp_path):
        assert agent_wheels.wheel_versions(tmp_path / 'nope') == {}

    def test_build_rewrites_version_and_restores_pyproject(self, tmp_path, monkeypatch):
        pkg = _package(tmp_path, 'adarevm', extra='[tool.uv.sources]\nadarelib = { workspace = true }\n')
        original = (pkg / 'pyproject.toml').read_text()
        expected = agent_wheels.expected_version(pkg)
        seen = {}

        def fake_run(cmd, cwd, **kwargs):
            seen['pyproject'] = (Path(cwd) / 'pyproject.toml').read_text()

        monkeypatch.setattr(agent_wheels.subprocess, 'run', fake_run)
        agent_wheels.build_agent_wheels({'adarevm': pkg}, tmp_path / 'wheels')

        assert f'version = "{expected}"' in seen['pyproject']
        assert 'workspace' not in seen['pyproject']
        assert (pkg / 'pyproject.toml').read_text() == original

    def test_build_restores_pyproject_on_failure(self, tmp_path, monkeypatch):
        pkg = _package(tmp_path, 'adarelib')
        original = (pkg / 'pyproject.toml').read_text()

        def failing_run(cmd, cwd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd)

        monkeypatch.setattr(agent_wheels.subprocess, 'run', failing_run)
        with pytest.raises(subprocess.CalledProcessError):
            agent_wheels.build_agent_wheels({'adarelib': pkg}, tmp_path / 'wheels')
        assert (pkg / 'pyproject.toml').read_text() == original

    @pytest.mark.skipif(shutil.which('uv') is None, reason='uv not on PATH')
    def test_real_uv_build_of_agent_packages(self, tmp_path):
        """Build the real adarelib/adarevm sources and check the wheel metadata versions."""
        dirs = {}
        for name in agent_wheels.AGENT_PACKAGES:
            dirs[name] = tmp_path / name
            shutil.copytree(REPO_ROOT / name, dirs[name], ignore=shutil.ignore_patterns('__pycache__', '.venv'))

        built = agent_wheels.build_agent_wheels(dirs, tmp_path / 'wheels')

        assert set(built) == set(agent_wheels.AGENT_PACKAGES)
        assert agent_wheels.wheels_up_to_date(dirs, tmp_path / 'wheels')
        for name, wheel in built.items():
            version = agent_wheels.expected_version(dirs[name])
            with zipfile.ZipFile(wheel) as zf:
                metadata = zf.read(f'{name}-{version}.dist-info/METADATA').decode()
            assert f'Version: {version}' in metadata

        (dirs['adarelib'] / 'adarelib' / '__init__.py').write_text('# changed\n', encoding='utf-8')
        assert not agent_wheels.wheels_up_to_date(dirs, tmp_path / 'wheels')


class _FakeVM:
    """Answers ``pip show <pkg>`` from a dict of installed versions."""

    def __init__(self, installed: dict[str, str]):
        self.installed = installed
        self.commands: list[str] = []

    async def run_command(self, cmd, stop_event=None, **kwargs):
        self.commands.append(cmd)
        pkg = cmd.rsplit(' ', 1)[-1]
        if pkg not in self.installed:
            return SimpleNamespace(returncode=1, stdout='')
        return SimpleNamespace(returncode=0, stdout=f'Name: {pkg}\nVersion: {self.installed[pkg]}\n')


LIB = '0.1.1+gaaaaaaaaaaaa'
VM = '0.1.1+gbbbbbbbbbbbb'


@pytest.fixture
def wheels_dir(tmp_path):
    (tmp_path / f'adarelib-{LIB}-py3-none-any.whl').touch()
    (tmp_path / f'adarevm-{VM}-py3-none-any.whl').touch()
    return tmp_path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('installed', 'skip'),
    [
        ({'adarelib': LIB, 'adarevm': VM}, True),
        ({}, False),
        ({'adarevm': VM}, False),
        ({'adarelib': LIB}, False),
        # guests provisioned before content hashing reinstall once
        ({'adarelib': '0.1.1', 'adarevm': '0.1.1'}, False),
        # each package is compared with its own wheel, not adarevm's
        ({'adarelib': VM, 'adarevm': VM}, False),
        ({'adarelib': LIB, 'adarevm': '0.1.1+gcccccccccccc'}, False),
    ],
)
async def test_should_skip_installation_matrix(wheels_dir, installed, skip):
    vm = _FakeVM(installed)
    result = await agent_installer.should_skip_installation(wheels_dir, vm, False, 'linux', threading.Event())
    assert result is skip


@pytest.mark.asyncio
async def test_should_skip_requires_both_wheels(tmp_path):
    (tmp_path / f'adarevm-{VM}-py3-none-any.whl').touch()
    vm = _FakeVM({'adarelib': LIB, 'adarevm': VM})
    assert await agent_installer.should_skip_installation(tmp_path, vm, False, 'linux', threading.Event()) is False
    assert vm.commands == []


class TestRuntimeCopyStaleness:
    """The project's vm_runtime copy is refreshed by content, not by mtime."""

    def test_copy_with_newer_mtime_but_old_content_is_stale(self, tmp_path):
        import os

        from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager

        source = _package(tmp_path / 'src', 'adarevm', version='0.2.0')
        target = _package(tmp_path / 'copy', 'adarevm', version='0.1.1')
        # A wheel build rewrites the copy's pyproject, leaving it newer than every source file.
        later = (source / 'pyproject.toml').stat().st_mtime + 3600
        os.utime(target / 'pyproject.toml', (later, later))

        assert VMLifecycleManager._runtime_copy_stale(source, target)

    def test_identical_copy_ignoring_build_output_is_fresh(self, tmp_path):
        from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager

        source = _package(tmp_path / 'src', 'adarevm')
        target = tmp_path / 'copy' / 'adarevm'
        shutil.copytree(source, target)
        (target / '__pycache__').mkdir()
        (target / '__pycache__' / 'x.pyc').write_bytes(b'\0')

        assert not VMLifecycleManager._runtime_copy_stale(source, target)
