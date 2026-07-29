"""Chat control-plane for ADARE.

A single **tool-plane** over :class:`~adare.api.AdareAPI` (the "hands"), consumed
by two brains: any external MCP client (``adare mcp serve``) and the embedded
``adare chat`` agentic REPL. Build the tools once (:mod:`.tools`); serve them
over MCP (:mod:`.mcp_control_server`) or drive them from the embedded loop
(:mod:`.repl` + :mod:`.brain`).
"""
