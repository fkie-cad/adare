import asyncio
import logging
from typing import Callable, Awaitable, Any

log = logging.getLogger(__name__)


class ExperimentStepRunner:
    """Handles execution of experiment steps with proper error handling and cancellation."""
    
    def __init__(self, stop_event: asyncio.Event, user_interrupt_event):
        self.stop_event = stop_event
        self.user_interrupt_event = user_interrupt_event
    
    async def run_blocking_step(self, step_func: Callable, context: Any):
        """Run a blocking step in a separate thread if not cancelled."""
        if not self.stop_event.is_set():
            log.info(f"Running blocking step: {step_func.__name__}")
            await asyncio.to_thread(step_func, context)
            log.info(f"Blocking step {step_func.__name__} completed")

    async def run_async_step(self, step_func: Callable[..., Awaitable], context: Any):
        """
        Run an asynchronous step and wait for its completion or for a stop event.
        The step function must return a coroutine.
        """
        if not self.stop_event.is_set():
            log.info(f"Running async step: {step_func.__name__}")
            
            # Create proper tasks so exceptions bubble up to main try/except
            step_task = asyncio.create_task(step_func(context))
            stop_task = asyncio.create_task(self.stop_event.wait())
            
            try:
                # Use gather to let exceptions bubble up naturally
                done, pending = await asyncio.wait(
                    [step_task, stop_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # Check if step_task completed with exception
                for task in done:
                    if task.exception():
                        log.error(
                            f"Step '{step_func.__name__}' failed with: "
                            f"{task.exception()!r}",
                            exc_info=task.exception(),
                        )
                        # Use result() to properly re-raise exception with chain
                        task.result()
                        
                log.info(f"Async step {step_func.__name__} completed")
                
            finally:
                # Ensure cleanup
                for task in [step_task, stop_task]:
                    if not task.done():
                        task.cancel()

    async def run_cleanup_step(self, step_func: Callable, context: Any, post_interrupt: bool = False, **kwargs):
        """Run a cleanup step regardless of stop event status."""
        log.info(f"Running cleanup step: {step_func.__name__}")
        if asyncio.iscoroutinefunction(step_func):
            await step_func(context, post_interrupt=post_interrupt, **kwargs)
        else:
            await asyncio.to_thread(step_func, context, post_interrupt, **kwargs)
        log.info(f"Cleanup step {step_func.__name__} completed")

    async def run_steps_sequence(self, steps: list[Callable], context: Any):
        """Run a sequence of blocking steps."""
        for step in steps:
            await self.run_blocking_step(step, context)