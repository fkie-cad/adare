"""Reading values at offsets of binary container files, for the ``binary`` testfunction collection.

Many applications keep data in their own binary containers that no parser knows: an entry
file whose last bytes point at a metadata block, an index of fixed-size records, a table of
NUL-separated key/value strings. This module reads such files by offset, without knowing the
format: an *offset expression* says where to look, a *value format* how to read it.

Offset expressions
------------------

An offset is an int (negative = counted from the end of the file: ``-4`` is the last four
bytes) or a string in this grammar (whitespace between tokens is ignored)::

    expr     := term (('+' | '-') NUMBER)*
    term     := ['-'] NUMBER | TYPE '@' operand | 'find:' HEX
    operand  := ['-'] NUMBER | TYPE '@' operand | '(' expr ')'
    NUMBER   := decimal digits | '0x' hex digits
    TYPE     := u8 | i8 | (u|i)(16|32|64)(le|be)

* ``TYPE@operand`` reads an integer of ``TYPE`` at ``operand`` and uses it as the offset:
  ``u32be@-4`` is the offset stored big-endian in the last four bytes.
* ``+N`` / ``-N`` after a term add to its result: ``u32be@-4+8`` is that stored offset plus 8.
  To add inside the read position use parentheses: ``u32le@(u32le@0+4)``.
* ``find:HEX`` is the offset of the first occurrence of the byte pattern ``HEX``
  (``find:00ff`` ...); ``find:6b6579+3`` points just past it. A pattern that does not occur
  cannot be resolved.
* A negative NUMBER counts from the end of the file where it is written (``-8+2`` is
  ``size - 6``); a computed offset that falls outside the file cannot be resolved.

At most :data:`MAX_DEREFERENCES` ``@`` reads and :data:`MAX_EXPRESSION_LENGTH` characters.
A malformed expression raises :class:`BinaryParameterError`; an offset that cannot be
resolved in the file raises :class:`OffsetError`. Testfunctions report both as ERROR: the
check never looked at the claimed value.

Ships with the agent's adarelib wheel; standard library only, importable on Python 3.10.
"""

import codecs
import math
import os
import re
import struct
from dataclasses import dataclass
from typing import Any, BinaryIO

from adarelib.testset.archive import MAX_BYTES_ENV, max_bytes_from_env
from adarelib.testset.content import FileTooLargeError, parse_byte_string

MAX_DEREFERENCES = 4
MAX_EXPRESSION_LENGTH = 200
MAX_CSTRING_BYTES = 1 << 16

# struct format and size of every integer type an offset expression or value format can read
INT_TYPES: dict[str, str] = {'u8': 'B', 'i8': 'b'}
for _bits, _code in ((16, 'h'), (32, 'i'), (64, 'q')):
    for _sign, _letter in (('u', _code.upper()), ('i', _code)):
        INT_TYPES[f'{_sign}{_bits}le'] = '<' + _letter
        INT_TYPES[f'{_sign}{_bits}be'] = '>' + _letter
FLOAT_TYPES: dict[str, str] = {'f32le': '<f', 'f32be': '>f', 'f64le': '<d', 'f64be': '>d'}
VALUE_FORMATS_HELP = 'u8, i8, u16le/be ... i64le/be, f32le/be, f64le/be, bytes:<n>, string:<n>, cstring'


class BinaryParameterError(ValueError):
    """A malformed offset expression, value format or pattern (the test definition is broken)."""


class OffsetError(ValueError):
    """An offset that cannot be resolved in this file (outside it, pattern not found, ...)."""


class NonFiniteValueError(ValueError):
    """A float read from the file is NaN or infinite, so it cannot be compared."""


# ---------------------------------------------------------------------------
# Offset expressions: parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Literal:
    value: int  # negative: from the end of the file


@dataclass(frozen=True)
class Deref:
    type: str
    operand: 'Node'


@dataclass(frozen=True)
class Find:
    pattern: bytes


@dataclass(frozen=True)
class Add:
    base: 'Node'
    addend: int


Node = Literal | Deref | Find | Add

_TOKEN = re.compile(
    r'\s*(?:'
    r'(?P<find>find:(?P<hex>[0-9a-fA-F]*))'
    r'|(?P<type>[ui](?:8|16le|16be|32le|32be|64le|64be))(?=\s*@)'
    r'|(?P<number>0[xX][0-9a-fA-F]+|[0-9]+)'
    r'|(?P<op>[@()+-])'
    r')'
)


