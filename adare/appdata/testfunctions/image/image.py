# Image metadata: PNG text chunks, EXIF tags and pixel dimensions.
#
# PNG text chunks are read by an own stdlib (struct/zlib) chunk walker rather than Pillow:
# Pillow stops collecting text at the first IDAT unless the image data is decoded, does not
# report duplicate keywords and does not verify every CRC. The walker visits every chunk up
# to IEND, checks each CRC and keeps duplicates, so the evidence is read exactly as stored.
#
# EXIF and dimensions use Pillow (requirements.txt), imported at module top like the excel
# collection imports pandas: the collection's requirements are installed with it.
#
# Python 3.10 syntax (guest code).

import io
import os
import re
import struct
import warnings
import zlib
from dataclasses import dataclass
from typing import Any

from PIL import ExifTags, Image, UnidentifiedImageError

# internal imports
from adarelib.testset.api import testfunction
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult
from adarelib.testset.content import read_bytes_capped
from adarelib.testset.structured import WILDCARD_MODES, compare_count, compare_value, count_parameter_errors

# configure logging
import logging

log = logging.getLogger(__name__)

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
# a decompressed zTXt/iTXt text larger than this is refused (decompression bomb guard)
MAX_TEXT_BYTES = 16 * 1024 * 1024

EXIF_IFD = 0x8769
GPS_IFD = 0x8825
# tags whose BYTE value is UTF-16-LE text (title/comment/author/keywords/subject)
UTF16_TAGS = frozenset(range(0x9C9B, 0x9CA0))
USER_COMMENT = 0x9286
_USER_COMMENT_CODES = {b'ASCII\x00\x00\x00': 'ascii', b'UNICODE\x00': 'utf-16', b'\x00' * 8: 'utf-8'}

# What Pillow raises for a file it cannot read as an image or whose metadata is corrupt.
# DecompressionBombError is not an OSError, so it is listed on its own.
PILLOW_ERRORS = (
    UnidentifiedImageError,
    Image.DecompressionBombError,
    OSError,
    SyntaxError,
    ValueError,
    EOFError,
    struct.error,
)


class PngError(ValueError):
    """The file is not a well-formed PNG (signature, truncation, CRC, malformed text chunk)."""


@dataclass(frozen=True)
class PngText:
    """One tEXt/zTXt/iTXt chunk."""

    chunk: str
    keyword: str
    text: str


# =============================================================================
# File loading
# =============================================================================


def _read_file(resolved: tuple[str, str], dst: str, label: str) -> tuple[bytes | None, str, TestResult | None]:
    """Read the file ``ctx.resolve_globfilepath(dst)`` gave (``resolved``).

    Returns ``(raw, path, None)`` or ``(None, path, error_result)``.
    """
    path, status = resolved
    if not path:
        return None, '', TestResult.error([f'{label} file {dst} not found ({status})'])
    log.debug(f'dst file {path} will be used for this {label} test')
    try:
        return read_bytes_capped(path), path, None
    except FileNotFoundError:
        return None, path, TestResult.error([f'{label} file {path} does not exist'])
    except IsADirectoryError:
        return None, path, TestResult.error([f'{label} file {path} is a directory'])
    except OSError as e:
        return None, path, TestResult.execution_error(e, f'Cannot read {label} file {path}')


def _image_path(resolved: tuple[str, str], dst: str) -> tuple[str, TestResult | None]:
    """The image file ``ctx.resolve_globfilepath(dst)`` gave, checked; Pillow opens it lazily
    (headers only), so dimensions and EXIF need no read cap."""
    path, status = resolved
    if not path:
        return '', TestResult.error([f'image file {dst} not found ({status})'])
    if os.path.isdir(path):
        return path, TestResult.error([f'image file {path} is a directory'])
    if not os.path.exists(path):
        return path, TestResult.error([f'image file {path} does not exist'])
    return path, None


# =============================================================================
# PNG text chunks (stdlib only)
# =============================================================================


