"""The CLI never crashes on characters the console encoding (cp1252 on Windows) cannot represent."""

import io
import sys

import pytest

from adare import run

pytestmark = pytest.mark.unit


def test_unencodable_output_is_replaced_not_raised(monkeypatch):
    stdout = io.TextIOWrapper(io.BytesIO(), encoding='cp1252')
    stderr = io.TextIOWrapper(io.BytesIO(), encoding='cp1252')
    monkeypatch.setattr(sys, 'stdout', stdout)
    monkeypatch.setattr(sys, 'stderr', stderr)

    run._replace_unencodable_output()
    print('✓ migrated')
    print('✗ failed', file=sys.stderr)
    stdout.flush()
    stderr.flush()

    assert stdout.buffer.getvalue().startswith(b'? migrated')
    assert stderr.buffer.getvalue().startswith(b'? failed')


def test_streams_that_are_not_text_wrappers_are_left_alone(monkeypatch):
    stdout = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', stdout)

    run._replace_unencodable_output()
    print('✓')

    assert stdout.getvalue() == '✓\n'
