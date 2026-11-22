"""Reading file content for the built-in testfunction collections: BOMs, encodings, size caps,
byte-string parameters, file hashes, duration parameters.

Ships with the agent's adarelib wheel (see :mod:`adarelib.testset.compare` for how collections
and adarelib stay in step). Standard library only, importable on Python 3.10.
"""

import codecs
import hashlib
import os
import re

from adarelib.testset.archive import MAX_BYTES_ENV, max_bytes_from_env

# longest first: the UTF-32-LE BOM starts with the UTF-16-LE one
_BOMS: tuple[tuple[bytes, str], ...] = (
    (b'\xff\xfe\x00\x00', 'utf-32-le'),
    (b'\x00\x00\xfe\xff', 'utf-32-be'),
    (b'\xef\xbb\xbf', 'utf-8'),
    (b'\xff\xfe', 'utf-16-le'),
    (b'\xfe\xff', 'utf-16-be'),
)


class FileTooLargeError(OSError):
    """The file is larger than the read cap (an OSError, so readers report it as an ERROR)."""


def detect_bom(raw: bytes) -> tuple[str | None, int]:
    """Encoding named by the byte order mark at the start of ``raw``, and the BOM's length."""
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            return encoding, len(bom)
    return None, 0


def detect_encoding_from_bom(file_path: str) -> tuple[str | None, int]:
    """Detect encoding from the file's BOM; return ``(encoding, bom_length)`` or ``(None, 0)``."""
    with open(file_path, 'rb') as f:
        return detect_bom(f.read(4))


def strip_bom_from_text(text: str, encoding: str) -> str:
    """Strip a decoded BOM (U+FEFF) from the start of text read as UTF-8/16/32."""
    if encoding.lower().startswith(('utf-8', 'utf-16', 'utf-32')) and text.startswith('﻿'):
        return text[1:]
    return text


def read_bytes_capped(path: str, max_bytes: int | None = None) -> bytes:
    """Read the whole file, refusing files over ``max_bytes`` (default: the archive size cap).

    :raises FileTooLargeError: the file is larger than the cap
    :raises OSError: the file cannot be read (FileNotFoundError when it does not exist)
    """
    cap = max_bytes_from_env() if max_bytes is None else max_bytes
    size = os.path.getsize(path)
    if size > cap:
        raise FileTooLargeError(f'{path} is {size} bytes, over the read cap of {cap} bytes (set {MAX_BYTES_ENV})')
    with open(path, 'rb') as f:
        return f.read()


def guess_utf16(raw: bytes) -> str | None:
    """``utf-16-le``/``-be`` for BOM-less text whose first character is ASCII, else None."""
    if len(raw) >= 2 and len(raw) % 2 == 0:
        if raw[0] != 0 and raw[1] == 0:
            return 'utf-16-le'
        if raw[0] == 0 and raw[1] != 0:
            return 'utf-16-be'
    return None


def decode_text(raw: bytes, encoding: str | None = None) -> str:
    """Decode file content; a BOM always wins and is removed.

    Without a BOM, ``encoding`` is used; ``None`` means auto: BOM-less UTF-16 is recognised by
    its zero bytes, everything else is read as UTF-8.

    :raises UnicodeDecodeError: the content is not valid in the chosen encoding
    :raises LookupError: unknown encoding name
    """
    bom_encoding, bom_length = detect_bom(raw)
    if bom_encoding is not None:
        return raw[bom_length:].decode(bom_encoding)
    if encoding is None:
        encoding = guess_utf16(raw) or 'utf-8'
    return raw.decode(encoding)


# the escapes allowed in a byte string; anything else after a backslash is refused: an escape
# unicode_escape does not know (``\q`` would silently stay two characters), a \u/\U/\N escape
# (characters, not bytes), a backslash-newline (silently dropped)
_BYTE_ESCAPE = re.compile(r'\\(x[0-9a-fA-F]{2}|[0-7]{1,3}|[\\\'"abfnrtv])')


def parse_byte_string(content: str) -> bytes:
    r"""The bytes a ``content_type: bytes`` parameter stands for.

    Only ASCII characters (each stands for its byte) and Python escapes (``\x00``, ``\n``,
    ``\\``, octal ``\0``) are allowed, so no byte value depends on a guessed encoding.

    :raises ValueError: a non-ASCII character, an unknown escape (``\q``), a ``\u``/``\U``/
        ``\N`` escape, an octal escape above ``\377``, or a trailing backslash
    """
    for position, char in enumerate(content):
        if ord(char) > 0x7F:
            raise ValueError(
                f'content_type bytes takes ASCII characters and escapes only, got {char!r} at position '
                f'{position}: write \\xNN escapes, or use content_type string with an encoding'
            )
    position = 0
    while True:
        position = content.find('\\', position)
        if position < 0:
            break
        match = _BYTE_ESCAPE.match(content, position)
        if match is not None and match.group(1)[0] in '01234567' and int(match.group(1), 8) > 0o377:
            match = None  # an octal escape above \377 is a character, not a byte
        if match is None:
            raise ValueError(
                f'invalid escape sequence {content[position : position + 2]!r} at position {position} in '
                f'content (allowed: \\xNN, octal, \\n, \\r, \\t, \\\\, ...): write \\xNN escapes, or '
                f'use content_type string with an encoding'
            )
        position = match.end()
    try:
        return codecs.decode(content.encode('ascii'), 'unicode_escape').encode('latin-1')
    except UnicodeError as e:  # an octal escape above \377
        raise ValueError(
            f'octal escape above \\377 in content ({e}): write \\xNN escapes, or use content_type string with an encoding'
        ) from e


HASH_TYPES = ('md5', 'sha1', 'sha256', 'sha512')


def file_hash(path: str, hash_type: str) -> str:
    """Hex digest of the file at ``path``; ``hash_type`` (case-insensitive) is one of HASH_TYPES.

    :raises ValueError: unsupported hash type
    :raises OSError: the file cannot be read
    """
    name = hash_type.lower()
    if name not in HASH_TYPES:
        raise ValueError(f'Unsupported hash type: {hash_type}')
    hasher = hashlib.new(name)
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


_DURATION_UNITS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
_DURATION = re.compile(r'([0-9]+)([smhd])')


def parse_duration(duration: str) -> int:
    """Seconds in a duration like ``30s``, ``5m``, ``1h``, ``2d``.

    :raises ValueError: anything else
    """
    match = _DURATION.fullmatch(duration) if isinstance(duration, str) else None
    if match is None:
        raise ValueError(f'Invalid duration format: {duration} (a whole number and s, m, h or d, e.g. 30m)')
    return int(match.group(1)) * _DURATION_UNITS[match.group(2)]
