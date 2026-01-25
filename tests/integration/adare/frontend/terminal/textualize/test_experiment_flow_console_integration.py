import pytest
import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Static
from adare.frontend.terminal.textualize.experiment_flow_console_widget import ExperimentRunFlowConsoleWidget, StatusEnum

class FlowConsoleTestApp(App):
    def compose(self) -> ComposeResult:
        # We mount the widget to be tested
        yield ExperimentRunFlowConsoleWidget()

@pytest.fixture(autouse=True)
def clean_messages():
    """Cleanup the class-level messages dictionary before each test."""
    ExperimentRunFlowConsoleWidget.messages.clear()
    yield
    ExperimentRunFlowConsoleWidget.messages.clear()

@pytest.mark.asyncio
async def test_console_integration_add_messages():
    app = FlowConsoleTestApp()
    async with app.run_test() as pilot:
        widget = app.query_one(ExperimentRunFlowConsoleWidget)
        
        # Add a success message
        widget.log_success("int_1", "Integration Success")
        await pilot.pause()
        
        # Check if the message is recorded
        assert "int_1" in widget.messages
        # Check if the UI reflects the message (recomposed)
        statics = widget.query(Static)
        assert len(statics) == 1
        # Retrieve the text content from the Static widget
        rendered_text = str(statics[0].renderable)
        assert "Integration Success" in rendered_text
        
        # Add another message
        widget.log_error("int_2", "Integration Error")
        await pilot.pause()
        
        statics = widget.query(Static)
        assert len(statics) == 2
        assert "Integration Error" in str(statics[1].renderable)

@pytest.mark.asyncio
async def test_console_integration_spinner_update():
    app = FlowConsoleTestApp()
    async with app.run_test() as pilot:
        widget = app.query_one(ExperimentRunFlowConsoleWidget)
        
        # Add a spinner message
        widget.log_spinner("spin_1", "Loading...", spinner="dots")
        await pilot.pause()
        
        # Initial state
        initial_tick = widget.tick
        # 'dots' spinner has multiple frames.
        # Wait for some ticks. Ticks per second is 12, so 0.2s should trigger ~2 ticks.
        await pilot.pause(0.2)
        
        assert widget.tick > initial_tick
        
        # Check frame update in message generation (indirectly via line content if we could capture exact frame)
        # But verifying tick increment confirms the interval is working.
        
        # Finish spinner
        widget.log_spinner_done("spin_1", StatusEnum.SUCCESS, "Done")
        await pilot.pause()
        
        statics = widget.query(Static)
        assert "Done" in str(statics[0].renderable)
        assert widget.messages["spin_1"]["spinner"] is None
