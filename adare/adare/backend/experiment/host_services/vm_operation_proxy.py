"""Base class for QGA-based proxy objects that communicate with guest VMs."""


class VMOperationProxy:
    """Base class for proxy objects that execute operations on a guest VM via QGA.

    Provides shared initialization (VM reference, OS detection) and
    async context manager protocol for resource cleanup.
    """

    def __init__(self, vm, guest_os: str):
        self.vm = vm
        self.guest_os = guest_os
        self.is_windows = 'windows' in guest_os.lower()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

    def cleanup(self):
        """Override in subclasses that need resource cleanup."""
        pass
