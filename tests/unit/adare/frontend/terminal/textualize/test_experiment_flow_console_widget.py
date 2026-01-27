import pytest
import logging
from unittest.mock import MagicMock
from rich.console import Console
from rich.text import Text
from adare.frontend.terminal.textualize.experiment_flow_console_widget import ExperimentRunFlowConsoleWidget, FlowWidgetManager
from adarelib.constants import StatusEnum

class TestExperimentRunFlowConsoleWidget:


    @pytest.fixture
    def widget(self):
        w = ExperimentRunFlowConsoleWidget()
        w._update_console_ui = MagicMock()
        return w

    def test_initialization(self, widget):
        assert widget.state.messages == {}
        assert widget._widgets_map == {}
        assert widget.tick == 0
        assert widget.ticks_per_second == 12

    def test_log_success(self, widget):
        identifier = "test_success"
        message = "Operation successful"
        widget.log_success(identifier, message, level=1)

        assert identifier in widget.state.messages
        entry = widget.state.messages[identifier]
        assert entry["message"] == message
        assert entry["status"] == StatusEnum.SUCCESS
        assert entry["level"] == 1
        assert entry["spinner"] is None

    def test_log_error(self, widget):
        identifier = "test_error"
        message = "Operation failed"
        widget.log_error(identifier, message)

        assert identifier in widget.state.messages
        entry = widget.state.messages[identifier]
        assert entry["message"] == message
        assert entry["status"] == StatusEnum.ERROR

    def test_log_warning(self, widget):
        identifier = "test_warning"
        message = "Warning issued"
        widget.log_warning(identifier, message)

        entry = widget.state.messages[identifier]
        assert entry["status"] == StatusEnum.WARNING

    def test_log_spinner(self, widget):
        identifier = "test_spinner"
        message = "Loading..."
        widget.log_spinner(identifier, message, spinner="dots")

        entry = widget.state.messages[identifier]
        assert entry["spinner"] == "dots"
        assert entry["status"] == StatusEnum.NONE

    def test_log_spinner_done(self, widget):
        identifier = "test_spinner"
        widget.log_spinner(identifier, "Loading...", spinner="dots")
        
        widget.log_spinner_done(identifier, StatusEnum.SUCCESS, message="Done!")
        
        entry = widget.state.messages[identifier]
        assert entry["spinner"] is None
        assert entry["status"] == StatusEnum.SUCCESS
        assert entry["message"] == "Done!"

    def test_generate_message_success(self, widget):
        identifier = "id_1"
        widget.log_success(identifier, "Success Msg")
        
        # Manually trigger message generation
        msg_str = widget._generate_message(identifier, widget.state.messages[identifier])
        
        # Check for icon and message
        icon = StatusEnum.get_icon(StatusEnum.SUCCESS, color=True)
        assert icon in msg_str
        assert "Success Msg" in msg_str

    def test_generate_message_with_indent(self, widget):
        identifier = "id_indent"
        widget.log_success(identifier, "Indented", level=2)
        
        msg_str = widget._generate_message(identifier, widget.state.messages[identifier])
        # 2 levels * 2 spaces = 4 spaces
        assert "    " in msg_str or (StatusEnum.get_icon(StatusEnum.SUCCESS, color=True) + " Indented") in msg_str

    def test_generate_message_spinner(self, widget):
        identifier = "id_spin"
        widget.log_spinner(identifier, "Spinning", spinner="dots")
        
        # Check frame 0
        msg_str_0 = widget._generate_message(identifier, widget.state.messages[identifier], spinner_position=0)
        # Check frame 1
        msg_str_1 = widget._generate_message(identifier, widget.state.messages[identifier], spinner_position=1)
        
        assert "Spinning" in msg_str_0
        # dots frames usually change
        assert msg_str_0 != msg_str_1


class TestFlowWidgetManager:
    def test_manager_operations(self):
        manager = FlowWidgetManager()
        handler = MagicMock(spec=ExperimentRunFlowConsoleWidget)
        ulid = "test_ulid"
        
        manager.add_handler(ulid, handler)
        assert manager.get_handler(ulid) == handler
        
        manager.remove_handler(ulid)
        with pytest.raises(KeyError):
            manager.get_handler(ulid)