def _inflate(data: bytes, what: str) -> bytes:
    """zlib-decompress ``data``, refusing results over :data:`MAX_TEXT_BYTES`."""
    inflater = zlib.decompressobj()
    try:
        out = inflater.decompress(data, MAX_TEXT_BYTES)
    except zlib.error as e:
        raise PngError(f'{what}: cannot decompress text ({e})') from e
    if inflater.unconsumed_tail:
        raise PngError(f'{what}: decompressed text exceeds {MAX_TEXT_BYTES} bytes')
    if not inflater.eof:
        raise PngError(f'{what}: compressed text is truncated')
    return out


def _split_keyword(body: bytes, what: str) -> tuple[str, bytes]:
    """Split ``keyword\\0rest``; the keyword is Latin-1."""
    keyword, sep, rest = body.partition(b'\x00')
    if not sep:
        raise PngError(f'{what}: no keyword terminator')
    return keyword.decode('latin-1'), rest


def _parse_text_chunk(ctype: str, body: bytes, offset: int) -> PngText:
    """Decode a tEXt (Latin-1), zTXt (zlib, Latin-1) or iTXt (UTF-8, optionally zlib) body."""
    what = f'{ctype} chunk at offset {offset}'
    keyword, rest = _split_keyword(body, what)
    if ctype == 'tEXt':
        return PngText(ctype, keyword, rest.decode('latin-1'))
    if ctype == 'zTXt':
        if not rest or rest[0] != 0:
            raise PngError(f'{what}: unknown compression method')
        return PngText(ctype, keyword, _inflate(rest[1:], what).decode('latin-1'))
    # iTXt: compression flag, method, language tag\0, translated keyword\0, text
    if len(rest) < 2:
        raise PngError(f'{what}: truncated header')
    compressed, method = rest[0], rest[1]
    _language, sep1, rest = rest[2:].partition(b'\x00')
    _translated, sep2, text = rest.partition(b'\x00')
    if not (sep1 and sep2):
        raise PngError(f'{what}: missing language tag or translated keyword terminator')
    if compressed:
        if method != 0:
            raise PngError(f'{what}: unknown compression method')
        text = _inflate(text, what)
    try:
        return PngText(ctype, keyword, text.decode('utf-8'))
    except UnicodeDecodeError as e:
        raise PngError(f'{what}: text is not UTF-8 ({e})') from e


