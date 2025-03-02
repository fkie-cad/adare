import asyncio
from typing import Callable

from textual.app import App, ComposeResult
from textual.containers import HorizontalGroup, VerticalScroll
from textual.widgets import Button, Footer, Header, Static, LoadingIndicator


class StepGroup(HorizontalGroup):
    """A widget for one step. It shows the function name and a Play button."""

    def __init__(self, label: str, func: Callable, **kwargs):
        super().__init__(**kwargs)
        self.label = label
        self.func = func

    def compose(self) -> ComposeResult:
        # Display the function name.
        yield Static(self.label)
        # Create a Play button with an id based on the step index.
        yield Button("Play")


class CustomApp(App):

    def __init__(self, steps: list):
        super().__init__()
        self.steps = steps

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        with VerticalScroll():
            for step in self.steps:
                yield StepGroup(step["label"], step["func"])

    async def action_quit(self) -> None:





if __name__ == "__main__":
    CustomApp.run()