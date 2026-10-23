"""The agent serves exactly the tools the shared protocol declares."""

import inspect

from adarelib.websocket.protocol import Tool, ToolRegistry
from adarevm.core.server import AdareVMServer


def test_dispatch_table_is_exactly_the_protocol_tools():
    assert set(AdareVMServer().tools) == {tool.value for tool in Tool}


def test_every_tool_handler_is_a_coroutine_taking_the_websocket():
    for name, handler in AdareVMServer().tools.items():
        assert inspect.iscoroutinefunction(handler), name
        assert next(iter(inspect.signature(handler).parameters)) == 'websocket', name


def test_registry_constants_mirror_the_enum():
    assert sorted(ToolRegistry.ALL_TOOLS) == sorted(tool.value for tool in Tool)
    for tool in Tool:
        assert getattr(ToolRegistry, tool.name) == tool.value
