"""
VirtualBox Manager for handling VirtualBox operations in a thread-safe manner.
"""
import asyncio
import logging
import queue
import threading
from typing import Any, Callable

log = logging.getLogger(__name__)


class VirtualBoxManager:
    """Thread-safe manager for VirtualBox operations."""
    
    def __init__(self):
        self._cmd_queue = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        log.debug("VirtualBoxManager initialized and worker thread started.")

    def _worker_loop(self):
        """Main worker loop for executing queued functions."""
        log.debug("VirtualBoxManager worker loop started.")
        while True:
            func, args, kwargs, result_queue = self._cmd_queue.get()
            try:
                log.debug(f"Executing function {func.__name__} with args={args} kwargs={kwargs}")
                result = func(*args, **kwargs)
                result_queue.put((result, None))
            except Exception as e:
                log.error(f"Exception in worker loop for function {func.__name__}: {e}")
                result_queue.put((None, e))

    def run(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function in the worker thread and return its result."""
        log.debug(f"Queueing function {func.__name__} for execution.")
        result_queue = queue.Queue()
        self._cmd_queue.put((func, args, kwargs, result_queue))
        result, error = result_queue.get()
        if error:
            log.error(f"Error running function {func.__name__}: {error}")
            raise error
        log.debug(f"Function {func.__name__} executed successfully.")
        return result

    async def run_async(self, func: Callable, *args, **kwargs) -> Any:
        """Run an async function directly without the worker thread."""
        log.debug(f"Executing async function {func.__name__} with args={args} kwargs={kwargs}")
        try:
            result = await func(*args, **kwargs)
            log.debug(f"Async function {func.__name__} executed successfully.")
            return result
        except Exception as e:
            log.error(f"Error running async function {func.__name__}: {e}")
            raise e