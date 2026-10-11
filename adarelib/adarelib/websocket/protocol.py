"""
WebSocket message protocol for adare-adarevm communication.

This module defines the message types and structures used for communication
between the host (adare) and VM (adarevm) over WebSocket connections.

Handshake (protocol 2): the host connects with ``Authorization: Bearer <token>``
(the per-run token from the agent's ``config.json``); the agent rejects a
missing or wrong token with HTTP 401, then sends a ``welcome`` event carrying
``protocol_version``, its package versions and the tools it serves. The host
refuses agents that speak another protocol version and only calls tools the
agent advertised.
"""

import json
import uuid
from dataclasses import asdict, dataclass, fields
from enum import Enum
from typing import Any

#: Bump on any incompatible change to messages, the handshake or tool semantics.
PROTOCOL_VERSION = 2

#: HTTP header carrying the agent token on the WebSocket upgrade request.
AUTH_HEADER = "Authorization"
AUTH_SCHEME = "Bearer"


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

    # First message on every connection (protocol >= 2)
    WELCOME = "welcome"


@dataclass
class BaseMessage:
    """Base class for all WebSocket messages."""

    type: MessageType
    id: str | None = None
    timestamp: float | None = None

    def to_json(self) -> str:
        """Convert message to JSON string."""
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_json(cls, json_str: str) -> 'BaseMessage':
        """Create message from JSON string."""
        return cls._from_dict(json.loads(json_str))

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> 'BaseMessage':
        """Build from a decoded message, ignoring fields this side does not know.

        Lets either side add fields without breaking an older peer.
        """
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class ToolCallMessage(BaseMessage):
    """Message for calling a tool on the VM."""

    type: MessageType = MessageType.TOOL_CALL
    tool: str = ""
    params: dict[str, Any] = None

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
    result: dict[str, Any] = None
    error: str | None = None

    def __post_init__(self):
        if self.result is None:
            self.result = {}


@dataclass
class EventMessage(BaseMessage):
    """Message for streaming real-time events."""

    type: MessageType = MessageType.EVENT
    event_type: EventType = ""
    data: dict[str, Any] = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


@dataclass
class StatusMessage(BaseMessage):
    """Message for status updates."""

    type: MessageType = MessageType.STATUS
    status: str = ""
    data: dict[str, Any] = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


@dataclass
class ConnectMessage(BaseMessage):
    """Message for connection establishment."""

    type: MessageType = MessageType.CONNECT
    client_info: dict[str, Any] = None

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
    """Parse a JSON message into the appropriate message type.

    Unknown fields are dropped and unknown message types become a plain
    ``BaseMessage``, so a newer peer does not break this one.
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse message: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"Failed to parse message: expected an object, got {type(data).__name__}")
    try:
        msg_type = MessageType(data.get('type'))
    except ValueError:
        return BaseMessage(type=data.get('type'), id=data.get('id'), timestamp=data.get('timestamp'))
    return MESSAGE_TYPES.get(msg_type, BaseMessage)._from_dict(data)


# Convenience functions for creating common messages


def create_tool_call(tool: str, params: dict[str, Any] = None) -> ToolCallMessage:
    """Create a tool call message."""
    return ToolCallMessage(tool=tool, params=params or {})


def create_tool_result(
    call_id: str, success: bool = True, result: dict[str, Any] = None, error: str = None
) -> ToolResultMessage:
    """Create a tool result message."""
    return ToolResultMessage(id=call_id, success=success, result=result or {}, error=error)


def create_event(event_type: EventType, data: dict[str, Any] = None) -> EventMessage:
    """Create an event message."""
    return EventMessage(event_type=event_type, data=data or {})


def create_status(status: str, data: dict[str, Any] = None) -> StatusMessage:
    """Create a status message."""
    return StatusMessage(status=status, data=data or {})


# Tool definitions (similar to MCP tools but for WebSocket)


class Tool(str, Enum):
    """Every tool the guest agent serves; the agent's dispatch table is built from this."""

    # GUI actions
    SCREENSHOT = "screenshot"
    CLICK = "click"
    RIGHT_CLICK = "right_click"
    DOUBLE_CLICK = "double_click"
    DRAG = "drag"
    KEYBOARD = "keyboard"
    SCROLL = "scroll"
    GOTO = "goto"
    IDLE = "idle"
    SCREENSHOT_WINDOW = "screenshot_window"
    SET_SCREENSHOT_METHOD = "set_screenshot_method"
    EXTRACT_ICON = "extract_icon"

    # Test management
    UPLOAD_TESTFUNCTIONS = "upload_testfunctions"
    INSTALL_DEPENDENCIES = "install_dependencies"
    SET_VARIABLES = "set_variables"
    RUN_TEST = "run_test"

    # System
    EXECUTE_SHELL = "execute_shell"
    CHAIN_COMMANDS = "chain_commands"
    GET_STATUS = "get_status"
    COLLECT_SYSTEM_INFO = "collect_system_info"
    GET_TIMESTAMP = "get_timestamp"

    # Files
    PULL_FILE_CHUNK = "pull_file_chunk"
    GET_FILESYSTEM_SNAPSHOT = "get_filesystem_snapshot"


class ToolRegistry:
    """String constants for the tools (kept for existing callers; see :class:`Tool`)."""

    SCREENSHOT = Tool.SCREENSHOT.value
    CLICK = Tool.CLICK.value
    RIGHT_CLICK = Tool.RIGHT_CLICK.value
    DOUBLE_CLICK = Tool.DOUBLE_CLICK.value
    DRAG = Tool.DRAG.value
    KEYBOARD = Tool.KEYBOARD.value
    SCROLL = Tool.SCROLL.value
    GOTO = Tool.GOTO.value
    IDLE = Tool.IDLE.value
    SCREENSHOT_WINDOW = Tool.SCREENSHOT_WINDOW.value
    SET_SCREENSHOT_METHOD = Tool.SET_SCREENSHOT_METHOD.value
    EXTRACT_ICON = Tool.EXTRACT_ICON.value
    UPLOAD_TESTFUNCTIONS = Tool.UPLOAD_TESTFUNCTIONS.value
    INSTALL_DEPENDENCIES = Tool.INSTALL_DEPENDENCIES.value
    SET_VARIABLES = Tool.SET_VARIABLES.value
    RUN_TEST = Tool.RUN_TEST.value
    EXECUTE_SHELL = Tool.EXECUTE_SHELL.value
    CHAIN_COMMANDS = Tool.CHAIN_COMMANDS.value
    GET_STATUS = Tool.GET_STATUS.value
    COLLECT_SYSTEM_INFO = Tool.COLLECT_SYSTEM_INFO.value
    GET_TIMESTAMP = Tool.GET_TIMESTAMP.value
    PULL_FILE_CHUNK = Tool.PULL_FILE_CHUNK.value
    GET_FILESYSTEM_SNAPSHOT = Tool.GET_FILESYSTEM_SNAPSHOT.value

    ALL_TOOLS = [tool.value for tool in Tool]
