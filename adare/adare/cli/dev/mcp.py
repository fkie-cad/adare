"""CLI handler for ``adare dev mcp`` — serve a dev session as an MCP server.

Binds a long-lived GUI-automation MCP server to an already-running dev session
so an external harness (OpenCode / Claude Code / any MCP client) can author
playbooks by natural language. ADARE grounds via CV/OCR and records crops +
tests; replay is deterministic with no LLM. See the "Authoring experiments with
the ADARE MCP server" guide for connection snippets.
"""

import logging
from pathlib import Path

from adare.api import AdareAPI
from adare.cli.dev._helpers import _resolve_session_id
from adare.cli.utils import get_project_path, handle_api_error
from adare.core.dto.devmode import DevServeMcpRequest

log = logging.getLogger(__name__)


def exec_dev_mcp(arguments):
    """Serve a dev session's VM as a GUI-automation MCP server (blocks)."""
    project_directory = get_project_path(arguments)
    session_id = _resolve_session_id(getattr(arguments, 'session_id', None), project_directory)

    output = getattr(arguments, 'output_dir', None)
    output_dir = Path(output).resolve() if output else None

    api = AdareAPI()
    request = DevServeMcpRequest(
        session_id=session_id,
        host=getattr(arguments, 'host', None),
        port=getattr(arguments, 'port', None),
        project_path=project_directory,
        output_dir=output_dir,
    )

    print(f"Serving dev session {session_id} as an MCP server.")
    print("Connect an external harness (OpenCode / Claude Code) as a remote HTTP MCP server.")
    print("Press Ctrl-C to stop.\n")

    result = api.devmode.serve_mcp(request)
    if not result.success:
        handle_api_error(result)
        return