def parse_png_text(data: bytes) -> list[PngText]:
    """Every text chunk of a PNG, in file order (also those after IDAT).

    :raises PngError: bad signature, truncated chunk, CRC mismatch, malformed text chunk,
        missing IEND
    """
    if not data.startswith(PNG_SIGNATURE):
        raise PngError('not a PNG file (bad signature)')
    texts = []
    pos = len(PNG_SIGNATURE)
    while pos + 8 <= len(data):
        length, raw_type = struct.unpack('>I4s', data[pos : pos + 8])
        end = pos + 12 + length
        if end > len(data):
            raise PngError(f'truncated chunk at offset {pos}')
        body = data[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack('>I', data[end - 4 : end])
        ctype = raw_type.decode('latin-1')
        if zlib.crc32(raw_type + body) & 0xFFFFFFFF != crc:
            raise PngError(f'CRC mismatch in {ctype!r} chunk at offset {pos}')
        if ctype == 'IEND':
            return texts
        if ctype in ('tEXt', 'zTXt', 'iTXt'):
            texts.append(_parse_text_chunk(ctype, body, pos))
        pos = end
    raise PngError('truncated PNG: no IEND chunk')


def _load_png_text(resolved: tuple[str, str], dst: str) -> tuple[list[PngText] | None, TestResult | None]:
    raw, path, error = _read_file(resolved, dst, 'PNG')
    if error is not None:
        return None, error
    try:
        return parse_png_text(raw), None
    except PngError as e:
        return None, TestResult.execution_error(e, f'Invalid PNG file {path}')


def _expected_text(expected: Any) -> Any:
    """Text values: compare a YAML number/bool as its text (``3``, ``true``)."""
    if isinstance(expected, bool):
        return 'true' if expected else 'false'
    if isinstance(expected, (int, float)):
        return str(expected)
    return expected


# =============================================================================
# EXIF (Pillow)
# =============================================================================


def _reverse(tags: dict[int, str]) -> dict[str, list[int]]:
    names: dict[str, list[int]] = {}
    for tag_id, name in tags.items():
        names.setdefault(name, []).append(tag_id)
    return names


_MAIN_NAMES = _reverse(ExifTags.TAGS)
_GPS_NAMES = _reverse(ExifTags.GPSTAGS)
_IFD_LABELS = {0: 'IFD0', EXIF_IFD: 'Exif IFD', GPS_IFD: 'GPS IFD'}


def _resolve_tag(tag: Any) -> list[tuple[int, int]]:
    """``(ifd, tag_id)`` pairs to look up for ``tag`` (a name, ``0x...``, a decimal string or an int).

    Names from the main tag table are looked up in IFD0 and the Exif IFD, GPS names in the
    GPS IFD; a number in all three.

    :raises ValueError: unknown name or invalid number
    """
    if isinstance(tag, bool) or not isinstance(tag, (str, int)):
        raise ValueError(f'tag must be a name or an integer, got {tag!r}')
    if isinstance(tag, str):
        text = tag.strip()
        if re.fullmatch(r'0[xX][0-9a-fA-F]+', text):
            tag = int(text, 16)
        elif text.isdigit():
            tag = int(text)
        elif text in _MAIN_NAMES:
            return [(ifd, t) for ifd in (0, EXIF_IFD) for t in _MAIN_NAMES[text]]
        elif text in _GPS_NAMES:
            return [(GPS_IFD, t) for t in _GPS_NAMES[text]]
        else:
            raise ValueError(f'unknown EXIF tag name {tag!r}')
    if not 0 <= tag <= 0xFFFF:
        raise ValueError(f'EXIF tag number out of range: {tag}')
    return [(ifd, tag) for ifd in (0, EXIF_IFD, GPS_IFD)]


def _format_number(value: Any) -> str:
    """``72`` for 72/1 and 72.0, ``2.8`` for 28/10, ``nan`` for x/0."""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return repr(number)


def _decode_bytes(tag_id: int, value: bytes) -> str:
    """Byte values: UTF-16 text tags, the user comment's charset prefix, printable text, else hex."""
    if tag_id in UTF16_TAGS:
        try:
            return value.decode('utf-16-le').rstrip('\x00')
        except UnicodeDecodeError:
            return value.hex()
    if tag_id == USER_COMMENT and value[:8] in _USER_COMMENT_CODES:
        try:
            return value[8:].decode(_USER_COMMENT_CODES[value[:8]]).rstrip('\x00').rstrip()
        except UnicodeDecodeError:
            return value.hex()
    try:
        text = value.rstrip(b'\x00').decode('utf-8')
    except UnicodeDecodeError:
        return value.hex()
    return text if text.isprintable() else value.hex()


def format_exif_value(value: Any, tag_id: int = -1) -> str:
    """Text form of an EXIF value used for comparison (see the docstrings for the rules)."""
    if isinstance(value, (bytes, bytearray)):
        return _decode_bytes(tag_id, bytes(value))
    if isinstance(value, str):
        return value.rstrip('\x00')
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (tuple, list)):
        return ', '.join(format_exif_value(v, tag_id) for v in value)
    try:
        return _format_number(value)  # IFDRational, float, Fraction
    except (TypeError, ValueError, ZeroDivisionError):
        return str(value)


def _expected_exif(expected: Any) -> Any:
    """Numbers and lists in YAML are formatted like EXIF values; text and tags are kept."""
    if isinstance(expected, (int, float, list, tuple)) and not isinstance(expected, bool):
        return format_exif_value(expected)
    return expected


