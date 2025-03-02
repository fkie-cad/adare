import asyncio
import time
import signal
import threading

from textual.app import App, ComposeResult
from textual.containers import HorizontalGroup, VerticalScroll
from textual.widgets import Button, Footer, Header, Static, LoadingIndicator
from adare.frontend.terminal.textualize.experiment_flow_console_widget import flowwidgetmanager
from adare.backend.experiment.runctx import ExperimentRunCtx
from typing import Callable, List
from adare.backend.types import Step

import logging
log = logging.getLogger(__name__)

class LogView(HorizontalGroup):
    experiment_run_ulid: str
    log_handler = None

    def __init__(self, experiment_run_ulid: str):
        super().__init__()
        self.experiment_run_ulid = experiment_run_ulid

    def compose(self) -> ComposeResult:
        self.log_handler = flowwidgetmanager.get_handler(self.experiment_run_ulid)
        yield self.log_handler

    def on_mount(self) -> None:
        # Periodically update the height based on the content
        self.set_interval(0.5, self.adjust_height)

    def adjust_height(self) -> None:
        # You might compute the new height based on the log handler's content.
        # This is an example—you might have a method/property that returns the desired height.
        new_height = self.log_handler.n_lines + 3
        self.styles.height = new_height
        self.refresh(layout=True)



class StepGroup(HorizontalGroup):
    """A widget for one step. It shows the function name and a Play button."""

    def __init__(self, step_index: int, step: Step, **kwargs):
        super().__init__(**kwargs)
        self.step_index = step_index
        self.step_label = step.label

    def compose(self) -> ComposeResult:
        # Display the function name.
        yield Static(self.step_label, classes="step-label")
        # Create a Play button with an id based on the step index.
        yield Button("Play", id=f"play-{self.step_index}", variant="primary", classes="playbutton")

    def disable(self) -> None:
        """Disable the Play button in this step group."""
        button = self.query_one(Button)
        button.disabled = True


class ExperimentApp(App):
    """A Textual app that renders experiment steps in one column and the log view in another.
    When a step’s Play button is clicked, it calls all functions from the beginning
    up to that step (if not already called). During execution, only the buttons corresponding
    to the steps that are running will be disabled. Steps not yet executed remain enabled,
    so they can be queued for execution later.
    """
    run_ctx: ExperimentRunCtx
    steps: List[Step]
    shutdown_steps: List[Step]
    last_executed_index: int
    step_queue: asyncio.Queue[int]
    shutdown_queue: asyncio.Queue[Step]
    stop_event: asyncio.Event  # using asyncio.Event consistently

    CSS_PATH = "experiment_interactive.tcss"

    def __init__(
        self,
        run_ctx: ExperimentRunCtx,
        steps: List[Step],
        shutdown_steps: List[Step]
    ):
        super().__init__()
        self.run_ctx = run_ctx
        self.run_ctx.stop_event = threading.Event()
        self.steps = steps
        self.shutdown_steps = shutdown_steps
        self.last_executed_index = -1
        self.step_queue = asyncio.Queue()
        self.shutdown_queue = asyncio.Queue()
        self.stop_event = asyncio.Event()

    async def on_mount(self) -> None:
        self.theme = 'catppuccin-mocha'
        # Start the background task that processes queued step requests.
        self.set_interval(0.1, self.process_queue)
        self.set_interval(0.1, self.proces_shutdown_queue)

    async def __run_blocking_step(self, step_func):
        """Run a blocking step in a separate thread if not cancelled."""
        await asyncio.to_thread(step_func, self.run_ctx)

    async def __run_async_step(self, step_func, stop_on_stop=True):
        task = step_func(self.run_ctx)
        if stop_on_stop:
            # Wait for either the task to complete or the stop_event to be set.
            done, pending = await asyncio.wait(
                [task, self.stop_event.wait()],
                return_when=asyncio.FIRST_COMPLETED
            )
            if self.stop_event.is_set():
                log.info('Cancelling step due to stop event')
                task.cancel()
            result = await task  # Ensure task completes (or is cancelled)
            log.info(f'Step completed: {result}')
        else:
            # For shutdown tasks, simply await the task.
            result = await task
            log.info(f'Shutdown step completed: {result}')

    async def run_step(self, step: Step, stop_on_stop: bool = True) -> None:
        if self.stop_event.is_set() and stop_on_stop:
            log.info(f"Stop event received. Skipping step {step.label}.")
            return

        log.info(f"Running step: {step.label}")

        if step.thread:
            await self.__run_blocking_step(step.func)
        else:
            await self.__run_async_step(step.func, stop_on_stop=stop_on_stop)
        log.info(f"Step completed: {step.label}")


    async def process_queue(self) -> None:
        if self.step_queue.empty():
            return
        target_index = await self.step_queue.get()
        # Compute the steps that have not yet run.
        steps_to_run = self.steps[self.last_executed_index + 1 : target_index + 1]
        # Disable only the buttons corresponding to the steps being executed.
        self.disable_buttons_upto(target_index)
        # Execute each step sequentially.
        for step in steps_to_run:
            await self.run_step(step)
        self.last_executed_index = target_index
        self.enable_pending_buttons()
        self.step_queue.task_done()

    async def proces_shutdown_queue(self) -> None:
        if self.shutdown_queue.empty():
            return
        step = await self.shutdown_queue.get()
        await self.run_step(step, stop_on_stop=False)
        self.shutdown_queue.task_done()


    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        # Create a horizontal group to split the screen into two columns.
        with HorizontalGroup():
            # Left column: all steps in a vertical scroll.
            with VerticalScroll():
                for index, step in enumerate(self.steps):
                    yield StepGroup(step_index=index, step=step)
            # Right column: the log view in its own vertical scroll.
            with VerticalScroll():
                yield LogView(self.run_ctx.experiment_run_ulid)

    def disable_buttons_upto(self, target_index: int) -> None:
        """Disable Play buttons for steps from (last_executed_index+1) up to target_index (inclusive)."""
        for btn in self.query(Button):
            if btn.id and btn.id.startswith("play-"):
                idx = int(btn.id.split("-")[1])
                if self.last_executed_index < idx <= target_index:
                    btn.disabled = True

    def enable_pending_buttons(self) -> None:
        """Re-enable Play buttons for steps that haven’t been executed yet."""
        for btn in self.query(Button):
            if btn.id and btn.id.startswith("play-"):
                idx = int(btn.id.split("-")[1])
                if idx > self.last_executed_index:
                    btn.disabled = False

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id and button_id.startswith("play-"):
            step_index = int(button_id.split("-")[1])
            if step_index > self.last_executed_index:
                self.disable_buttons_upto(step_index)
                await self.step_queue.put(step_index)

    async def action_quit(self) -> None:
        if not self.stop_event.is_set():
            log.info("Stopping experiment run...")
            self.run_ctx.stop_event.set()
            self.stop_event.set()
            log.info("send stop events")
            await asyncio.sleep(1)
            await self.step_queue.join()
            log.info("step_queue joined")
            for step in self.shutdown_steps:
                await self.run_step(step, stop_on_stop=False)
            # for step in self.shutdown_steps:
            #     log.info(f"queueing shutdown step: {step.label}")
            #     await self.shutdown_queue.put(step)
            # log.info("shutdown steps queued")
            # await self.shutdown_queue.join()
            # log.info("shutdown_queue joined")
            self.exit()