def _tokenize(text: str) -> list[tuple[str, Any]]:
    tokens: list[tuple[str, Any]] = []
    position = 0
    text = text.rstrip()
    while position < len(text):
        match = _TOKEN.match(text, position)
        if match is None or match.end() == position:
            raise BinaryParameterError(f'invalid offset expression {text!r}: unexpected {text[position:].strip()!r}')
        if match.group('find') is not None:
            pattern = match.group('hex')
            if not pattern or len(pattern) % 2:
                raise BinaryParameterError(
                    f'invalid offset expression {text!r}: find: needs an even number of hex digits'
                )
            tokens.append(('find', bytes.fromhex(pattern)))
        elif match.group('type') is not None:
            tokens.append(('type', match.group('type')))
        elif match.group('number') is not None:
            number = match.group('number')
            tokens.append(('number', int(number, 16) if number[:2] in ('0x', '0X') else int(number)))
        else:
            tokens.append((match.group('op'), None))
        position = match.end()
    return tokens


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = _tokenize(text)
        self.position = 0
        self.dereferences = 0

    def _error(self, what: str) -> BinaryParameterError:
        return BinaryParameterError(f'invalid offset expression {self.text!r}: {what}')

    def _peek(self) -> str | None:
        return self.tokens[self.position][0] if self.position < len(self.tokens) else None

    def _take(self, kind: str) -> Any:
        if self._peek() != kind:
            found = self._peek() or 'end of expression'
            raise self._error(f'expected {kind}, found {found}')
        value = self.tokens[self.position][1]
        self.position += 1
        return value

    def parse(self) -> Node:
        if not self.tokens:
            raise self._error('empty')
        node = self._expr()
        if self._peek() is not None:
            raise self._error(f'unexpected {self._peek()} after the offset')
        return node

    def _expr(self) -> Node:
        node = self._term()
        while self._peek() in ('+', '-'):
            operator = self._peek()
            self._take(operator)
            sign = 1 if operator == '+' else -1
            node = Add(node, sign * self._take('number'))
        return node

    def _signed_number(self) -> Node:
        if self._peek() == '-':
            self._take('-')
            return Literal(-self._take('number'))
        return Literal(self._take('number'))

    def _deref(self) -> Node:
        type_name = self._take('type')
        self._take('@')
        self.dereferences += 1
        if self.dereferences > MAX_DEREFERENCES:
            raise self._error(f'more than {MAX_DEREFERENCES} @ reads')
        return Deref(type_name, self._operand())

    def _term(self) -> Node:
        kind = self._peek()
        if kind == 'find':
            return Find(self._take('find'))
        if kind == 'type':
            return self._deref()
        if kind in ('number', '-'):
            return self._signed_number()
        raise self._error(f'expected a number, TYPE@offset or find:HEX, found {kind or "end of expression"}')

    def _operand(self) -> Node:
        kind = self._peek()
        if kind == '(':
            self._take('(')
            node = self._expr()
            self._take(')')
            return node
        if kind == 'type':
            return self._deref()
        if kind in ('number', '-'):
            return self._signed_number()
        raise self._error(f'expected a number, TYPE@... or (...) after @, found {kind or "end of expression"}')


def parse_offset(offset: Any) -> Node:
    """The offset expression ``offset`` (an int or a string, see the module docstring) as a tree.

    :raises BinaryParameterError: not an int or a valid expression
    """
    if isinstance(offset, bool) or not isinstance(offset, (int, str)):
        raise BinaryParameterError(f'offset must be an integer or an offset expression, got {offset!r}')
    if isinstance(offset, int):
        return Literal(offset)
    if len(offset) > MAX_EXPRESSION_LENGTH:
        raise BinaryParameterError(f'offset expression longer than {MAX_EXPRESSION_LENGTH} characters')
    return _Parser(offset).parse()


# ---------------------------------------------------------------------------
# Reading a file
# ---------------------------------------------------------------------------


