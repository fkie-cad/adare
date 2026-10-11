"""
The contract between ``VirtualBoxVM`` and its mixins.

The mixins read state that ``VirtualBoxVM.__init__`` sets up and call methods
defined on ``VirtualBoxVM`` or on sibling mixins. They subclass
``VirtualBoxVMHost`` for type checking only (plain ``object`` at runtime), so
mypy checks every such use against the declarations below.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any

from adare.hypervisor.base.vm import AbstractVM

if TYPE_CHECKING:
    from adare.hypervisor.executable_manager import ExecutableManager
    from adare.hypervisor.virtualbox.manager import VirtualBoxManager


class VirtualBoxVMHost(AbstractVM):
    """State and methods the VirtualBox mixins rely on (implemented by ``VirtualBoxVM``)."""

    vm_name: str
    guest_os: str
    username: str
    password: str
    cpus: int
    ram: int
    network: str
    host_os: str
    executables: ExecutableManager
    vboxmanage_exe: str
    manager: VirtualBoxManager
    _background_pids: list[int]
    _command_queue: list[Any]

    # Implemented by VirtualBoxVM / CommandExecutionMixin; gradual signatures
    # (*args: Any, **kwargs: Any) accept the concrete ones.
    @abstractmethod
    def vm_exists(self) -> bool: ...

    def queue_command(self, *args: Any, **kwargs: Any) -> Any: ...

    def clear_command_queue(self) -> Any: ...

    async def execute_queued_commands(self, *args: Any, **kwargs: Any) -> Any: ...

    async def create_from_ovf_or_ova(self, *args: Any, **kwargs: Any) -> Any: ...

    def _execute_streaming_command(self, *args: Any, **kwargs: Any) -> Any: ...

    async def _execute_streaming_command_async(self, *args: Any, **kwargs: Any) -> Any: ...

    def _build_guest_command_args(self, *args: Any, **kwargs: Any) -> Any: ...
