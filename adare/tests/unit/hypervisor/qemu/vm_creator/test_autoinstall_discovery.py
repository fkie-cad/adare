"""Tests for self-describing autoinstall template discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from adare.hypervisor.qemu.vm_creator import autoinstall, os_catalog
from adare.hypervisor.qemu.vm_creator.autoinstall import (
    TemplateMetadata,
    discover_templates,
    parse_template_metadata,
    resolve_template,
)


_VALID_FRONTMATTER = """\
{# adare-template
schema: 1
id: ubuntu-test
description: Test fixture
maintainer: tester
revision: 2026-05-06
supports:
  - testos1
  - testos2
#}
#cloud-config
autoinstall:
  version: 1
"""


def _write(dir_: Path, name: str, body: str) -> Path:
    p = dir_ / name
    p.write_text(body)
    return p


@pytest.fixture(autouse=True)
def _reset_discovery_cache():
    """Each test starts with a clean discovery cache."""
    autoinstall._DISCOVERY_CACHE = None
    yield
    autoinstall._DISCOVERY_CACHE = None


def test_parse_returns_expected_fields(tmp_path: Path):
    p = _write(tmp_path, 'good.yaml', _VALID_FRONTMATTER)
    meta = parse_template_metadata(p)

    assert isinstance(meta, TemplateMetadata)
    assert meta.id == 'ubuntu-test'
    assert meta.description == 'Test fixture'
    assert meta.supports == ('testos1', 'testos2')
    assert meta.schema == 1
    assert meta.maintainer == 'tester'
    assert meta.revision == '2026-05-06'
    assert meta.path == p


def test_parse_returns_none_when_no_frontmatter(tmp_path: Path):
    p = _write(tmp_path, 'plain.yaml', '#cloud-config\nautoinstall:\n  version: 1\n')
    assert parse_template_metadata(p) is None


def test_parse_unknown_schema_raises(tmp_path: Path):
    body = _VALID_FRONTMATTER.replace('schema: 1', 'schema: 99')
    p = _write(tmp_path, 'bad.yaml', body)
    with pytest.raises(ValueError, match='schema'):
        parse_template_metadata(p)


def test_parse_invalid_supports_raises(tmp_path: Path):
    body = _VALID_FRONTMATTER.replace('  - testos1\n  - testos2', '  testos1: 42')
    p = _write(tmp_path, 'bad.yaml', body)
    with pytest.raises(ValueError, match='supports'):
        parse_template_metadata(p)


def test_discover_user_dir_overrides_builtin(tmp_path: Path):
    builtin = tmp_path / 'builtin'
    user = tmp_path / 'user'
    builtin.mkdir()
    user.mkdir()

    _write(builtin, 'builtin.yaml', _VALID_FRONTMATTER)
    user_body = _VALID_FRONTMATTER.replace(
        'id: ubuntu-test', 'id: user-override'
    )
    _write(user, 'user.yaml', user_body)

    discovered = discover_templates(builtin, user)

    assert discovered['testos1'].id == 'user-override'
    assert discovered['testos2'].id == 'user-override'
    assert discovered['testos1'].path.parent == user


def test_discover_conflicting_builtins_raise(tmp_path: Path):
    body_a = _VALID_FRONTMATTER.replace('id: ubuntu-test', 'id: a')
    body_b = _VALID_FRONTMATTER.replace('id: ubuntu-test', 'id: b')
    _write(tmp_path, 'a.yaml', body_a)
    _write(tmp_path, 'b.yaml', body_b)

    with pytest.raises(ValueError, match='Conflicting'):
        discover_templates(tmp_path)


def test_discover_skips_files_without_frontmatter(tmp_path: Path):
    _write(tmp_path, 'plain.yaml', '#cloud-config\n')
    _write(tmp_path, 'good.yaml', _VALID_FRONTMATTER)

    discovered = discover_templates(tmp_path)

    assert set(discovered) == {'testos1', 'testos2'}


def test_resolve_template_explicit_field_wins(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(autoinstall, 'TEMPLATES_DIR', tmp_path)
    monkeypatch.setattr(autoinstall, 'VM_TEMPLATES_DIR', tmp_path / '__nonexistent__')
    autoinstall._DISCOVERY_CACHE = None

    os_def = os_catalog.OS_CATALOG['ubuntu2404']
    explicit = os_def.__class__(**{**os_def.__dict__, 'template': 'my_explicit.yaml'})
    assert resolve_template(explicit) == 'my_explicit.yaml'


def test_resolve_template_uses_discovered_map(tmp_path: Path, monkeypatch):
    _write(tmp_path, 'foo.yaml', _VALID_FRONTMATTER)
    monkeypatch.setattr(autoinstall, 'TEMPLATES_DIR', tmp_path)
    monkeypatch.setattr(autoinstall, 'VM_TEMPLATES_DIR', tmp_path / '__nonexistent__')
    autoinstall._DISCOVERY_CACHE = None

    fake_def = os_catalog.OS_CATALOG['ubuntu2404'].__class__(
        **{
            **os_catalog.OS_CATALOG['ubuntu2404'].__dict__,
            'name': 'testos1',
            'distribution': 'testos',
            'template': '',
        }
    )
    assert resolve_template(fake_def) == 'foo.yaml'


def test_resolve_template_distribution_fallback(tmp_path: Path, monkeypatch):
    _write(tmp_path, 'foo.yaml', _VALID_FRONTMATTER)
    monkeypatch.setattr(autoinstall, 'TEMPLATES_DIR', tmp_path)
    monkeypatch.setattr(autoinstall, 'VM_TEMPLATES_DIR', tmp_path / '__nonexistent__')
    autoinstall._DISCOVERY_CACHE = None

    # An OS not in `supports:` but whose distribution matches by prefix.
    fallback_def = os_catalog.OS_CATALOG['ubuntu2404'].__class__(
        **{
            **os_catalog.OS_CATALOG['ubuntu2404'].__dict__,
            'name': 'testosUnknown',
            'distribution': 'testos',
            'template': '',
        }
    )
    assert resolve_template(fallback_def) == 'foo.yaml'


def test_render_strips_frontmatter_comment():
    """Generated user-data must not leak the {# adare-template ... #} block."""
    os_def = os_catalog.OS_CATALOG['ubuntu2404']
    rendered = autoinstall.generate_user_data(os_def, 'unit-test-vm')

    assert 'adare-template' not in rendered
    assert '{#' not in rendered
    # cloud-init still finds its sentinel on the very first non-empty line.
    first_line = rendered.lstrip().splitlines()[0]
    assert first_line == '#cloud-config'


def test_discovery_covers_all_linux_auto_profiles():
    """Every catalog entry that needs an autoinstall has either an explicit
    template or a discovered/prefix-matched one."""
    discovered = discover_templates(autoinstall.TEMPLATES_DIR)
    for os_def in os_catalog.OS_CATALOG.values():
        if os_def.platform != 'linux' or os_def.install_mode == 'manual':
            continue
        if os_def.template:
            continue
        if os_def.name in discovered:
            continue
        prefix_matches = [k for k in discovered if k.startswith(os_def.distribution)]
        assert prefix_matches, f'No template can serve {os_def.name}'