class BinaryFile:
    """An open binary file read by offset; only the bytes asked for are read.

    ``find:`` and regions need more; they are read up to the size cap
    (:func:`adarelib.testset.archive.max_bytes_from_env`).
    """

    def __init__(self, handle: BinaryIO, size: int, path: str = '', max_bytes: int | None = None):
        self.handle = handle
        self.size = size
        self.path = path
        self.max_bytes = max_bytes_from_env() if max_bytes is None else max_bytes
        self._whole: bytes | None = None

    def read_at(self, offset: int, length: int, what: str = 'value') -> bytes:
        """``length`` bytes at ``offset``.

        :raises OffsetError: the bytes are not all inside the file
        :raises FileTooLargeError: ``length`` is over the size cap
        """
        if offset < 0 or length < 0 or offset + length > self.size:
            raise OffsetError(f'{what} at offset {offset} ({length} bytes) is outside the file ({self.size} bytes)')
        if length > self.max_bytes:
            raise FileTooLargeError(
                f'{what} of {length} bytes is over the read cap of {self.max_bytes} bytes (set {MAX_BYTES_ENV})'
            )
        self.handle.seek(offset)
        data = self.handle.read(length)
        if len(data) != length:  # the file shrank while it was read
            raise OffsetError(f'{what} at offset {offset}: only {len(data)} of {length} bytes could be read')
        return data

    def whole(self) -> bytes:
        """The whole file (for ``find:``).

        :raises FileTooLargeError: the file is over the size cap
        """
        if self._whole is None:
            self._whole = self.read_at(0, self.size, 'file')
        return self._whole

    def read_int(self, type_name: str, offset: int) -> int:
        fmt = INT_TYPES[type_name]
        return struct.unpack(fmt, self.read_at(offset, struct.calcsize(fmt), f'{type_name} pointer'))[0]


def _absolute(value: int, size: int) -> int:
    return size + value if value < 0 else value


def _evaluate(node: Node, data: BinaryFile) -> int:
    if isinstance(node, Literal):
        return _absolute(node.value, data.size)
    if isinstance(node, Add):
        return _evaluate(node.base, data) + node.addend
    if isinstance(node, Find):
        position = data.whole().find(node.pattern)
        if position < 0:
            raise OffsetError(f'find:{node.pattern.hex()} does not occur in the file')
        return position
    target = _evaluate(node.operand, data)
    return data.read_int(node.type, target)


def resolve_offset(node: Node, data: BinaryFile, allow_end: bool = False) -> int:
    """The absolute offset ``node`` stands for in ``data``.

    :param allow_end: the file size itself is valid (the end of a region)
    :raises OffsetError: it is outside the file, a read falls outside it, a pattern is missing
    """
    offset = _evaluate(node, data)
    limit = data.size if allow_end else data.size - 1
    if offset < 0 or offset > limit:
        raise OffsetError(f'offset {offset} is outside the file ({data.size} bytes)')
    return offset


def describe(node: Node) -> str:
    """The expression as text (for messages)."""
    if isinstance(node, Literal):
        return str(node.value)
    if isinstance(node, Add):
        return f'{describe(node.base)}{node.addend:+d}'
    if isinstance(node, Find):
        return f'find:{node.pattern.hex()}'
    inner = describe(node.operand)
    return f'{node.type}@({inner})' if isinstance(node.operand, Add) else f'{node.type}@{inner}'


def region(data: BinaryFile, start: Node, end: Node | None) -> tuple[int, int, bytes]:
    """``(start, end, bytes)`` of the region ``[start, end)``; ``end`` None = end of file.

    :raises OffsetError: an offset cannot be resolved, or ``end`` is before ``start``
    :raises FileTooLargeError: the region is over the size cap
    """
    first = resolve_offset(start, data, allow_end=True)
    last = data.size if end is None else resolve_offset(end, data, allow_end=True)
    if last < first:
        raise OffsetError(f'region end {last} is before its start {first}')
    return first, last, data.read_at(first, last - first, 'region')


def open_binary(path: str):
    """Open ``path`` for :class:`BinaryFile`; returns ``(handle, size)``.

    :raises OSError: FileNotFoundError, IsADirectoryError, ...
    """
    handle = open(path, 'rb')  # noqa: SIM115 - closed by the caller
    try:
        size = os.fstat(handle.fileno()).st_size
    except OSError:
        handle.close()
        raise
    return handle, size


