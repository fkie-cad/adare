"""
The contract between ``QEMUVM`` and its mixins.

The mixins are not usable on their own: they read state that ``QEMUVM.__init__``
sets up and call methods defined on ``QEMUVM`` or on sibling mixins. They
subclass ``QEMUVMHost`` for type checking only (plain ``object`` at runtime),
so mypy checks every such use against the declarations below; anything new a
mixin needs from its host is declared here first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adare.hypervisor.base.vm import AbstractVM

if TYPE_CHECKING:
    from adare.hypervisor.executable_manager import ExecutableManager
    from adare.hypervisor.qemu.manager import QEMUManager
    from adare.hypervisor.qemu.models import QEMUVMConfig


class QEMUVMHost(AbstractVM):
    """State and methods the QEMU mixins rely on (implemented by ``QEMUVM``)."""

    vm_name: str
    guest_os: str
    architecture: str
    username: str
    password: str
    cpus: int
    ram: int
    machine: str
    accel: str
    drive_format: str
    host_os: str
    manager: QEMUManager
    executables: ExecutableManager
    config: QEMUVMConfig
    _libvirt_conn: Any
    _libvirt_domain: Any
    _cached_guest_path: str | None
    _path_discovery_attempted: bool
    _hypervisor_config: dict[str, Any]

    def _ensure_libvirt_domain(self) -> Any: ...

    def _save_vm_config(self) -> None: ...