def _load_exif(resolved: tuple[str, str], dst: str) -> tuple[dict[int, dict[int, Any]] | None, TestResult | None]:
    """IFD0, Exif IFD and GPS IFD of ``dst`` as ``{ifd: {tag_id: value}}``."""
    path, error = _image_path(resolved, dst)
    if error is not None:
        return None, error
    try:
        # Pillow drops corrupt EXIF with a warning (or silently), which would read as "no tag"
        with warnings.catch_warnings(record=True) as caught, Image.open(path) as img:
            warnings.simplefilter('always')
            exif = img.getexif()
            ifds = {0: dict(exif), EXIF_IFD: dict(exif.get_ifd(EXIF_IFD)), GPS_IFD: dict(exif.get_ifd(GPS_IFD))}
            embedded = img.info.get('exif') or b''
    except PILLOW_ERRORS as e:
        return None, TestResult.execution_error(e, f'Cannot read image or EXIF data of {path}')
    corrupt = [str(w.message).strip() for w in caught if 'corrupt exif' in str(w.message).lower()]
    if corrupt:
        return None, TestResult.error([f'corrupt EXIF data in {path}: {corrupt[0]}'])
    if len(embedded) > 14 and not ifds[0]:  # an EXIF block (header + TIFF header) that parsed to nothing
        return None, TestResult.error([f'EXIF data in {path} ({len(embedded)} bytes) cannot be parsed'])
    return ifds, None


def _exif_values(
    resolved: tuple[str, str], dst: str, tag: Any
) -> tuple[list[tuple[str, str]] | None, TestResult | None]:
    """``(location, formatted value)`` for every occurrence of ``tag``; or an error result."""
    try:
        lookups = _resolve_tag(tag)
    except ValueError as e:
        return None, TestResult.error([str(e)])
    ifds, error = _load_exif(resolved, dst)
    if error is not None:
        return None, error
    found = []
    for ifd, tag_id in lookups:
        if tag_id in ifds[ifd]:
            location = f'{_IFD_LABELS[ifd]} tag 0x{tag_id:04x}'
            found.append((location, format_exif_value(ifds[ifd][tag_id], tag_id)))
    return found, None


# =============================================================================
# Testfunctions: PNG text
# =============================================================================


@testfunction(
    name='png_text_matches',
    description='tests if a PNG text chunk (tEXt/zTXt/iTXt) with a keyword exists or matches an expected value',
    category=HostModeCategory.FILE_CONTENT,
)
def png_text_matches(
    ctx,
    dst: str,
    keyword: str,
    expected_value: str | int | float | bool | None = None,
    regex_match: bool = False,
    wildcard_mode: str = 'any',
):
    """Pass when the PNG ``dst`` has a text chunk with ``keyword`` (whose text matches ``expected_value``).

    Use for: metadata an application embeds in saved images (software, source, comment).
    With several chunks for ``keyword``, one match is enough (``wildcard_mode: all``: every
    chunk must match). For "absent" use
    image.png_text_count with ``expected_count: 0``.

    Args:
        dst: Guest path to the PNG file; a glob must match exactly one path. A missing file,
            a bad signature, a truncated chunk, any chunk CRC mismatch, a malformed or
            undecompressable text chunk, or a missing IEND is an error.
        keyword: Chunk keyword, compared exactly (case-sensitive). All chunks up to IEND are read,
            also those after the image data. tEXt is Latin-1, zTXt zlib + Latin-1, iTXt UTF-8
            (compressed or not; language tag and translated keyword are ignored).
        expected_value: ``None`` (default): the keyword exists. Otherwise compared with the
            text; a YAML number/boolean is compared as its text, a ``!re``/``!timestamp`` tag
            or ``{{placeholder}}`` is matched by type.
        regex_match: Search ``expected_value`` as a Python regex (``re.search``, unanchored).
            An invalid regex is an error.
        wildcard_mode: With several chunks for ``keyword``, ``any`` (default): one must
            match; ``all``: every one must match. Ignored without ``expected_value``. Other
            values are an error.

    Example:
        function: image.png_text_matches
        parameter:
          dst: /home/user/Pictures/photo.png
          keyword: Comment
          expected_value: exported by app
    """
    if wildcard_mode not in WILDCARD_MODES:
        return TestResult.error([f"Invalid wildcard_mode: {wildcard_mode}. Must be 'any' or 'all'"])
    texts, error = _load_png_text(ctx.resolve_globfilepath(dst), dst)
    if error is not None:
        return error
    found = [t for t in texts if t.keyword == keyword]
    if not found:
        keys = sorted({t.keyword for t in texts})
        return TestResult.failed(
            [f'no text chunk with keyword "{keyword}"', f'keywords: {", ".join(keys) or "(none)"}']
        )
    if expected_value is None:
        return TestResult.success([f'{len(found)} text chunk(s) with keyword "{keyword}": {found[0].text}'])
    expected = _expected_text(expected_value)
    try:
        results = [(t, *compare_value(ctx, t.text, expected, regex_match)) for t in found]
    except re.error as e:
        return TestResult.error([str(e)])
    if len(results) == 1:
        _, ok, message = results[0]
        return TestResult.success([message]) if ok else TestResult.failed([message])
    matching = [t for t, ok, _ in results if ok]
    head = f'keyword "{keyword}": {len(matching)}/{len(results)} text chunks match (mode: {wildcard_mode})'
    passed = bool(matching) if wildcard_mode == 'any' else len(matching) == len(results)
    if passed:
        return TestResult.success([head, f'matching {matching[0].chunk} text: {matching[0].text}'])
    shown = ', '.join([f'{t.chunk}: {t.text}' for t, ok, _ in results if not ok][:5])
    return TestResult.failed([head, f'expected: "{expected_value}"', f'non-matching texts: {shown}'])


