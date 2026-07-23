"""Thin OpenAI-compatible client for a vision-LLM served by vLLM.

The client is intentionally minimal: it speaks the ``/v1/chat/completions``
protocol with multi-modal messages (data-URI images + text) over ``httpx``.
It is model-agnostic — any grounding-capable vision model (Qwen2-VL, UI-TARS,
Molmo-class) works; :data:`VLLM_COORD_SPACE` reconciles coordinate conventions
downstream in :mod:`adare.backend.experiment.vlm.actions`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .exceptions import VLMError

log = logging.getLogger(__name__)

# Bounded retry for transport-level failures (read timeout / connection reset)
# on the decision POST. A single network hiccup against a remote endpoint
# (e.g. Ollama Cloud) must not abort a whole agent run. HTTP-status errors
# (4xx/5xx) are NOT retried here — a real auth/server error surfaces at once.
_TRANSPORT_RETRIES = 3
_TRANSPORT_BACKOFF_BASE = 1.5  # seconds; grows exponentially per attempt


class VLMClient:
    """Async client for an OpenAI-compatible vision-LLM endpoint."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = 'EMPTY',
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    # -- message builders ---------------------------------------------------

    @staticmethod
    def image_content(png_base64: str) -> dict[str, Any]:
        """Build an ``image_url`` content part from a base64 PNG string."""
        return {
            'type': 'image_url',
            'image_url': {'url': f'data:image/png;base64,{png_base64}'},
        }

    @staticmethod
    def text_content(text: str) -> dict[str, Any]:
        """Build a ``text`` content part."""
        return {'type': 'text', 'text': text}

    # -- request ------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        """Send a chat completion request and return the assistant text.

        Raises:
            VLMError: on transport failure, non-2xx status, or a response shape
                that does not contain a message.
        """
        url = f'{self.base_url}/chat/completions'
        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

        data = await self._post_with_retry(url, payload, headers)

        try:
            content = data['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise VLMError(f'Unexpected vLLM response shape: {data!r}') from exc

        if not isinstance(content, str):
            raise VLMError(f'vLLM message content was not text: {content!r}')
        return content

    async def _post_with_retry(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        """POST the payload, retrying only transport-level failures.

        ``httpx.TransportError`` (read timeouts, connection resets — the class
        whose ``str(exc)`` is often empty) is retried with exponential backoff
        up to :data:`_TRANSPORT_RETRIES` attempts. ``httpx.HTTPStatusError``
        (a real 4xx/5xx) is raised immediately — retrying an auth or server
        error only hides it. The error message names the exception *type* so an
        empty-``str(exc)`` transport error is still identifiable in logs.
        """
        last_exc: httpx.TransportError | None = None
        for attempt in range(1, _TRANSPORT_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    return resp.json()
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < _TRANSPORT_RETRIES:
                    delay = _TRANSPORT_BACKOFF_BASE ** attempt
                    log.warning(
                        'vLLM transport error on attempt %d/%d (%s: %s); '
                        'retrying in %.1fs',
                        attempt, _TRANSPORT_RETRIES,
                        type(exc).__name__, exc, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
            except httpx.HTTPError as exc:
                # Non-transport HTTP errors — chiefly httpx.HTTPStatusError from
                # raise_for_status() (a real 4xx/5xx). Surface immediately, never
                # retry: an auth or server error will not fix itself.
                raise VLMError(
                    f'vLLM request to {url} failed: '
                    f'{type(exc).__name__}: {exc}'
                ) from exc
            except ValueError as exc:  # JSON decode
                raise VLMError(f'vLLM returned non-JSON response: {exc}') from exc

        raise VLMError(
            f'vLLM request to {url} failed after {_TRANSPORT_RETRIES} attempts: '
            f'{type(last_exc).__name__}: {last_exc}'
        ) from last_exc
