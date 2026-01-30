"""
WebSocket message protocol for adare-adarevm communication.

This module defines the message types and structures used for communication
between the host (adare) and VM (adarevm) over WebSocket connections.
"""

from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass, asdict
import json
import uuid
from enum import Enum


class MessageType(str, Enum):
    """WebSocket message types."""
    # Tool calling (MCP-inspired)
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    
    # Real-time events
    EVENT = "event" 
    STATUS = "status"
    
    # Connection management
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    PING = "ping"
    PONG = "pong"


class EventType(str, Enum):
    """Event types for real-time streaming."""
    # Test execution events
    TEST_START = "test_start"
    TEST_COMPLETE = "test_complete"
    TEST_FAILED = "test_failed"
    
    # GUI automation events
    GUI_CLICK = "gui_click"
    GUI_FIND = "gui_find"
    GUI_KEYPRESS = "gui_keypress"
    GUI_IDLE = "gui_idle"
    GUI_DRAG = "gui_drag"
    
    # Command execution events
    COMMAND_START = "command_start"
    COMMAND_COMPLETE = "command_complete"
    
    # General events
    LOG = "log"
    ERROR = "error"
    PROGRESS = "progress"


@dataclass
class BaseMessage:
    """Base class for all WebSocket messages."""
    type: MessageType
    id: Optional[str] = None
    timestamp: Optional[float] = None
    
    def to_json(self) -> str:
        """Convert message to JSON string."""
        return json.dumps(asdict(self), default=str)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'BaseMessage':
        """Create message from JSON string."""
        data = json.loads(json_str)
        return cls(**data)


@dataclass  
class ToolCallMessage(BaseMessage):
    """Message for calling a tool on the VM."""
    type: MessageType = MessageType.TOOL_CALL
    tool: str = ""
    params: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())
        if self.params is None:
            self.params = {}


@dataclass
class ToolResultMessage(BaseMessage):
    """Message containing the result of a tool call."""
    type: MessageType = MessageType.TOOL_RESULT
    success: bool = True
    result: Dict[str, Any] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.result is None:
            self.result = {}


@dataclass
class EventMessage(BaseMessage):
    """Message for streaming real-time events."""
    type: MessageType = MessageType.EVENT
    event_type: EventType = ""
    data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}


@dataclass
class StatusMessage(BaseMessage):
    """Message for status updates."""
    type: MessageType = MessageType.STATUS
    status: str = ""
    data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}


@dataclass
class ConnectMessage(BaseMessage):
    """Message for connection establishment."""
    type: MessageType = MessageType.CONNECT
    client_info: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.client_info is None:
            self.client_info = {}


# Message type mapping for deserialization
MESSAGE_TYPES = {
    MessageType.TOOL_CALL: ToolCallMessage,
    MessageType.TOOL_RESULT: ToolResultMessage, 
    MessageType.EVENT: EventMessage,
    MessageType.STATUS: StatusMessage,
    MessageType.CONNECT: ConnectMessage,
}


def parse_message(json_str: str) -> BaseMessage:
    """Parse a JSON message into the appropriate message type."""
    try:
        data = json.loads(json_str)
        msg_type = MessageType(data.get('type'))
        message_class = MESSAGE_TYPES.get(msg_type, BaseMessage)
        return message_class(**data)
    except Exception as e:
        raise ValueError(f"Failed to parse message: {e}")


# Convenience functions for creating common messages

def create_tool_call(tool: str, params: Dict[str, Any] = None) -> ToolCallMessage:
    """Create a tool call message."""
    return ToolCallMessage(tool=tool, params=params or {})


def create_tool_result(call_id: str, success: bool = True, 
                      result: Dict[str, Any] = None, error: str = None) -> ToolResultMessage:
    """Create a tool result message."""
    return ToolResultMessage(id=call_id, success=success, result=result or {}, error=error)


def create_event(event_type: EventType, data: Dict[str, Any] = None) -> EventMessage:
    """Create an event message."""
    return EventMessage(event_type=event_type, data=data or {})


def create_status(status: str, data: Dict[str, Any] = None) -> StatusMessage:
    """Create a status message."""
    return StatusMessage(status=status, data=data or {})


# Tool definitions (similar to MCP tools but for WebSocket)

class ToolRegistry:
    """Registry of available tools on the VM."""
    
    # GUI Actions
    SCREENSHOT = "screenshot"
    CLICK = "click"
    RIGHT_CLICK = "right_click"
    DOUBLE_CLICK = "double_click"
    DRAG = "drag"
    KEYBOARD = "keyboard"
    SCROLL = "scroll"
    GOTO = "goto"
    IDLE = "idle"
    
    # Test Management
    UPLOAD_TESTFUNCTIONS = "upload_testfunctions"
    UPLOAD_TESTSET = "upload_testset"
    INSTALL_DEPENDENCIES = "install_dependencies"
    SET_VARIABLES = "set_variables"
    RUN_TEST = "run_test"
    RUN_ALL_TESTS = "run_all_tests"
    LIST_TESTS = "list_tests"
    EXECUTE_SHELL = "execute_shell"
    GET_STATUS = "get_status"
    COLLECT_SYSTEM_INFO = "collect_system_info"

    # Window Management
    SCREENSHOT_WINDOW = "screenshot_window"

    # File Transfer
    PULL_FILE_CHUNK = "pull_file_chunk"

    # Filesystem
    GET_FILESYSTEM_SNAPSHOT = "get_filesystem_snapshot"

    # Timestamp
    GET_TIMESTAMP = "get_timestamp"

    ALL_TOOLS = [
        SCREENSHOT, CLICK, RIGHT_CLICK, DOUBLE_CLICK, DRAG,
        KEYBOARD, SCROLL, GOTO, IDLE, UPLOAD_TESTFUNCTIONS,
        UPLOAD_TESTSET, SET_VARIABLES, RUN_TEST, RUN_ALL_TESTS,
        LIST_TESTS, EXECUTE_SHELL, GET_STATUS, COLLECT_SYSTEM_INFO, SCREENSHOT_WINDOW,
        PULL_FILE_CHUNK, GET_FILESYSTEM_SNAPSHOT, GET_TIMESTAMP
    ]