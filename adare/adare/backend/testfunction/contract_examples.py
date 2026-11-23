"""Run the examples of testfunction contracts offline, against files built from their spec.

An example's ``files:`` maps guest paths to a small spec of the file's content; the files are
written under a temporary root, the guest paths in the parameters are rewritten to it, and the
function runs as in ``adare test dry-run``. The outcome must be the example's ``expect``. This
keeps every documented example (and every documented boundary: "an absent key fails", "an
offset outside the file is an error") true.

File specs (one key each):

``text: str`` (+ ``encoding``) · ``hex: str`` · ``base64: str`` · ``json: any`` ·
``concat: [spec, ...]`` (also ``u8``/``u16le``/.../``i64be``/``f32le``/``f64be``: number) ·
``sqlite: [sql, ...]`` · ``zip``/``tar``/``tar.gz``: ``{member: spec}`` · ``gzip``/``bzip2``/``xz``: spec ·
``xlsx: {sheet: [[cell, ...], ...]}`` · ``plist: any`` / ``plist_binary: any`` ·
``png: {size: [w, h], text: {key: value}}`` · ``jpeg: {size: [w, h], exif: {tag: value}}`` ·
``dir: true`` (an empty folder) · ``fixture: <path under adare/tests/unit/testfunctions/fixtures>``.
"""

import base64
import bz2
import gzip
import io
import json
import lzma
import plistlib
import sqlite3
import struct
import tarfile
import zipfile
from pathlib import Path, PureWindowsPath
from typing import Any

from adare.backend.testfunction.catalog import CatalogEntry
from adare.backend.testfunction.contract import Example

FIXTURES_DIR = Path(__file__).resolve().parents[3] / 'tests' / 'unit' / 'testfunctions' / 'fixtures'
_STRUCT = {
    'u8': 'B',
    'i8': 'b',
    **{
        f'{s}{n}{e}': f'{"<" if e == "le" else ">"}{c}'
        for n, (u, i) in {16: ('H', 'h'), 32: ('I', 'i'), 64: ('Q', 'q')}.items()
        for e in ('le', 'be')
        for s, c in (('u', u), ('i', i))
    },
    **{f'f{n}{e}': f'{"<" if e == "le" else ">"}{c}' for n, c in ((32, 'f'), (64, 'd')) for e in ('le', 'be')},
}
OFFLINE_CATEGORIES = ('FILE_BASED', 'FILE_CONTENT')


class FixtureError(ValueError):
    """A ``files:`` spec that cannot be built."""


# ---------------------------------------------------------------------------
# Building files
# ---------------------------------------------------------------------------


def _one_key(spec: Any) -> tuple[str, Any]:
    if not isinstance(spec, dict) or len([k for k in spec if k != 'encoding']) != 1:
        raise FixtureError(f'a file spec has exactly one kind key, got {spec!r}')
    key = next(k for k in spec if k != 'encoding')
    return key, spec[key]


def _compressed(kind: str, value: Any) -> bytes:
    data = build_bytes(value)
    if kind == 'gzip':
        return gzip.compress(data, mtime=0)
    return bz2.compress(data) if kind == 'bzip2' else lzma.compress(data)


def _tar_spec(kind: str, value: Any) -> bytes:
    data = _tar(value)
    return gzip.compress(data, mtime=0) if kind == 'tar.gz' else data


def _plist(kind: str, value: Any) -> bytes:
    return plistlib.dumps(value, fmt=plistlib.FMT_BINARY if kind == 'plist_binary' else plistlib.FMT_XML)


_BUILDERS: dict[str, Any] = {
    'hex': lambda _k, v: bytes.fromhex(''.join(str(v).split())),
    'base64': lambda _k, v: base64.b64decode(v),
    'json': lambda _k, v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
    'concat': lambda _k, v: b''.join(build_bytes(part) for part in v),
    'gzip': _compressed,
    'bzip2': _compressed,
    'xz': _compressed,
    'zip': lambda _k, v: _zip(v),
    'tar': _tar_spec,
    'tar.gz': _tar_spec,
    'plist': _plist,
    'plist_binary': _plist,
    'xlsx': lambda _k, v: _xlsx(v),
    'png': lambda k, v: _image(k, v),
    'jpeg': lambda k, v: _image(k, v),
    'sqlite': lambda _k, v: _sqlite_bytes(v),
    'fixture': lambda _k, v: (FIXTURES_DIR / str(v)).read_bytes(),
}


def build_bytes(spec: Any) -> bytes:
    """The content of a file spec (``dir`` needs a path: see :func:`write_file`)."""
    kind, value = _one_key(spec)
    if kind == 'text':
        return str(value).encode(spec.get('encoding', 'utf-8'))
    if kind in _STRUCT:
        return struct.pack(_STRUCT[kind], value)
    if kind not in _BUILDERS:
        raise FixtureError(f'unknown file spec kind "{kind}"')
    return bytes(_BUILDERS[kind](kind, value))


def _members(value: Any) -> dict:
    if not isinstance(value, dict):
        raise FixtureError('an archive spec maps member paths to file specs')
    return value


def _zip(value: Any) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, member in _members(value).items():
            archive.writestr(name, build_bytes(member))
    return out.getvalue()