# ---------------------------------------------------------------------------
# Value formats
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValueFormat:
    kind: str  # 'int', 'float', 'bytes', 'string', 'cstring'
    name: str
    length: int = 0  # bytes / string length; the struct size for numbers

    @property
    def is_number(self) -> bool:
        return self.kind in ('int', 'float')


def parse_value_format(value_format: Any) -> ValueFormat:
    """The value format named by ``value_format``.

    :raises BinaryParameterError: unknown format or a bad length
    """
    if not isinstance(value_format, str):
        raise BinaryParameterError(f'value_format must be a string ({VALUE_FORMATS_HELP}), got {value_format!r}')
    name = value_format.strip().lower()
    if name in INT_TYPES:
        return ValueFormat('int', name, struct.calcsize(INT_TYPES[name]))
    if name in FLOAT_TYPES:
        return ValueFormat('float', name, struct.calcsize(FLOAT_TYPES[name]))
    if name == 'cstring':
        return ValueFormat('cstring', name)
    kind, _, length = name.partition(':')
    if kind in ('bytes', 'string') and length:
        if not length.isdigit() or int(length) < 1:
            raise BinaryParameterError(f'{kind}:<n> needs a positive length, got {value_format!r}')
        return ValueFormat(kind, name, int(length))
    raise BinaryParameterError(f'unknown value_format {value_format!r} (allowed: {VALUE_FORMATS_HELP})')


def code_unit(encoding: str) -> int:
    """Bytes per code unit of ``encoding`` (the size of its NUL terminator).

    :raises LookupError: unknown encoding
    :raises BinaryParameterError: an encoding without a fixed byte order (``utf-16``)
    """
    name = codecs.lookup(encoding).name
    if name in ('utf-16', 'utf-32', 'utf-8-sig'):
        raise BinaryParameterError(
            f'encoding {encoding!r} writes a byte order mark: use {name}-le or {name}-be'
            if name != 'utf-8-sig'
            else f'encoding {encoding!r} writes a byte order mark: use utf-8'
        )
    if name.startswith('utf-16'):
        return 2
    if name.startswith('utf-32'):
        return 4
    return 1


def read_value(data: BinaryFile, offset: int, fmt: ValueFormat, encoding: str = 'utf-8') -> Any:
    """The value of format ``fmt`` at ``offset``: an int, a float, a hex string or a string.

    ``string:<n>`` drops trailing NUL characters (fixed-size fields are NUL-padded); ``cstring``
    ends at the first NUL code unit (``\\x00\\x00`` for UTF-16).

    :raises OffsetError: the value is not inside the file, or a cstring has no terminator
    :raises UnicodeDecodeError: the string is not valid in ``encoding``
    :raises NonFiniteValueError: a NaN/infinite float
    """
    if fmt.kind == 'int':
        return struct.unpack(INT_TYPES[fmt.name], data.read_at(offset, fmt.length))[0]
    if fmt.kind == 'float':
        value = struct.unpack(FLOAT_TYPES[fmt.name], data.read_at(offset, fmt.length))[0]
        if not math.isfinite(value):
            raise NonFiniteValueError(f'{fmt.name} at offset {offset} is {value}, not a finite number')
        return value
    if fmt.kind == 'bytes':
        return data.read_at(offset, fmt.length).hex()
    if fmt.kind == 'string':
        return data.read_at(offset, fmt.length).decode(encoding).rstrip('\x00')
    unit = code_unit(encoding)
    available = min(data.size - offset, MAX_CSTRING_BYTES)
    raw = data.read_at(offset, max(available, 0), 'cstring')
    for end in range(0, len(raw) - unit + 1, unit):
        if raw[end : end + unit] == b'\x00' * unit:
            return raw[:end].decode(encoding)
    raise OffsetError(f'no NUL terminator within {available} bytes after offset {offset}')


# ---------------------------------------------------------------------------
# Byte patterns and string tables
# ---------------------------------------------------------------------------

PATTERN_TYPES = ('bytes', 'hex', 'regex', 'text')


