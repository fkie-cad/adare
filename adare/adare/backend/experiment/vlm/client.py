"""Thin OpenAI-compatible client for a vision-LLM served by vLLM.

The client is intentionally minimal: it speaks the ``/v1/chat/completions``
protocol with multi-modal messages (data-URI images + text) over ``httpx``.
It is model-agnostic — any grounding-capable vision model (Qwen2-VL, UI-TARS,
Molmo-class) works; :data:`VLLM_COORD_SPACE` reconciles coordinate conventions
downstream in :mod:`adare.backend.experiment.vlm.actions`.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .exceptions import VLMError

log = logging.getLogger(__name__)


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

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise VLMError(f'vLLM request to {url} failed: {exc}') from exc
        except ValueError as exc:  # JSON decode
            raise VLMError(f'vLLM returned non-JSON response: {exc}') from exc

        try:
            content = data['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise VLMError(f'Unexpected vLLM response shape: {data!r}') from exc

        if not isinstance(content, str):
            raise VLMError(f'vLLM message content was not text: {content!r}')
        return content
