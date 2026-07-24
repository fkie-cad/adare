"""CLI handler for ``adare chat`` — the embedded agentic REPL.

A terminal console with its own agent loop and an embedded, provider-agnostic
brain (:class:`OpenAICompatBrain`) that drives ADARE by calling the same shared
tool registry the MCP control server exposes. The brain reuses whatever
OpenAI-compatible endpoint the user configured for ``adare vlm`` (vLLM /
Ollama-cloud / custom) — no separate provider, no API-key SDK dependency.
"""

import logging

log = logging.getLogger(__name__)


def exec_chat(arguments):
    """Start the embedded ADARE chat REPL."""
    from adare.backend.chat.brain import DEFAULT_MAX_TOKENS, OpenAICompatBrain
    from adare.backend.chat.repl import ChatREPL
    from adare.backend.chat.tools import build_tools
    from adare.config.server import _cfg
    from adare.console import print_error_message

    # Re-read the provider config now (not the import-time constants) so a freshly
    # `adare vlm use`d profile is picked up; env vars still override per the _cfg rule.
    base_url = getattr(arguments, 'base_url', None) or _cfg(
        'ADARE_VLLM_BASE_URL', 'http://localhost:8000/v1')
    api_key = _cfg('ADARE_VLLM_API_KEY', 'EMPTY')
    model = (getattr(arguments, 'model', None)
             or _cfg('ADARE_CHAT_MODEL', None)
             or _cfg('ADARE_VLLM_MODEL', 'Qwen/Qwen2-VL-7B-Instruct'))
    max_tokens = getattr(arguments, 'max_tokens', None) or DEFAULT_MAX_TOKENS
    tool_protocol = getattr(arguments, 'tool_protocol', None) or 'auto'

    try:
        brain = OpenAICompatBrain(
            base_url=base_url, model=model, api_key=api_key,
            tool_protocol=tool_protocol, max_tokens=max_tokens)
    except ValueError as exc:
        print_error_message(
            title='Could not start the chat brain',
            next_steps=[str(exc),
                        'Valid --tool-protocol values: native, json, auto'],
        )
        exit(1)

    log.info('chat brain: model=%s base_url=%s protocol=%s', model, base_url, tool_protocol)
    tools = build_tools()
    ChatREPL(brain, tools).run()
