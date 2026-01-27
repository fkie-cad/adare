import pytest
from unittest.mock import MagicMock, call, patch
from adare.frontend.terminal.textualize.experiment_flow_console_widget import ExperimentRunFlowConsoleWidget
from adarelib.constants import StatusEnum
from rich.text import Text
from textual.widgets import Static

class TestConsoleWidgetPerformance:
    @pytest.fixture
    def widget(self):
        # Patch Static to return a MagicMock, preventing NoActiveAppError during update()
        with patch('adare.frontend.terminal.textualize.experiment_flow_console_widget.Static') as mock_static:
             # Configure the mock to behave like a widget if needed, but for now just returning a Mock is enough
             # so that static_instance.update() is a mock call.
             
             w = ExperimentRunFlowConsoleWidget()
             w.mount = MagicMock()
             w.scroll_end = MagicMock()
             w.call_after_refresh = MagicMock()
             yield w

    def test_incremental_add(self, widget):
        """Verify that adding a new message calls mount."""
        identifier = "msg1"
        widget.log_success(identifier, "Hello")
        
        # Trigger update
        widget._update_console_ui()
        
        # Should have mounted a new widget
        assert widget.mount.called
        assert identifier in widget._widgets_map
        # Since Static is patched, we can't check isinstance easily without spec, 
        # but presence in map implies creation.
        assert widget._widgets_map[identifier] is not None
        
        # Should schedule scroll to end for new messages
        assert widget.call_after_refresh.called
        # Check that scroll_end was the argument
        args, kwargs = widget.call_after_refresh.call_args
        assert args[0] == widget.scroll_end
        assert kwargs.get('animate') is False

    def test_no_recomposition_on_tick(self, widget):
        """Verify that subsequent ticks do NOT re-mount widgets."""
        identifier = "msg1"
        widget.log_success(identifier, "Hello")
        
        # First update
        widget._update_console_ui()
        mount_count_initial = widget.mount.call_count
        
        # Second update (tick)
        widget._update_tick()
        
        # Should verify mount was NOT called again
        assert widget.mount.call_count == mount_count_initial
        
        # The widget in map should be the same object
        cached_widget = widget._widgets_map[identifier]
        assert cached_widget is not None

    def test_update_existing_widget(self, widget):
        """Verify that updating a message updates the text but doesn't remount."""
        identifier = "msg1"
        widget.log_spinner(identifier, "Loading...", spinner="dots")
        
        # Initial render
        widget._update_console_ui()
        initial_widget = widget._widgets_map[identifier]
        
        # Mock the update method on the actual Static widget we just created?
        # Since we can't easily mock the method of the instance attached to _widgets_map 
        # (unless we intercept creation or mock the class), we can inspect the renderable?
        # Actually, Static.update() updates the renderable.
        
        # Let's mock the update method of the stored widget
        initial_widget.update = MagicMock()
        
        # Advance tick and update
        widget.tick += 1
        widget._update_console_ui()
        
        # Verify update called
        assert initial_widget.update.called
        # Verify NO new mount
        assert widget.mount.call_count == 1
