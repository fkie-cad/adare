"""Decode a stored value before it is compared: the ``value_decode`` / ``decoded_key_path`` parameters.

Applications often store a value encoded inside a field: percent-encoded in a URL, as base64
or hex text, as UTF-16 bytes, or as a JSON document in a string. Value testfunctions take
``value_decode``, one step or a list of steps applied in order to the value read from the file
(the actual value) before it is compared:

* ``url``: percent-decoding (``%2F`` -> ``/``; a ``+`` stays a ``+``)
* ``base64``: standard or URL-safe alphabet; missing ``=`` padding and whitespace are fine
* ``hex``: hex digits, whitespace between bytes allowed
* ``utf16``: bytes as UTF-16 text (a BOM gives the byte order, little-endian without one;
  trailing NUL characters are dropped). Needs bytes: put ``base64`` or ``hex`` before it
* ``json``: parse JSON text and take the value at ``decoded_key_path`` (key path syntax of
  :func:`adarelib.testset.compare.parse_key_path`); it must select exactly one value

``url``, ``base64`` and ``hex`` produce bytes. A result that is still bytes after the last step
becomes UTF-8 text, or lowercase hex when it is no valid UTF-8.

Every problem raises :class:`ValueDecodeError` naming the step; callers report it as ERROR (the
value could not be read as the test said, so nothing was learnt about it).

Standard library only (plus adarelib), importable on Python 3.10.
"""

import base64
import codecs
import json
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from adarelib.event.event import TestResult
from adarelib.testset.compare import resolve_key_path

DECODE_STEPS = ('url', 'base64', 'hex', 'utf16', 'json')
_SHOWN = 80


class ValueDecodeError(ValueError):
    """A ``value_decode`` parameter or a decode step that failed."""


def _shown(value: Any) -> str:
    shown = repr(value)
    return shown if len(shown) <= _SHOWN else shown[:_SHOWN] + '...'


def _text(value: Any) -> str:
    """The text a step reads: a string, UTF-8 bytes, or a number as its text."""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode('utf-8')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    raise ValueDecodeError(f'needs text, got {type(value).__name__} {_shown(value)}')


def _url(value: Any, _key_path: str | None) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return urllib.parse.unquote_to_bytes(bytes(value))
    return urllib.parse.unquote_to_bytes(_text(value))


def _base64(value: Any, _key_path: str | None) -> bytes:
    data = ''.join(_text(value).split())
    urlsafe = '-' in data or '_' in data
    data += '=' * (-len(data) % 4)
    return base64.b64decode(data, altchars=b'-_' if urlsafe else None, validate=True)


def _hex(value: Any, _key_path: str | None) -> bytes:
    return bytes.fromhex(_text(value))


def _utf16(value: Any, _key_path: str | None) -> str:
    if not isinstance(value, (bytes, bytearray)):
        raise ValueDecodeError(f'needs bytes, got {type(value).__name__} {_shown(value)} (put base64 or hex before it)')
    data = bytes(value)
    encoding = 'utf-16' if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else 'utf-16-le'
    return data.decode(encoding).rstrip('\x00')


def _json(value: Any, key_path: str | None) -> Any:
    parsed = json.loads(_text(value))
    values = resolve_key_path(parsed, key_path or '')
    if not values:
        raise ValueDecodeError(f'decoded_key_path {key_path!r} selects nothing in {_shown(parsed)}')
    if len(values) > 1:
        raise ValueDecodeError(
            f'decoded_key_path {key_path!r} selects {len(values)} values; it must select exactly one'
        )
    return values[0]


_STEPS: dict[str, Callable[[Any, str | None], Any]] = {
    'url': _url,
    'base64': _base64,
    'hex': _hex,
    'utf16': _utf16,
    'json': _json,
}


def _bytes_result(data: bytes) -> str:
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return data.hex()


@dataclass(frozen=True)
class ValueDecoder:
    """A validated ``value_decode`` chain (see the module docstring)."""

    steps: tuple[str, ...]
    key_path: str | None = None

    def __call__(self, value: Any, as_text: bool = False) -> Any:
        """``value`` decoded by every step; ``as_text``: a non-string result as its JSON text.

        :raises ValueDecodeError: a step that cannot decode the value
        """
        current = value
        for step in self.steps:
            try:
                current = _STEPS[step](current, self.key_path)
            except ValueDecodeError as e:
                raise ValueDecodeError(f'value_decode step {step!r}: {e}') from e
            except ValueError as e:  # binascii.Error, UnicodeDecodeError, JSONDecodeError
                raise ValueDecodeError(f'value_decode step {step!r} cannot decode {_shown(current)}: {e}') from e
        if isinstance(current, (bytes, bytearray)):
            current = _bytes_result(bytes(current))
        if as_text and not isinstance(current, str):
            current = json.dumps(current, ensure_ascii=False)
        return current

    def describe(self) -> str:
        return ' -> '.join(self.steps)


def build_decoder(value_decode: Any = None, decoded_key_path: Any = None) -> ValueDecoder | None:
    """The validated decoder, or ``None`` without ``value_decode`` (compare the value as read).

    :raises ValueDecodeError: unknown steps, ``json`` without ``decoded_key_path`` (or twice),
        ``decoded_key_path`` without ``json``
    """
    if value_decode is None or value_decode == [] or value_decode == '':
        if decoded_key_path is not None:
            raise ValueDecodeError("decoded_key_path needs a 'json' step in value_decode")
        return None
    steps = [value_decode] if isinstance(value_decode, str) else value_decode
    if not isinstance(steps, (list, tuple)):
        raise ValueDecodeError(f'value_decode must be a step name or a list of them, got {_shown(value_decode)}')
    errors = []
    unknown = [s for s in steps if not isinstance(s, str) or s not in DECODE_STEPS]
    if unknown:
        errors.append(
            f'unknown value_decode step(s) {", ".join(map(repr, unknown))} (allowed: {", ".join(DECODE_STEPS)})'
        )
    if steps.count('json') > 1:
        errors.append("value_decode may contain 'json' only once (there is one decoded_key_path)")
    if 'json' in steps and (not isinstance(decoded_key_path, str) or not decoded_key_path):
        errors.append("value_decode step 'json' needs decoded_key_path (the key path of the value to compare)")
    if 'json' not in steps and decoded_key_path is not None:
        errors.append("decoded_key_path needs a 'json' step in value_decode")
    if errors:
        raise ValueDecodeError('; '.join(errors))
    return ValueDecoder(tuple(steps), decoded_key_path)


def decoder_setup(
    value_decode: Any = None, decoded_key_path: Any = None
) -> tuple[ValueDecoder | None, TestResult | None]:
    """``(decoder or None, None)``, or ``(None, error_result)`` for bad decode parameters."""
    try:
        return build_decoder(value_decode, decoded_key_path), None
    except ValueDecodeError as e:
        return None, TestResult.error([str(e)])
