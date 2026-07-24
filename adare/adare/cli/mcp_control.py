"""CLI handler for ``adare mcp serve`` — the ADARE control-plane MCP server.

Distinct from the session-scoped ``adare dev mcp`` (which hands one running
session's VM to a harness): this serves the whole ADARE lifecycle (projects,
environments, experiments, runs, VMs, dev sessions, and LLM playbook authoring)
as MCP tools. Point any MCP client (Claude Code / Claude Desktop) at it and
drive ADARE conversationally with zero brain code.
"""

import logging

log = logging.getLogger(__name__)


def exec_mcp_serve(arguments):
    """Serve the ADARE control-plane over MCP (blocking)."""
    from adare.backend.chat.mcp_control_server import serve

    transport = getattr(arguments, 'transport', 'stdio')
    host = getattr(arguments, 'host', '127.0.0.1')
    port = getattr(arguments, 'port', 13111)

    if transport == 'stdio':
        # Do NOT print to stdout on stdio: it carries the MCP JSON-RPC stream.
        log.info('Serving the ADARE control-plane over MCP (stdio).')
    else:
        print(f"Serving the ADARE control-plane over MCP at http://{host}:{port}/mcp")
        print("Connect an MCP client (Claude Code / Claude Desktop). Press Ctrl-C to stop.\n")

    try:
        serve(transport=transport, host=host, port=port)
    except KeyboardInterrupt:
        log.info('ADARE control MCP server stopped')
