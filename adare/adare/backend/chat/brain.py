"""Pluggable chat brains for the embedded ``adare chat`` REPL.

A :class:`ChatBrain` decides which tools to call. The REPL owns the agent loop
and the tool registry; the brain owns its provider-native message history and
turns the conversation-so-far into the next assistant turn (text + tool calls).

The default (and only) brain is :class:`OpenAICompatBrain`, which speaks the
OpenAI ``/chat/completions`` protocol against whatever endpoint the user already
configured for ``adare vlm`` (vLLM / Ollama-cloud / custom) — no Anthropic
dependency, no new provider layer. It supports two tool-call protocols:

* ``native`` — OpenAI ``tools=[…]`` function-calling, read back from
  ``choices[0].message.tool_calls``. Server-validated; best on tool-capable
  models/endpoints (vLLM, tool-capable Ollama models).
* ``json`` — a JSON-in-text contract (ADARE's existing convention, mirroring
  :data:`actions.ACTION_SCHEMA_DOC`): the model emits ``{"tool": …}`` or
  ``{"final": …}``, parsed with the reused :func:`actions._extract_json_object`
  (+ :func:`author_playbook.strip_think`) with a bounded self-heal on a parse
  slip. Works on any chat model.
* ``auto`` (default) — try ``native``; on a tools-related request error
  (HTTP 400/422 whose body names tools/function/unsupported) switch the session
  to ``json`` once and replay.

The brain-owns-history split keeps the REPL fully provider-agnostic: it only ever
sees :class:`ToolCall` / :class:`ToolResult` / :class:`BrainResponse`.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

from adare.backend.experiment.vlm.actions import _extract_json_object
from adare.backend.experiment.vlm.authoring.author_playbook import strip_think
from adare.backend.experiment.vlm.exceptions import VLMError

if TYPE_CHECKING:
    from adare.backend.chat.tools import ChatTool

log = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 4096
DEFAULT_HEAL_RETRIES = 2
_TOOL_PROTOCOLS = ('native', 'json', 'auto')


@dataclass
class ToolCall:
    """A single tool invocation the brain wants the REPL to execute."""
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolResult:
    """The normalized ``{ok, data|error}`` envelope for one executed tool call."""
    id: str
    name: str
    output: dict[str, Any]
    is_error: bool = False


@dataclass
class BrainResponse:
    """One assistant turn: visible text and any requested tool calls."""
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    done: bool = True


class ChatBrain(ABC):
    """A brain owns its message history and yields the next assistant turn.

    The REPL drives it as: :meth:`start` once, then per user turn
    ``resp = send_user(text)`` and, while ``resp.tool_calls``, execute them and
    feed the envelopes back via :meth:`send_tool_results`.
    """

    name: str = 'brain'

    @abstractmethod
    def start(self, system: str, tools: list[ChatTool]) -> None:
        """Initialize the session with a system prompt and the tool registry."""
        raise NotImplementedError

    @abstractmethod
    def send_user(self, text: str) -> BrainResponse:
        """Append a user message and produce the next assistant turn."""
        raise NotImplementedError

    @abstractmethod
    def send_tool_results(self, results: list[ToolResult]) -> BrainResponse:
        """Append tool results and produce the next assistant turn."""
        raise NotImplementedError


class _ToolsUnsupported(RuntimeError):
    """Raised internally when an endpoint rejects the ``tools`` parameter."""


class OpenAICompatBrain(ChatBrain):
    """Brain over an OpenAI-compatible ``/chat/completions`` endpoint.

    Reuses the ``adare vlm`` provider config (``base_url`` / ``api_key`` /
    ``model``) via :mod:`plain httpx`; ``VLMClient`` itself is not reused because
    it discards everything but the message ``content`` (we need ``tool_calls``).
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = 'EMPTY',
        tool_protocol: str = 'auto',
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.0,
        timeout: float = 300.0,
        heal_retries: int = DEFAULT_HEAL_RETRIES,
    ):
        if tool_protocol not in _TOOL_PROTOCOLS:
            raise ValueError(
                f'Unknown tool protocol {tool_protocol!r}; expected one of {_TOOL_PROTOCOLS}')
        self._base_url = base_url.rstrip('/')
        self.model = model
        self._api_key = api_key
        self._requested = tool_protocol
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._heal_retries = heal_retries
        self._client = httpx.Client(timeout=timeout)

        # Session state (populated in start()).
        self._protocol = 'native'
        self._auto = False
        self._base_system = ''
        self._tools: list[ChatTool] = []
        self._native_tools: list[dict[str, Any]] = []
        self._messages: list[dict[str, Any]] = []
        self._counter = 0
        self.name = f'openai-compat:{model} [{tool_protocol}]'

    # -- session lifecycle --------------------------------------------------

    def start(self, system: str, tools: list[ChatTool]) -> None:
        self._base_system = system
        self._tools = list(tools)
        self._native_tools = [self._to_native_tool(t) for t in self._tools]
        self._protocol = 'json' if self._requested == 'json' else 'native'
        self._auto = self._requested == 'auto'
        self._counter = 0
        self._messages = [{'role': 'system', 'content': self._system_for(self._protocol)}]

    def send_user(self, text: str) -> BrainResponse:
        self._messages.append({'role': 'user', 'content': text})
        return self._turn()

    def send_tool_results(self, results: list[ToolResult]) -> BrainResponse:
        if self._protocol == 'native':
            for r in results:
                self._messages.append({
                    'role': 'tool',
                    'tool_call_id': r.id,
                    'content': json.dumps(r.output, default=str),
                })
        else:
            blocks = '\n\n'.join(
                f'Tool `{r.name}` returned:\n{json.dumps(r.output, default=str)}'
                for r in results
            )
            self._messages.append({
                'role': 'user',
                'content': blocks + '\n\nContinue: reply with the next tool call, '
                'or {"final": "..."} if the task is done.',
            })
        return self._turn()

    # -- turn dispatch ------------------------------------------------------

    def _turn(self) -> BrainResponse:
        if self._protocol == 'native':
            return self._native_turn()
        return self._json_turn()

    def _native_turn(self) -> BrainResponse:
        try:
            msg = self._post(tools=self._native_tools)
        except _ToolsUnsupported as exc:
            # auto-only: this endpoint/model can't take `tools`. Switch once.
            log.info('Endpoint rejected native tool-calling; falling back to the '
                     'JSON-in-text protocol. (%s)', str(exc)[:200])
            self._switch_to_json()
            return self._json_turn()

        self._messages.append(msg)  # assistant message echoed back verbatim
        tool_calls: list[ToolCall] = []
        for tc in msg.get('tool_calls') or []:
            fn = tc.get('function') or {}
            try:
                args = json.loads(fn.get('arguments') or '{}')
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            tool_calls.append(ToolCall(id=tc.get('id') or self._next_id(),
                                       name=fn.get('name', ''), input=args))
        text = _coerce_text(msg.get('content'))
        return BrainResponse(text=text, tool_calls=tool_calls, done=not tool_calls)

    def _json_turn(self) -> BrainResponse:
        msg = self._post(tools=None)
        reply = _coerce_text(msg.get('content'))
        self._messages.append({'role': 'assistant', 'content': reply})
        try:
            return self._parse_json_turn(reply)
        except VLMError as exc:
            return self._json_self_heal(reply, exc)

    # -- json protocol parsing + self-heal ----------------------------------

    def _parse_json_turn(self, reply: str) -> BrainResponse:
        obj = _extract_json_object(strip_think(reply))
        if 'final' in obj:
            return BrainResponse(text=str(obj['final']), tool_calls=[], done=True)
        if 'tool' in obj:
            name = str(obj['tool'])
            args = obj.get('arguments') or obj.get('args') or {}
            if not isinstance(args, dict):
                raise VLMError(f'"arguments" must be an object, got: {args!r}')
            tc = ToolCall(id=self._next_id(), name=name, input=args)
            return BrainResponse(text=str(obj.get('reasoning', '')),
                                 tool_calls=[tc], done=False)
        raise VLMError('JSON object had neither a "tool" nor a "final" key')

    def _json_self_heal(self, bad_reply: str, exc: VLMError) -> BrainResponse:
        """Bounded repair for a JSON-contract parse slip (mirrors agent._recover_decision)."""
        last_reply, last_exc = bad_reply, exc
        for attempt in range(1, self._heal_retries + 1):
            log.warning('Chat tool-call parse failed (attempt %d/%d): %s; requesting a repair',
                        attempt, self._heal_retries, last_exc)
            self._messages.append({
                'role': 'user',
                'content': (
                    f'Your last reply could not be parsed ({last_exc}). Reply with '
                    'ONLY a single JSON object and nothing else — either '
                    '{"tool": "<name>", "arguments": {...}} to call a tool, or '
                    '{"final": "<answer>"} if the task is done.'
                ),
            })
            msg = self._post(tools=None)
            reply = _coerce_text(msg.get('content'))
            self._messages.append({'role': 'assistant', 'content': reply})
            try:
                return self._parse_json_turn(reply)
            except VLMError as rexc:
                last_reply, last_exc = reply, rexc
        # Give up gracefully: surface the raw reply as text rather than crash.
        return BrainResponse(text=last_reply.strip() or f'(unparseable reply: {last_exc})',
                             tool_calls=[], done=True)

    # -- transport ----------------------------------------------------------

    def _post(self, *, tools: list[dict[str, Any]] | None) -> dict[str, Any]:
        url = f'{self._base_url}/chat/completions'
        payload: dict[str, Any] = {
            'model': self.model,
            'messages': self._messages,
            'temperature': self._temperature,
            'max_tokens': self._max_tokens,
        }
        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = 'auto'
        headers = {
            'Authorization': f'Bearer {self._api_key}',
            'Content-Type': 'application/json',
        }
        try:
            resp = self._client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text
            if (tools and self._auto and self._protocol == 'native'
                    and exc.response.status_code in (400, 422)
                    and _mentions_tools(body)):
                raise _ToolsUnsupported(body) from exc
            raise RuntimeError(
                f'chat endpoint {url} returned HTTP {exc.response.status_code}: '
                f'{body[:400]}') from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f'chat request to {url} failed: {exc}. Check the endpoint is up, or '
                'configure a provider with `adare vlm use`.') from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError(f'chat endpoint returned non-JSON: {exc}') from exc
        try:
            return data['choices'][0]['message']
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f'unexpected chat response shape: {data!r}') from exc

    # -- helpers ------------------------------------------------------------

    def _switch_to_json(self) -> None:
        self._protocol = 'json'
        self._auto = False  # committed for the rest of the session
        if self._messages:
            self._messages[0] = {'role': 'system', 'content': self._system_for('json')}
        self.name = f'openai-compat:{self.model} [json (auto-fallback)]'

    def _system_for(self, protocol: str) -> str:
        if protocol == 'native':
            return self._base_system
        return self._base_system + '\n\n' + self._contract_doc()

    def _contract_doc(self) -> str:
        """Document the registry as a JSON contract (mirrors ACTION_SCHEMA_DOC)."""
        lines = [
            'TOOL PROTOCOL — this endpoint has no native function-calling, so you '
            'call tools via JSON. Reply with a SINGLE JSON object and NOTHING else:',
            '  {"tool": "<tool_name>", "arguments": { ... }}   # to call one tool',
            '  {"final": "<your answer to the user>"}          # when no more tools are needed',
            '',
            'Call exactly one tool per reply; you will be shown its result and may '
            'then call another. Available tools:',
        ]
        for t in self._tools:
            lines.append(f'- {t.name}: {t.description}')
            props = (t.parameters or {}).get('properties') or {}
            required = set((t.parameters or {}).get('required') or [])
            if not props:
                lines.append('    arguments: (none)')
                continue
            for pname, spec in props.items():
                ptype = spec.get('type', 'any')
                req = 'required' if pname in required else 'optional'
                desc = spec.get('description', '')
                lines.append(f'    - {pname} ({ptype}, {req}): {desc}')
        return '\n'.join(lines)

    def _to_native_tool(self, tool: ChatTool) -> dict[str, Any]:
        return {
            'type': 'function',
            'function': {
                'name': tool.name,
                'description': tool.description,
                'parameters': tool.parameters,
            },
        }

    def _next_id(self) -> str:
        self._counter += 1
        return f'call_{self._counter}'


def _coerce_text(content: Any) -> str:
    """Coerce an OpenAI message ``content`` (str | None | list-of-parts) to text."""
    if content is None:
        return ''
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get('type') == 'text':
                parts.append(part.get('text', ''))
            elif isinstance(part, str):
                parts.append(part)
        return ''.join(parts)
    return str(content)


def _mentions_tools(body: str) -> bool:
    low = (body or '').lower()
    return any(k in low for k in ('tool', 'function', 'unsupported'))
