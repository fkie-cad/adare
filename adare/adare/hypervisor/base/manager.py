"""
Abstract Hypervisor Manager for thread-safe VM operations.

All hypervisor implementations must provide a manager that implements
thread-safe queued operations for VM management.
"""
import logging
import queue
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class AbstractHypervisorManager(ABC):
    """
    Abstract base class for hypervisor managers.

    All hypervisor implementations MUST implement thread-safe queued operations.
    This enforces consistency and prevents race conditions across all hypervisors.
    """

    def __init__(self):
        """
        Initialize the hypervisor manager with thread-safe queue.

        Subclasses should call super().__init__() and then start their worker thread.
        """
        self._cmd_queue = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        log.debug(f"{self.__class__.__name__} initialized and worker thread started.")

    @abstractmethod
    def _worker_loop(self):
        """
        Main worker loop for executing queued functions.

        This method runs in a separate thread and processes commands from the queue.
        Implementations must:
        1. Continuously get items from self._cmd_queue
        2. Execute the function with provided args/kwargs
        3. Put results back into the result_queue
        4. Handle exceptions appropriately

        Example implementation:
            while True:
                func, args, kwargs, result_queue = self._cmd_queue.get()
                try:
                    result = func(*args, **kwargs)
                    result_queue.put((result, None))
                except Exception as e:
                    result_queue.put((None, e))
        """
        pass

    @abstractmethod
    def run(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function in the worker thread and return its result (synchronous).

        Args:
            func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result from the function execution

        Raises:
            Any exception raised by the function

        Example implementation:
            result_queue = queue.Queue()
            self._cmd_queue.put((func, args, kwargs, result_queue))
            result, error = result_queue.get()
            if error:
                raise error
            return result
        """
        pass

    @abstractmethod
    async def run_async(self, func: Callable, *args, **kwargs) -> Any:
        """
        Run an async function directly without the worker thread.

        Args:
            func: Async function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result from the async function execution

        Raises:
            Any exception raised by the function

        Example implementation:
            return await func(*args, **kwargs)
        """
        pass

    @abstractmethod
    async def import_vm_async(
        self,
        vm_file_path: Path,
        vm_name: str,
        environment_ulid: str | None = None
    ):
        """
        Import a VM from OVF/OVA file asynchronously.

        This is a high-level operation that:
        1. Creates a VM instance
        2. Imports from the provided file
        3. Registers the VM with the hypervisor

        Args:
            vm_file_path: Path to the OVF/OVA file
            vm_name: Name for the imported VM
            environment_ulid: Optional environment ULID for context

        Returns:
            VM instance (hypervisor-specific VM class)

        Raises:
            VMImportException: If import fails
        """
        pass
