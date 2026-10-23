"""Undefine-flag policy for libvirt domains: what survives a redefine, and what does not.

A QEMU experiment run defines one libvirt domain, redefines it on every start
(the XML is rebuilt each time, including every cold-boot retry) and removes it at
the end of the run. Two pieces of firmware state live outside the disk image and
are governed by undefine flags rather than by the run overlay:

**UEFI NVRAM varstore** (``<run>-nvram.fd``) carries the guest's boot entries,
including the aarch64 Shell-boot pre-population.

**Emulated TPM state** lives under ``~/.config/libvirt/qemu/swtpm/<domain-uuid>/``.
Each run boots a *copy* of its environment's vTPM template under the run's own
domain UUID (see :mod:`adare.hypervisor.qemu.run_resources`), so runs keep one
stable TPM identity without sharing -- or mutating -- each other's TPM state.
What happens to it on undefine depends on ``persistent_state`` on the
``<backend>`` element (``libvirt_xml_builder``): unset, libvirt deletes it on any
undefine regardless of flags; ADARE sets ``persistent_state='yes'``, so it
survives by default, ``KEEP_TPM`` makes that explicit for a redefine and the
``TPM`` flag deletes it.

Hence :func:`keep_firmware_state_flags` for a redefine within a run, and
:func:`delete_firmware_state_flags` when the run's domain is removed.

The flag constants are looked up with ``getattr``: ``KEEP_TPM`` / ``TPM`` need
libvirt 8.9+, and an older libvirt-python degrades to the flags it has rather
than raising ``AttributeError``.
"""

import logging

log = logging.getLogger(__name__)


def _flag(name: str) -> int:
    """Value of ``libvirt.VIR_DOMAIN_UNDEFINE_<name>``, or 0 if unsupported."""
    import libvirt

    return getattr(libvirt, f'VIR_DOMAIN_UNDEFINE_{name}', 0)


def keep_firmware_state_flags() -> int:
    """Flags for a redefine: preserve the instance's NVRAM varstore and vTPM."""
    return _flag('KEEP_NVRAM') | _flag('KEEP_TPM')


def delete_firmware_state_flags() -> int:
    """Flags for instance removal: take the NVRAM varstore and vTPM with it.

    Without ``TPM`` the swtpm state directory outlives the instance it belonged
    to, one orphan per removed Windows VM.
    """
    return _flag('MANAGED_SAVE') | _flag('SNAPSHOTS_METADATA') | _flag('NVRAM') | _flag('TPM')


def undefine(domain, flags: int) -> None:
    """``domain.undefineFlags(flags)``, degrading instead of failing.

    Two degradations, both deliberate:

    * ``AttributeError`` — a libvirt-python too old to have ``undefineFlags`` at
      all. A flagless ``undefine()`` still works for BIOS domains.
    * ``libvirtError`` naming an unsupported flag — a libvirt daemon older than
      the bindings. Retry without the TPM bits so the undefine itself still
      happens; the vTPM state is then handled as it was before, which is the
      status quo rather than a new failure.

    Any other ``libvirtError`` propagates: the caller decides how to report it.
    """
    import libvirt

    try:
        domain.undefineFlags(flags)
        return
    except AttributeError:
        domain.undefine()
        return
    except libvirt.libvirtError as e:
        tpm_flags = _flag('KEEP_TPM') | _flag('TPM')
        if not tpm_flags or not (flags & tpm_flags) or 'flag' not in str(e).lower():
            raise
        log.debug(f"undefineFlags({flags}) rejected ({e}); retrying without the TPM flags")
        domain.undefineFlags(flags & ~tpm_flags)
