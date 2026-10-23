"""Undefine-flag policy (adare.hypervisor.qemu.libvirt_undefine) against a fake domain.

A run redefines its domain on every start and removes it at the end. A redefine
must keep the run's UEFI varstore and vTPM copy (libvirt refuses a flagless
undefine of a domain with <nvram/>, and would otherwise reset the TPM mid-run);
removing the run's domain must take both with it, or every run leaks a varstore
file and a swtpm directory. No libvirtd and no VM are involved.
"""

import libvirt
import pytest

from adare.hypervisor.qemu.libvirt_undefine import delete_firmware_state_flags, keep_firmware_state_flags, undefine

pytestmark = pytest.mark.unit

KEEP_NVRAM = libvirt.VIR_DOMAIN_UNDEFINE_KEEP_NVRAM
NVRAM = libvirt.VIR_DOMAIN_UNDEFINE_NVRAM
# KEEP_TPM / TPM need libvirt-python 8.9+; 0 makes the TPM assertions vacuous on older bindings.
KEEP_TPM = getattr(libvirt, 'VIR_DOMAIN_UNDEFINE_KEEP_TPM', 0)
TPM = getattr(libvirt, 'VIR_DOMAIN_UNDEFINE_TPM', 0)


class FakeDomain:
    """Records undefine flags; rejects an undefine that neither keeps nor deletes an existing varstore."""

    def __init__(self, *, has_nvram: bool = True):
        self.has_nvram = has_nvram
        self.undefine_flags_calls: list[int] = []

    def undefineFlags(self, flags):  # noqa: N802 - mirrors the libvirt API name
        if self.has_nvram and not flags & (KEEP_NVRAM | NVRAM):
            raise libvirt.libvirtError('Cannot undefine domain with NVRAM')
        self.undefine_flags_calls.append(flags)


class FakeDomainWithoutUndefineFlags:
    """Ancient libvirt-python: no undefineFlags at all."""

    def __init__(self):
        self.plain_undefine_calls = 0

    def undefine(self):
        self.plain_undefine_calls += 1


def test_redefine_keeps_varstore_and_vtpm():
    domain = FakeDomain()
    undefine(domain, keep_firmware_state_flags())

    (flags,) = domain.undefine_flags_calls
    assert flags & KEEP_NVRAM and not flags & NVRAM
    assert flags & KEEP_TPM == KEEP_TPM and not flags & TPM


def test_run_removal_deletes_varstore_and_vtpm_copy():
    domain = FakeDomain()
    undefine(domain, delete_firmware_state_flags())

    (flags,) = domain.undefine_flags_calls
    assert flags & NVRAM and not flags & KEEP_NVRAM
    assert flags & TPM == TPM and not flags & KEEP_TPM


def test_bios_domain_without_varstore_undefines_either_way():
    domain = FakeDomain(has_nvram=False)
    undefine(domain, keep_firmware_state_flags())
    undefine(domain, delete_firmware_state_flags())

    assert len(domain.undefine_flags_calls) == 2


def test_flagless_fallback_when_undefineflags_is_missing():
    domain = FakeDomainWithoutUndefineFlags()
    undefine(domain, delete_firmware_state_flags())

    assert domain.plain_undefine_calls == 1


def test_other_libvirt_errors_propagate():
    class Failing(FakeDomain):
        def undefineFlags(self, flags):  # noqa: N802 - mirrors the libvirt API name
            raise libvirt.libvirtError('unexpected failure')

    with pytest.raises(libvirt.libvirtError):
        undefine(Failing(), delete_firmware_state_flags())
