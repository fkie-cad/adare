import asyncio
import time
import signal
import threading
from tkinter import Widget

from textual import events
from textual.app import App, ComposeResult, RenderResult
from textual.containers import HorizontalGroup, VerticalScroll, Vertical, Horizontal, VerticalGroup
from textual.widgets import Button, Footer, Header, Static, LoadingIndicator, Rule
from textual.screen import Screen
from adare.frontend.terminal.textualize.experiment_flow_console_widget import flowwidgetmanager
from adare.backend.experiment.runctx import ExperimentRunCtx
from typing import Callable, List
from adare.backend.types import Step
from rich.text import Text
from textual.reactive import reactive

import logging
log = logging.getLogger(__name__)


class FlowPanel(Vertical):
    experiment_run_ulid: str
    log_handler = None
    BORDER_TITLE = Text.from_markup('Flow Panel :water_wave:')

    def __init__(self, experiment_run_ulid: str):
        super().__init__()
        self.experiment_run_ulid = experiment_run_ulid

    def compose(self) -> ComposeResult:
        self.log_handler = flowwidgetmanager.get_handler(self.experiment_run_ulid)
        yield self.log_handler


class PlayButton(Button):
    state = reactive('not_started')

    def __init__(self, **kwargs):
        kwargs['label'] = ''
        super().__init__(**kwargs)

    def render(self) -> RenderResult:
        if self.state == 'not_started':
            return Button(Text.from_markup('Play :play_button:')).render()
        elif self.state == 'running':
            return Button(Text.from_markup('Running :hourglass:')).render()
        elif self.state == 'replay':
            return Button(Text.from_markup('Replay :repeat:')).render()
        elif self.state == 'done':
            return Button(Text.from_markup('Done :white_check_mark:')).render()
        else:
            return Static('Not implemented').render()

class StepPanel(VerticalGroup):
    """A widget for one step. It shows the function name and a Play button."""

    def __init__(self, step_index: int, step: Step, **kwargs):
        super().__init__(**kwargs)
        self.step_index = step_index
        self.step_label = step.label

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes='box2', id=f'step-{self.step_index}') as box:
                box.border_title = Text.from_markup(f'{self.step_label}')
                yield PlayButton(id=f"play-{self.step_index}")

    def disable(self) -> None:
        """Disable the Play button in this step group."""
        button = self.query_one(Button)
        button.disabled = True


class CustomIconizedButton(Button):
    """A custom button that displays an icon and a label."""

    def __init__(self, icon: str, label: str, width: int, **kwargs):
        super().__init__(**kwargs)
        self.icon = icon
        self.label = label
        self.width = width

    def render(self) -> RenderResult:
        number_spaces = self.width - 4 - 1 - len(self.label)
        if number_spaces <= 0:
            number_spaces = 1
        return Text.from_markup(f'{self.icon} {self.label}{" "*(number_spaces-1)}')


class MachinePanel(Vertical):
    BORDER_TITLE = Text.from_markup(f'Machine :laptop_computer:')

    def __init__(self, experiment: str, environment: str):
        super().__init__()
        self.experiment = experiment
        self.environment = environment
        self.id = 'machine-panel'

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes='box') as box:
                box.border_title = Text.from_markup('metadata :gear:')
                #yield StatusStatic()
                yield Static(f'Experiment: {self.experiment}')
                yield Static(f'Environment: {self.environment}')
            with Vertical(classes='verticalbuttonlist box') as box:
                box.border_title = Text.from_markup('actions :hammer_and_wrench: ')
                yield CustomIconizedButton(icon=':red_square:', label='Stop Machine', width=20, id='btn-stop-vm')
                yield CustomIconizedButton(icon=':rocket:', label='Restart Exp.', width=20, id='btn-restart')
                yield CustomIconizedButton(icon=':door:', label='Quit', width=20, id='btn-quit')


class StepListPanel(Vertical):
    """ A widget that displays multiple StepGroups vertically. """
    steps: List[Step]
    BORDER_TITLE = Text.from_markup('Steps Panel :rocket:')

    def __init__(self, steps: List[Step]):
        super().__init__()
        self.steps = steps

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            for index, step in enumerate(self.steps):
                yield StepPanel(step_index=index, step=step)


class MessageScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Pop screen")]

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        yield Static(self.message)


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
    callbacks: dict[str, Callable]
    AUTO_FOCUS = None

    CSS_PATH = "experiment_interactive.tcss"

    def __init__(
        self,
        run_ctx: ExperimentRunCtx,
        steps: List[Step],
        shutdown_steps: List[Step],
        callbacks: dict[str, Callable],
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
        self.callbacks = callbacks

    async def on_mount(self) -> None:
        self.theme = 'catppuccin-mocha'
        # Start the background task that processes queued step requests.
        self.set_interval(0.1, self.process_queue)
        self.set_interval(0.1, self.proces_shutdown_queue)


    async def __run_blocking_step(self, step_func):
        """Run a blocking step in a separate thread if not cancelled."""
        await asyncio.to_thread(step_func, self.run_ctx)

    async def __run_async_step(self, step_func, stop_on_stop=True):
        task = asyncio.create_task(step_func(self.run_ctx))  # ✅ Create an actual task
        if stop_on_stop:
            done, pending = await asyncio.wait(
                [task, self.stop_event.wait()],
                return_when=asyncio.FIRST_COMPLETED
            )

            # Explicitly check if the stop event future is in the `done` set
            if self.stop_event.is_set() or self.stop_event.wait() in done:
                log.info('Cancelling step due to stop event')
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    log.info('Step was cancelled')
                return

        result = await task
        log.info(f'Step completed: {result}')

    def __run_callback(self, name: str):
        return self.callbacks[name](self.run_ctx)

    def __run_callback_async(self, name: str):
        return asyncio.to_thread(self.__run_callback, name)


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


    def __update_step_panel_before_run(self, step: Step, index: int) -> None:
        step_panel = self.query_one(f'#step-{index}')
        step_panel.toggle_class('box2', 'box2running')
        play_btn = self.query_one(f"#play-{index}")
        play_btn.state = 'running'

    def __update_step_panel_after_run(self, step: Step, index: int) -> None:
        play_btn = self.query_one(f"#play-{index}")
        step_panel = self.query_one(f'#step-{index}')
        if not step.repeatable:
            step_panel.toggle_class('box2running', 'box2done')
            play_btn.state = 'done'
        else:
            play_btn.state = 'replay'


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
            self.__update_step_panel_before_run(step, target_index)
            await self.run_step(step)
            self.__update_step_panel_after_run(step, target_index)
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
            with Vertical():
                yield MachinePanel(
                    experiment=self.run_ctx.experiment_name,
                    environment=self.run_ctx.environment_name,
                )
                yield StepListPanel(self.steps)
            # Right column: the log view in its own vertical scroll.
            with Vertical():
                yield FlowPanel(self.run_ctx.experiment_run_ulid)

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
        elif button_id == 'btn-stop-vm':
            log.info('Stopping VM')
        elif button_id == 'btn-restart':
            log.info('Restarting VM')
        elif button_id == 'btn-quit':
            await self.action_quit()
        else:
            log.warning(f'Unknown button pressed: {button_id}')





    async def action_quit(self) -> None:
        if not self.__run_callback('vagrant_box_exists'):
            self.exit()

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






