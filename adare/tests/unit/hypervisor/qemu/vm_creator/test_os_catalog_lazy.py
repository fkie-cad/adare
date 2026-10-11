"""The OS catalog is built on first use, cached, and rebuilt by reload_catalog()."""

import pytest

from adare.hypervisor.qemu.vm_creator import os_catalog

pytestmark = pytest.mark.unit


def test_os_catalog_name_still_resolves_to_the_cached_catalog():
    from adare.hypervisor.qemu.vm_creator.os_catalog import OS_CATALOG

    assert OS_CATALOG is os_catalog.OS_CATALOG is os_catalog._catalog()
    assert os_catalog.get_os_definition('ubuntu2404') is OS_CATALOG['ubuntu2404']
    assert [d.name for d in os_catalog.list_os_definitions()] == sorted(OS_CATALOG)


def test_reload_catalog_picks_up_new_profiles(tmp_path, monkeypatch):
    before = os_catalog.OS_CATALOG
    (tmp_path / 'lazytest.yml').write_text('name: lazytest\nplatform: linux\ndistribution: ubuntu\nversion: "24.04"\n')
    monkeypatch.setattr(os_catalog, 'OS_PROFILES_DIR', tmp_path)
    assert 'lazytest' not in os_catalog.OS_CATALOG  # still the cached build

    os_catalog.reload_catalog()
    try:
        assert os_catalog.OS_CATALOG is not before
        assert os_catalog.get_os_definition('lazytest').version == '24.04'
    finally:
        monkeypatch.undo()
        os_catalog.reload_catalog()


def test_unknown_module_attribute_still_raises():
    with pytest.raises(AttributeError):
        os_catalog.NOT_A_THING  # noqa: B018
