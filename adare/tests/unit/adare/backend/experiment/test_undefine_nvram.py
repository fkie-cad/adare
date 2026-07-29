"""Tests for `_undefine_keeping_firmware_state` in adare.backend.experiment.vm_lifecycle_manager.

A UEFI domain declares <nvram/>, and libvirt refuses a flagless undefine() on it
("Cannot undefine domain with NVRAM/varstore"), which used to leave one stale
defined-but-shutoff domain behind per aarch64 run. These tests pin the flag selection
against a mocked libvirt domain: no libvirtd connection and no VM are involved.

They also pin the second piece of instance-scoped firmware state, the emulated TPM.
libvirt DELETES the swtpm state on undefine unless KEEP_TPM is passed, so omitting it
made every Windows cold boot — including every cold-boot retry — manufacture a fresh
vTPM for the guest to re-provision. That is invisible from the host except in the
swtpm log, which is exactly why it needs a test rather than a comment.
"""

import libvirt
import pytest

pytestmark = pytest.mark.unit

from adare.backend.experiment.vm_lifecycle_manager import _undefine_keeping_firmware_state

KEEP_BOTH = (
    libvirt.VIR_DOMAIN_UNDEFINE_KEEP_NVRAM | libvirt.VIR_DOMAIN_UNDEFINE_KEEP_TPM
)


class FakeDomain:
    """Duck-typed virDomain recording the flags it was undefined with.

    ``has_nvram`` reproduces libvirt's own precondition: with an nvram varstore
    present, a call that specifies neither KEEP_NVRAM nor NVRAM fails.
    """

    def __init__(self, *, has_nvram: bool):
        self.has_nvram = has_nvram
        self.undefine_flags_calls: list[int] = []
        self.plain_undefine_calls = 0

    def undefineFlags(self, flags):  # noqa: N802 - mirrors the libvirt API name
        if self.has_nvram and not flags & (
            libvirt.VIR_DOMAIN_UNDEFINE_KEEP_NVRAM | libvirt.VIR_DOMAIN_UNDEFINE_NVRAM
        ):
            raise libvirt.libvirtError('Cannot undefine domain with NVRAM')
        self.undefine_flags_calls.append(flags)

    def undefine(self):
        if self.has_nvram:
            raise libvirt.libvirtError('Cannot undefine domain with NVRAM')
        self.plain_undefine_calls += 1


class FakeDomainWithoutUndefineFlags:
    """Ancient libvirt-python: the domain object genuinely has no undefineFlags."""

    def __init__(self):
        self.plain_undefine_calls = 0

    def undefine(self):
        self.plain_undefine_calls += 1


class TestFlagSelection:
    def test_aarch64_experiment_domain_with_nvram_keeps_the_varstore(self):
        """The leaking case: UEFI/aarch64 run domain must undefine and KEEP its nvram.

        The varstore is instance-scoped (<instance>-nvram.fd beside the instance's base
        disk) and this teardown releases the instance for reuse, so deleting it would
        reset a reusable instance's UEFI boot entries.
        """
        domain = FakeDomain(has_nvram=True)
        _undefine_keeping_firmware_state(domain)

        assert domain.undefine_flags_calls == [KEEP_BOTH]
        assert domain.plain_undefine_calls == 0

    def test_never_passes_the_destructive_nvram_flag(self):
        """VIR_DOMAIN_UNDEFINE_NVRAM would delete the varstore file — must never be set."""
        domain = FakeDomain(has_nvram=True)
        _undefine_keeping_firmware_state(domain)

        (flags,) = domain.undefine_flags_calls
        assert not flags & libvirt.VIR_DOMAIN_UNDEFINE_NVRAM

    def test_base_vm_varstore_survives_this_path(self):
        """A base/pooled VM's nvram is part of the image and must outlive the undefine.

        Same assertion as above from the caller's point of view: this path can only ever
        ask libvirt to keep the file, so it cannot destroy a base image's firmware state
        no matter which domain it is handed.
        """
        domain = FakeDomain(has_nvram=True)
        _undefine_keeping_firmware_state(domain)

        assert domain.undefine_flags_calls == [KEEP_BOTH]

    def test_x86_bios_domain_without_nvram_still_undefines(self):
        """KEEP_NVRAM is inert for a BIOS domain, so x86 guests do not regress."""
        domain = FakeDomain(has_nvram=False)
        _undefine_keeping_firmware_state(domain)

        assert domain.undefine_flags_calls == [KEEP_BOTH]
        assert domain.plain_undefine_calls == 0

    def test_vtpm_state_survives_so_the_guest_keeps_one_tpm_identity(self):
        """Without KEEP_TPM libvirt deletes the swtpm state and the next define
        manufactures a new vTPM, so the guest re-provisions its TPM on every cold
        boot — irreproducible by construction, and unlike a real machine.
        """
        domain = FakeDomain(has_nvram=True)
        _undefine_keeping_firmware_state(domain)

        (flags,) = domain.undefine_flags_calls
        assert flags & libvirt.VIR_DOMAIN_UNDEFINE_KEEP_TPM
        assert not flags & libvirt.VIR_DOMAIN_UNDEFINE_TPM

    def test_flagless_fallback_when_undefineflags_is_missing(self):
        """Very old libvirt-python: fall back to undefine() rather than crashing."""
        domain = FakeDomainWithoutUndefineFlags()
        _undefine_keeping_firmware_state(domain)

        assert domain.plain_undefine_calls == 1

    def test_libvirt_error_propagates_to_the_caller(self):
        """The caller distinguishes 'already gone' from a real leak, so errors must escape."""
        class Failing(FakeDomain):
            def undefineFlags(self, flags):  # noqa: N802 - mirrors the libvirt API name
                raise libvirt.libvirtError('unexpected failure')

        with pytest.raises(libvirt.libvirtError):
            _undefine_keeping_firmware_state(Failing(has_nvram=True))


class TestRegressionAgainstThePlainUndefine:
    def test_plain_undefine_would_have_failed_on_the_uefi_domain(self):
        """Pins the bug being fixed: the pre-fix call is rejected for a UEFI domain."""
        domain = FakeDomain(has_nvram=True)
        with pytest.raises(libvirt.libvirtError, match='NVRAM'):
            domain.undefine()
        assert domain.plain_undefine_calls == 0
