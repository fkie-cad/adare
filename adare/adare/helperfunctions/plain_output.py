"""Plain (tab-separated) rendering of structured CLI output.

``plain`` is the format a command prints when stdout is not a terminal and no
format was requested, so the rules favour ``cut``/``awk``/``while read``:

* a list of records is a TSV table: one header row, then one row per record;
* a single record is ``key<TAB>value`` lines; a nested list of records inside it
  follows as its own table, introduced by a ``# <key>`` line;
* flat sub-records become dotted columns (``vm.id``, ``disk.present``);
* values are never truncated, carry no colour, box-drawing or emoji, and tabs /
  newlines inside a value are flattened to spaces so a row stays one line;
* booleans are ``true``/``false``, ``None`` is empty, scalar lists are joined
  with ``,`` and anything still nested is compact JSON.

The input is already-prepared data (see ``StructuredOutputFormatter.prepare_data``):
dicts, lists and JSON scalars only.
"""

import json
from typing import Any


def _cell(value: Any) -> str:
    """Render one value as a single TSV-safe cell."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (list, tuple)):
        if all(not isinstance(item, (dict, list, tuple)) for item in value):
            return ','.join(_cell(item) for item in value)
        return _flatten(json.dumps(value, ensure_ascii=False, separators=(',', ':')))
    if isinstance(value, dict):
        return _flatten(json.dumps(value, ensure_ascii=False, separators=(',', ':')))
    return _flatten(str(value))


def _flatten(text: str) -> str:
    """Keep a cell on one line and inside its column."""
    return text.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')


def _is_record_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, dict) for item in value)


def _is_scalar_or_scalar_list(value: Any) -> bool:
    if isinstance(value, (list, tuple)):
        return all(not isinstance(item, (dict, list, tuple)) for item in value)
    return not isinstance(value, dict)


def _is_flat_record(value: Any) -> bool:
    """A non-empty dict whose values are scalars or scalar lists (dotted-key material)."""
    return isinstance(value, dict) and bool(value) and all(_is_scalar_or_scalar_list(v) for v in value.values())


def _is_record_map(value: Any) -> bool:
    """A dict of records keyed by name (e.g. ``{"test_a": {...}, "test_b": {...}}``)."""
    return isinstance(value, dict) and bool(value) and all(isinstance(item, dict) for item in value.values())


def _flatten_record(record: dict[str, Any]) -> dict[str, Any]:
    """Lift flat sub-records into dotted columns: ``{"vm": {"id": 1}}`` -> ``vm.id``."""
    flat: dict[str, Any] = {}
    for key, value in record.items():
        if _is_flat_record(value):
            for sub_key, sub_value in value.items():
                flat[f'{key}.{sub_key}'] = sub_value
        else:
            flat[key] = value
    return flat


def render_table(records: list[dict[str, Any]]) -> str:
    """Render a list of records as TSV: a header row (union of keys, first-seen order)."""
    if not records:
        return ''
    records = [_flatten_record(record) for record in records]
    columns: list[str] = []
    for record in records:
        for key in record:
            if key not in columns:
                columns.append(key)
    lines = ['\t'.join(columns)]
    lines.extend('\t'.join(_cell(record.get(column)) for column in columns) for record in records)
    return '\n'.join(lines)


def _render_record(record: dict[str, Any]) -> str:
    """Render one record: scalar fields as key/value lines, nested record lists as tables."""
    lines: list[str] = []
    tables: list[tuple[str, list[dict[str, Any]]]] = []
    for key, value in record.items():
        if _is_record_list(value):
            tables.append((key, value))
        elif _is_record_map(value):
            tables.append((key, list(value.values())))
        elif _is_flat_record(value):
            # A small flat sub-record (e.g. a "vm" section) reads best dotted.
            lines.extend(f'{key}.{sub_key}\t{_cell(sub_value)}' for sub_key, sub_value in value.items())
        else:
            lines.append(f'{key}\t{_cell(value)}')
    blocks = ['\n'.join(lines)] if lines else []
    blocks.extend(f'# {key}\n{render_table(rows)}' for key, rows in tables)
    return '\n\n'.join(blocks)


def render_plain(data: Any) -> str:
    """Render prepared structured data as plain text (see module docstring)."""
    if data is None:
        return ''
    if isinstance(data, list):
        if not data:
            return ''
        if _is_record_list(data):
            return render_table(data)
        return '\n'.join(_cell(item) for item in data)
    if isinstance(data, dict):
        # The common list-command envelope: {"environments": [...]} -> just the table.
        if len(data) == 1:
            (only_value,) = data.values()
            if isinstance(only_value, list):
                return render_plain(only_value)
        return _render_record(data)
    return _cell(data)
