"""Regression test to enforce specific exception catching in hypervisor code.

Per CLAUDE.md: 'never catch generic exception (with except Exception) -
use more specific Exception that are expected instead'.

This test scans all Python files under hypervisor/qemu/ and asserts that
only intentionally marked exemptions use 'except Exception'.
"""
import pytest

pytestmark = pytest.mark.unit

import re
from pathlib import Path


def test_no_generic_exception_catching():
    """Regression test: ensure no bare 'except Exception' in hypervisor code."""
    qemu_dir = Path(__file__).parents[5] / 'adare' / 'hypervisor' / 'qemu'
    violations = []

    for py_file in sorted(qemu_dir.rglob('*.py')):
        content = py_file.read_text()
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            if re.search(r'except\s+Exception\b', line):
                # Check if it has the intentional marker
                # Look at this line and the next two lines for the marker
                start = max(0, i - 1)
                end = min(len(lines), i + 2)
                context = lines[start:end]
                if not any('# Intentional:' in ctx for ctx in context):
                    rel_path = py_file.relative_to(qemu_dir)
                    violations.append(f"{rel_path}:{i}: {line.strip()}")

    assert not violations, (
        "Found generic exception catching without '# Intentional:' marker:\n"
        + "\n".join(violations)
    )