@testfunction(
    name='png_text_count',
    description='tests the number of PNG text chunks with a keyword (optionally with a matching text)',
    category=HostModeCategory.FILE_CONTENT,
)
def png_text_count(
    ctx,
    dst: str,
    keyword: str,
    expected_count: int,
    expected_value: str | int | float | bool | None = None,
    regex_match: bool = False,
    comparison_type: str = 'equals',
):
    """Pass when the number of text chunks with ``keyword`` (whose text matches ``expected_value``,
    if given) satisfies ``comparison_type`` against ``expected_count``.

    Use for: duplicate keywords and absence: ``expected_count: 0`` asserts no such chunk (or
    none with that text).

    Args:
        dst: Guest path to the PNG file; a glob must match exactly one path. A missing file,
            a bad signature, a truncated chunk, any chunk CRC mismatch, a malformed or
            undecompressable text chunk, or a missing IEND is an error.
        keyword: Chunk keyword, compared exactly; tEXt, zTXt and iTXt chunks are counted
            together, also those after the image data.
        expected_count: Required non-negative integer to compare against; anything else is
            an error.
        expected_value: Count only chunks whose text equals/matches this (same rules as
            image.png_text_matches); ``None`` (default) counts every chunk with ``keyword``.
        regex_match: Search ``expected_value`` as a Python regex (``re.search``, unanchored).
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``; other values are an error.

    Example:
        function: image.png_text_count
        parameter:
          dst: /home/user/Pictures/photo.png
          keyword: Comment
          expected_count: 0
    """
    resolved = ctx.resolve_globfilepath(dst)
    problems = count_parameter_errors(expected_count, comparison_type)
    if problems:
        return TestResult.error(problems)
    texts, error = _load_png_text(resolved, dst)
    if error is not None:
        return error
    found = [t for t in texts if t.keyword == keyword]
    if expected_value is None:
        actual = len(found)
        what = f'{actual} text chunk(s) with keyword "{keyword}"'
    else:
        expected = _expected_text(expected_value)
        try:
            actual = sum(1 for t in found if compare_value(ctx, t.text, expected, regex_match)[0])
        except re.error as e:
            return TestResult.error([str(e)])
        what = f'{actual} text chunk(s) with keyword "{keyword}" match "{expected_value}"'
    ok, message = compare_count(actual, expected_count, comparison_type)
    details = [what, message]
    return TestResult.success(details) if ok else TestResult.failed(details)


# =============================================================================
# Testfunctions: EXIF
# =============================================================================


