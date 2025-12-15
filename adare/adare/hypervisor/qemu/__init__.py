"""QEMU hypervisor implementation for ADARE."""

def register():
    """Register QEMU hypervisor with the factory."""
    from adare.hypervisor import register_hypervisor
    from adare.hypervisor.qemu.manager import QEMUManager
    from adare.hypervisor.qemu.vm import QEMUVM

    register_hypervisor('qemu', QEMUManager, QEMUVM)