def _tar(value: Any) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w') as archive:
        for name, member in _members(value).items():
            data = build_bytes(member)
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return out.getvalue()


def _xlsx(sheets: Any) -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for title, rows in _members(sheets).items():
        sheet = workbook.create_sheet(title)
        for row in rows or []:
            sheet.append(row)
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def _image(kind: str, value: Any) -> bytes:
    from PIL import Image, PngImagePlugin

    value = value or {}
    width, height = value.get('size', [4, 4])
    image = Image.new('RGB', (width, height), (200, 30, 30))
    out = io.BytesIO()
    if kind == 'png':
        info = PngImagePlugin.PngInfo()
        for key, text in (value.get('text') or {}).items():
            info.add_text(str(key), str(text))
        image.save(out, 'PNG', pnginfo=info)
    else:
        exif = Image.Exif()
        for tag, tag_value in (value.get('exif') or {}).items():
            exif[_exif_tag(tag)] = tag_value
        image.save(out, 'JPEG', exif=exif)
    return out.getvalue()


def _exif_tag(tag: Any) -> int:
    if isinstance(tag, int):
        return tag
    from PIL import ExifTags

    by_name = {name: number for number, name in ExifTags.TAGS.items()}
    if tag not in by_name:
        raise FixtureError(f'unknown EXIF tag "{tag}"')
    return by_name[tag]


def _sqlite_bytes(statements: Any) -> bytes:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'db.sqlite'
        _write_sqlite(path, statements)
        return path.read_bytes()


def _write_sqlite(path: Path, statements: Any) -> None:
    if isinstance(statements, str):
        statements = [statements]
    connection = sqlite3.connect(path)
    try:
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()


def write_file(path: Path, spec: Any) -> None:
    kind, value = _one_key(spec)
    if kind == 'dir':
        path.mkdir(parents=True, exist_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == 'sqlite':
        _write_sqlite(path, value)
    else:
        path.write_bytes(build_bytes(spec))


# ---------------------------------------------------------------------------
# Guest paths -> local paths
# ---------------------------------------------------------------------------


def local_path(root: Path, guest_path: str) -> Path:
    """``/home/u/a.json`` -> ``<root>/home/u/a.json``; ``C:\\Users\\a.json`` -> ``<root>/C/Users/a.json``."""
    if len(guest_path) > 1 and guest_path[1] == ':':
        parts = PureWindowsPath(guest_path).parts
        return root.joinpath(parts[0][0], *parts[1:])
    return root.joinpath(*[p for p in guest_path.split('/') if p])


def _rewrite(value: Any, prefixes: list[tuple[str, str]]) -> Any:
    if isinstance(value, dict):
        return {k: _rewrite(v, prefixes) for k, v in value.items()}
    if isinstance(value, list):
        return [_rewrite(v, prefixes) for v in value]
    if isinstance(value, str):
        for guest, local in prefixes:
            if value.startswith(guest):
                rest = value[len(guest) :]
                archive, sep, member = rest.partition('!')
                return local + archive.replace('\\', '/') + sep + member
    return value


def rewrite_paths(parameter: dict, files: dict, root: Path) -> dict:
    """Point every parameter that starts with a guest folder of ``files`` into ``root``."""
    prefixes: dict[str, str] = {}
    for guest in files:
        sep = '\\' if '\\' in guest else '/'
        folder = guest.rsplit(sep, 1)[0] + sep
        prefixes[folder] = local_path(root, folder.rstrip(sep)).as_posix() + '/'
    ordered = sorted(prefixes.items(), key=lambda item: -len(item[0]))
    return {name: _rewrite(value, ordered) for name, value in parameter.items()}


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def offline_blocker(entry: CatalogEntry, example: Example) -> str:
    """Why the example cannot run offline (``''`` when it can)."""
    from adarelib.testset.yaml.customtags import YamlCustomTag

    if not example.run:
        return example.why_not_run
    if entry.category not in OFFLINE_CATEGORIES:
        return f'{entry.category} tests need a live guest or host'

    def needs_runtime(value: Any) -> bool:
        if isinstance(value, dict):
            return any(needs_runtime(v) for v in value.values())
        if isinstance(value, list):
            return any(needs_runtime(v) for v in value)
        return isinstance(value, YamlCustomTag) or (isinstance(value, str) and '{{' in value)

    if needs_runtime(example.parameter):
        return '!re / !timestamp tags and {{placeholders}} are resolved by a playbook run'
    return ''


def run_example(entry: CatalogEntry, example: Example, root: Path):
    """Build the files under ``root`` and run the function; returns the ``TestResult``."""
    from adarelib.helper.module import import_module_from_pyfile

    for guest, spec in example.files.items():
        write_file(local_path(root, guest), spec)
    parameter = rewrite_paths(dict(example.parameter), example.files, root)
    module = import_module_from_pyfile(Path(entry.path))
    function = next(
        (v for v in vars(module).values() if getattr(getattr(v, '_test_class', None), 'testname', None) == entry.name),
        None,
    )
    if function is None:
        raise FixtureError(f'{entry.dotnotation}: function not found in {entry.path}')
    test = function._test_class(name='example', parameter=function._parameter_class(**parameter))
    return test.test()


OUTCOME_STATUS = {'passed': 'SUCCESS', 'failed': 'FAILED', 'error': 'ERROR'}
