"""Undefine-flag policy for libvirt domains: what survives a redefine, and what does not.

ADARE undefines and redefines the same libvirt domain constantly — on every VM
start (the XML is rebuilt each time), on every cold-boot retry, and at the end of
every run — while the *instance* behind it is long-lived and reused. Two pieces of
per-instance firmware state live outside the disk image and are therefore governed
by undefine flags rather than by the overlay:

**UEFI NVRAM varstore.** Carries the guest's boot entries, including the aarch64
Shell-boot pre-population. Kept across redefines; deleted only on instance removal.

**Emulated TPM state** (``<tpm model='tpm-tis'><backend type='emulator'/>``).
libvirt stores it under ``~/.config/libvirt/qemu/swtpm/<domain-uuid>/``, and what
happens to it on undefine depends on one XML attribute this module does not
control: ``persistent_state`` on the ``<backend>`` element
(``adare.hypervisor.qemu.libvirt_xml_builder``).

* **``persistent_state`` unset (libvirt's default).** The state is treated as
  ephemeral and is **deleted on any undefine, regardless of which undefineFlags
  are passed** — ``KEEP_TPM`` has no effect. This was ADARE's behaviour before
  the backend element gained ``persistent_state='yes'``: every Windows cold boot,
  including every cold-boot retry, got a brand-new vTPM (new EK, new SRK, cleared
  owner auth) because ``swtpm_setup`` manufactures one on every define.
* **``persistent_state='yes'`` (ADARE's current XML).** The state survives
  undefine **by default**; ``KEEP_TPM`` is now what makes that explicit for a
  redefine, and the destructive ``TPM`` flag is required to actually delete it.
  This is the state this module's flag selection assumes.

Either way, a domain UUID that is not stable across runs of the same environment
defeats this: swtpm keys the state directory by UUID, so a fresh UUID per run
means "kept" state is simply orphaned under a UUID nothing points at again
(see ``ConfigurationMixin._domain_uuid_for``, which derives the UUID from the
environment rather than randomizing it per run).

An irreproducible-per-boot vTPM is wrong for two independent reasons:

* **Reproducibility.** ADARE exists to make guest artifacts comparable across
  runs. A TPM identity that is different on every boot makes every TPM-derived
  artifact (owner auth, TPM-bound keys, PCR measurements, ``Get-Tpm`` output)
  irreproducible by construction, and inconsistent with the sealed base image.
* **Fidelity.** A real machine has exactly one TPM for its lifetime.

The flag constants are looked up with ``getattr``: ``KEEP_TPM`` / ``TPM`` need
libvirt 8.9+, and an older libvirt-python must degrade to the previous behaviour
rather than raise ``AttributeError``. That degradation is believed correct for
this host (libvirt-python 12.1.0, where both constants exist) but has not been
exercised against an older libvirt-python here — it is untested, not proven.
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
    return (
        _flag('MANAGED_SAVE')
        | _flag('SNAPSHOTS_METADATA')
        | _flag('NVRAM')
        | _flag('TPM')
    )


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