@testfunction(
    name='exif_value_matches',
    description='tests if an EXIF tag (IFD0, Exif or GPS IFD) equals or matches an expected value',
    category=HostModeCategory.FILE_CONTENT,
)
def exif_value_matches(
    ctx,
    dst: str,
    tag: str | int,
    expected_value: str | int | float | bool,
    regex_match: bool = False,
    wildcard_mode: str = 'any',
):
    """Pass when EXIF tag ``tag`` of the image ``dst`` equals (or matches) ``expected_value``.

    Use for: camera, time and location metadata written into photos (JPEG, PNG eXIf, TIFF,
    WebP). A tag present in several IFDs passes if one occurrence matches (``wildcard_mode:
    all``: every occurrence must match); a missing tag fails. For "absent" use image.exif_value_count with ``expected_count: 0``.

    Args:
        dst: Guest path to the image; a glob must match exactly one path. A missing file, a
            file that is not an image or has corrupt EXIF data is an error.
        tag: Tag name as in Pillow's tables (``Make``, ``DateTimeOriginal``, ``GPSLatitude``)
            or a number (``0x9003``, ``36867``). Main-table names are looked up in IFD0 and the
            Exif IFD, GPS names in the GPS IFD, numbers in all three. An unknown name is an
            error.
        expected_value: Compared with the value's text form: text as stored (trailing NULs
            removed); integers in decimal; rationals and floats as decimals (``72``, ``2.8``,
            ``0.004``; ``nan`` for x/0); sequences joined with ``", "`` (GPS ``51, 30, 12.5``);
            bytes as text when printable UTF-8, else lowercase hex; the user comment without
            its 8-byte charset prefix; the UTF-16 title/comment tags (0x9C9B-0x9C9F) decoded.
            A YAML number is formatted the same way (write a sequence as text, ``51, 30, 12.5``);
            a ``!re``/``!timestamp`` tag or
            ``{{placeholder}}`` is matched by type.
        regex_match: Search ``expected_value`` as a Python regex (``re.search``, unanchored).
            An invalid regex is an error.
        wildcard_mode: With the tag in several IFDs, ``any`` (default): one occurrence must
            match; ``all``: every one must match. Other values are an error.

    Example:
        function: image.exif_value_matches
        parameter:
          dst: /home/user/Pictures/photo.jpg
          tag: DateTimeOriginal
          expected_value: "2024:05:01 12:00:00"
    """
    if wildcard_mode not in WILDCARD_MODES:
        return TestResult.error([f"Invalid wildcard_mode: {wildcard_mode}. Must be 'any' or 'all'"])
    found, error = _exif_values(ctx.resolve_globfilepath(dst), dst, tag)
    if error is not None:
        return error
    if not found:
        return TestResult.failed([f'EXIF tag {tag} not present'])
    expected = _expected_exif(expected_value)
    try:
        results = [(loc, value, *compare_value(ctx, value, expected, regex_match)) for loc, value in found]
    except re.error as e:
        return TestResult.error([str(e)])
    matching = [(loc, value) for loc, value, ok, _ in results if ok]
    if len(results) == 1:
        loc, _, ok, message = results[0]
        details = [f'EXIF tag {tag} ({loc}): {message}']
        return TestResult.success(details) if ok else TestResult.failed(details)
    head = f'EXIF tag {tag}: {len(matching)}/{len(results)} occurrences match (mode: {wildcard_mode})'
    passed = bool(matching) if wildcard_mode == 'any' else len(matching) == len(results)
    if passed:
        return TestResult.success([head, f'{matching[0][0]}: {matching[0][1]}'])
    shown = ', '.join([f'{loc}: {value}' for loc, value, ok, _ in results if not ok][:5])
    return TestResult.failed([head, f'expected: "{expected_value}"', f'non-matching values: {shown}'])