def compile_pattern(pattern: Any, pattern_type: str, encoding: str = 'utf-8') -> bytes | re.Pattern:
    r"""The bytes (or compiled bytes regex) ``pattern`` stands for.

    ``bytes``: ASCII and Python escapes (``\x00``); ``hex``: hex digits, whitespace allowed;
    ``regex``: an ASCII regular expression over the raw bytes (``\xNN`` for other bytes);
    ``text``: ``pattern`` encoded in ``encoding``.

    :raises BinaryParameterError: empty pattern, unknown type, invalid escape/hex/regex
    :raises LookupError: unknown encoding
    """
    if not isinstance(pattern, str) or not pattern:
        raise BinaryParameterError(f'pattern must be a non-empty string, got {pattern!r}')
    if pattern_type not in PATTERN_TYPES:
        raise BinaryParameterError(f"invalid pattern_type {pattern_type!r} (allowed: {', '.join(PATTERN_TYPES)})")
    try:
        if pattern_type == 'bytes':
            try:
                return parse_byte_string(pattern)
            except ValueError as e:
                raise ValueError(str(e).replace('content_type string', 'pattern_type text')) from e
        if pattern_type == 'hex':
            compiled = bytes.fromhex(pattern)
            if not compiled:
                raise ValueError('no hex digits')
            return compiled
        if pattern_type == 'regex':
            return re.compile(pattern.encode('ascii'))
        code_unit(encoding)
        return pattern.encode(encoding)
    except UnicodeEncodeError as e:
        if pattern_type == 'regex':
            raise BinaryParameterError(f'regex must be ASCII (write \\xNN for other bytes): {e}') from e
        raise BinaryParameterError(f'pattern cannot be encoded as {encoding}: {e}') from e
    except re.error as e:
        raise BinaryParameterError(f'invalid regex {pattern!r}: {e}') from e
    except ValueError as e:
        raise BinaryParameterError(f'invalid {pattern_type} pattern {pattern!r}: {e}') from e


def count_pattern(data: bytes, pattern: bytes | re.Pattern) -> int:
    """Non-overlapping occurrences of ``pattern`` in ``data``; empty regex matches do not count."""
    if isinstance(pattern, bytes):
        return data.count(pattern)
    return sum(1 for match in pattern.finditer(data) if match.end() > match.start())


def split_strings(raw: bytes, separator: bytes, encoding: str) -> list[bytes]:
    """``raw`` split at ``separator`` occurrences aligned to the code unit of ``encoding``.

    One separator at the very end terminates the last string and adds no empty one.

    :raises BinaryParameterError: empty separator or one not a whole number of code units
    """
    unit = code_unit(encoding)
    if not separator or len(separator) % unit:
        raise BinaryParameterError(
            f'separator must be a non-empty whole number of {unit}-byte code units for {encoding}, got {separator!r}'
        )
    items: list[bytes] = []
    start = search = 0
    while True:
        position = raw.find(separator, search)
        while position >= 0 and (position - start) % unit:
            position = raw.find(separator, position + 1)
        if position < 0:
            break
        items.append(raw[start:position])
        start = search = position + len(separator)
    if start < len(raw) or not items:
        items.append(raw[start:])
    return items


def string_table(raw: bytes, separator: bytes, encoding: str) -> list[tuple[str, bytes]]:
    """Alternating key/value strings of ``raw`` as ``(key, raw value)`` pairs.

    Keys are decoded (undecodable bytes become U+FFFD and so match no plain key); values stay
    raw until one is compared.

    :raises BinaryParameterError: bad separator
    :raises OffsetError: an odd number of strings (a key without value: the region is wrong)
    """
    if not raw:
        return []
    items = split_strings(raw, separator, encoding)
    if len(items) % 2:
        raise OffsetError(
            f'the region holds {len(items)} strings, not key/value pairs: check start/end '
            f'(last string: {items[-1][:40]!r})'
        )
    return [(items[i].decode(encoding, 'replace'), items[i + 1]) for i in range(0, len(items), 2)]


def parse_separator(separator: Any) -> bytes:
    r"""The bytes of a ``separator`` parameter (ASCII and Python escapes, ``\x00``).

    :raises BinaryParameterError: not a non-empty valid byte string
    """
    if not isinstance(separator, str) or not separator:
        raise BinaryParameterError(f'separator must be a non-empty string, got {separator!r}')
    try:
        return parse_byte_string(separator)
    except ValueError as e:
        raise BinaryParameterError(str(e)) from e
