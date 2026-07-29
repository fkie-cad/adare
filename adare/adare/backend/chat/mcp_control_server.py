"""FastMCP server exposing the whole ADARE control-plane (Phase 2).

Generalizes the per-session ``vlm/mcp_server.py`` pattern to the full lifecycle:
every tool in the shared registry (:mod:`.tools`) is registered as an MCP tool,
so any MCP client (Claude Code / Claude Desktop / any harness) becomes an ADARE
console with zero brain code. Served over stdio (a client launches the process)
or streamable HTTP.

Each tool's callable is synchronous and may call ``asyncio.run`` internally, so
it is dispatched via ``asyncio.to_thread`` — off the server's event loop, in a
thread with no running loop. Tools flagged ``serialized_vm`` share one lock so
live-VM operations never overlap (one VM, one input focus — see FLOW.md).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_SERVER_NAME = 'adare-control'


def build_mcp(server_name: str = DEFAULT_SERVER_NAME, api: Any | None = None):
    """Build a :class:`FastMCP` server registering every control-plane tool."""
    from fastmcp import FastMCP

    from adare.backend.chat.tools import build_tools, call_tool

    mcp = FastMCP(name=server_name)
    vm_lock = asyncio.Lock()  # serializes all live-VM tools

    for tool in build_tools(api):
        mcp.add_tool(_make_function_tool(tool, call_tool, vm_lock))

    return mcp


def _make_function_tool(tool, call_tool, vm_lock: asyncio.Lock):
    """Wrap a :class:`ChatTool` as a FastMCP ``FunctionTool`` with its schema."""
    from fastmcp.tools.function_tool import FunctionTool

    serialized = tool.serialized_vm

    async def fn(**kwargs):
        if serialized:
            async with vm_lock:
                return await asyncio.to_thread(call_tool, tool, kwargs)
        return await asyncio.to_thread(call_tool, tool, kwargs)

    fn.__name__ = tool.name
    return FunctionTool(
        name=tool.name,
        description=tool.description,
        parameters=tool.parameters,
        fn=fn,
    )


def serve(
    *,
    transport: str = 'stdio',
    host: str = '127.0.0.1',
    port: int = 13111,
    path: str = '/mcp',
    server_name: str = DEFAULT_SERVER_NAME,
) -> None:
    """Run the control-plane MCP server (blocking) over the chosen transport."""
    mcp = build_mcp(server_name=server_name)
    if transport == 'stdio':
        log.info('ADARE control MCP server on stdio')
        mcp.run(transport='stdio')
    else:
        log.info('ADARE control MCP server on http://%s:%d%s', host, port, path)
        mcp.run(transport='http', host=host, port=port, path=path)