@testfunction(
    name='exif_value_count',
    description='tests the number of occurrences of an EXIF tag (optionally with a matching value)',
    category=HostModeCategory.FILE_CONTENT,
)
def exif_value_count(
    ctx,
    dst: str,
    tag: str | int,
    expected_count: int,
    expected_value: str | int | float | bool | None = None,
    regex_match: bool = False,
    comparison_type: str = 'equals',
):
    """Pass when the number of occurrences of EXIF tag ``tag`` (whose value matches ``expected_value``,
    if given) satisfies ``comparison_type`` against ``expected_count``.

    Use for: absence: ``expected_count: 0`` asserts the tag was not written (or stripped, e.g.
    location data removed on export).

    Args:
        dst: Guest path to the image; a glob must match exactly one path. A missing file, a
            file that is not an image or has corrupt EXIF data is an error.
        tag: Tag name (``Make``, ``GPSLatitude``) or number (``0x010f``); names are looked up
            in their IFD (IFD0 + Exif IFD, or GPS IFD), numbers in all three, and each IFD that
            has the tag counts once. An unknown name is an error.
        expected_count: Required non-negative integer to compare against; anything else is
            an error.
        expected_value: Count only occurrences whose value text equals/matches this (same
            formatting as image.exif_value_matches); ``None`` (default) counts every occurrence.
        regex_match: Search ``expected_value`` as a Python regex (``re.search``, unanchored).
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``; other values are an error.

    Example:
        function: image.exif_value_count
        parameter:
          dst: /home/user/Pictures/photo.jpg
          tag: GPSLatitude
          expected_count: 0
    """
    resolved = ctx.resolve_globfilepath(dst)
    problems = count_parameter_errors(expected_count, comparison_type)
    if problems:
        return TestResult.error(problems)
    found, error = _exif_values(resolved, dst, tag)
    if error is not None:
        return error
    if expected_value is None:
        actual = len(found)
        what = f'{actual} occurrence(s) of EXIF tag {tag}'
    else:
        expected = _expected_exif(expected_value)
        try:
            actual = sum(1 for _, value in found if compare_value(ctx, value, expected, regex_match)[0])
        except re.error as e:
            return TestResult.error([str(e)])
        what = f'{actual} occurrence(s) of EXIF tag {tag} match "{expected_value}"'
    ok, message = compare_count(actual, expected_count, comparison_type)
    details = [what, message]
    return TestResult.success(details) if ok else TestResult.failed(details)


# =============================================================================
# Testfunctions: dimensions
# =============================================================================


def _dimension_errors(width: Any, height: Any) -> list[str]:
    if width is None and height is None:
        return ['give width, height or both']
    errors = []
    for name, value in (('width', width), ('height', height)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
            errors.append(f'{name} must be a positive integer, got {value!r}')
    return errors


@testfunction(
    name='dimensions_match',
    description='tests if an image has the expected width and/or height in pixels',
    category=HostModeCategory.FILE_CONTENT,
)
def dimensions_match(ctx, dst: str, width: int = None, height: int = None):
    """Pass when the image ``dst`` is ``width`` x ``height`` pixels (only the given ones are checked).

    Use for: checking an exported, resized or cropped image, or a generated thumbnail.

    Args:
        dst: Guest path to the image (any format Pillow reads); a glob must match exactly one
            path. A missing file or a file that is not an image is an error.
        width: Expected width in pixels (positive integer).
        height: Expected height in pixels (positive integer). Give at least one of the two;
            neither, or a non-positive / non-integer value, is an error.

    Example:
        function: image.dimensions_match
        parameter:
          dst: /home/user/Pictures/thumbnail.png
          width: 256
          height: 256
    """
    resolved = ctx.resolve_globfilepath(dst)
    problems = _dimension_errors(width, height)
    if problems:
        return TestResult.error(problems)
    path, error = _image_path(resolved, dst)
    if error is not None:
        return error
    try:
        with Image.open(path) as img:
            actual_width, actual_height = img.size
    except PILLOW_ERRORS as e:
        return TestResult.execution_error(e, f'Cannot read image {path}')
    size = f'image is {actual_width}x{actual_height}'
    misses = [
        f'{name} {actual} != expected {expected}'
        for name, actual, expected in (('width', actual_width, width), ('height', actual_height, height))
        if expected is not None and actual != expected
    ]
    if misses:
        return TestResult.failed([size, *misses])
    return TestResult.success([size])
