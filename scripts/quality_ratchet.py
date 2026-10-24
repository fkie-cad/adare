#!/usr/bin/env python3
"""Quality ratchet: legacy debt may shrink, never grow.

Three budgets are tracked in ``quality-baseline.json`` at the repo root:

- ``ruff``: violation count per rule code. A rule absent from the baseline must
  have zero violations; a listed rule may not exceed its count.
- ``mypy``: type-error count per error code over the host package (``MYPY_TARGET``).
  ``--no-mypy`` skips it (pre-commit); CI always runs it. ``MYPY_ZERO`` (adare.core,
  strict) has no budget: any error there fails.
- ``oversized_files``: Python files over ``MAX_LINES`` lines. A file not listed
  may not cross the limit; a listed file may not grow past its recorded size.

After paying debt down, run with ``--update`` to lower the baseline. Raising it
needs ``--allow-increase`` and should be a deliberate, reviewed decision.
"""

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

MAX_LINES = 1000
ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / 'quality-baseline.json'
MYPY_TARGET = 'adare/adare'
MYPY_ZERO = 'adare/adare/core/'
MYPY_ERROR = re.compile(r': error: .*\[([a-z0-9-]+)\]$')


def ruff_counts() -> dict[str, int]:
    proc = subprocess.run(
        [sys.executable, '-m', 'ruff', 'check', '.', '--output-format', 'json', '--exit-zero'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return dict(sorted(Counter(v['code'] for v in json.loads(proc.stdout)).items()))


def mypy_counts() -> tuple[dict[str, int], list[str]]:
    """Error counts per code, and the errors in ``MYPY_ZERO`` (which must have none)."""
    proc = subprocess.run(
        [sys.executable, '-m', 'mypy', MYPY_TARGET, '--no-error-summary', '--no-pretty'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,  # exits 1 whenever errors exist
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(f'mypy crashed:\n{proc.stderr or proc.stdout}')
    errors = [(line, m.group(1)) for line in proc.stdout.splitlines() if (m := MYPY_ERROR.search(line))]
    zero_violations = [line for line, _ in errors if line.replace('\\', '/').startswith(MYPY_ZERO)]
    return dict(sorted(Counter(code for _, code in errors).items())), zero_violations


def oversized_files() -> dict[str, int]:
    tracked = subprocess.run(
        ['git', 'ls-files', '-z', '--', '*.py'], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split('\0')
    sizes = {}
    for rel in filter(None, tracked):
        path = ROOT / rel
        if not path.is_file():  # deleted in the working tree but still in the index
            continue
        with path.open('rb') as fh:
            lines = sum(1 for _ in fh)
        if lines > MAX_LINES:
            sizes[rel] = lines
    return dict(sorted(sizes.items()))


def compare(kind: str, current: dict[str, int], allowed: dict[str, int], unit: str) -> tuple[list[str], list[str]]:
    regressions, improvements = [], []
    for key in sorted(current.keys() | allowed.keys()):
        now, budget = current.get(key, 0), allowed.get(key, 0)
        if now > budget:
            regressions.append(f'{kind}: {key} has {now} {unit} (budget {budget})')
        elif now < budget:
            improvements.append(f'{kind}: {key} {budget} -> {now} {unit}')
    return regressions, improvements


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--update', action='store_true', help='rewrite the baseline with current values')
    parser.add_argument('--allow-increase', action='store_true', help='let --update raise budgets')
    parser.add_argument('--no-mypy', action='store_true', help='skip the (slower) mypy budget')
    args = parser.parse_args()

    baseline = {'ruff': {}, 'mypy': {}, 'oversized_files': {}}
    if BASELINE.exists():
        baseline |= json.loads(BASELINE.read_text())
    mypy, zero_violations = (baseline['mypy'], []) if args.no_mypy else mypy_counts()
    current = {'ruff': ruff_counts(), 'mypy': mypy, 'oversized_files': oversized_files()}

    if zero_violations:
        print(f'mypy: {MYPY_ZERO} must stay at zero errors:', *zero_violations, sep='\n  ')
        return 1

    regressions, improvements = [], []
    for kind, key, unit in [
        ('ruff', 'ruff', 'violations'),
        ('mypy', 'mypy', 'errors'),
        (f'size>{MAX_LINES}', 'oversized_files', 'lines'),
    ]:
        reg, imp = compare(kind, current[key], baseline[key], unit)
        regressions += reg
        improvements += imp

    if args.update:
        if regressions and BASELINE.exists() and not args.allow_increase:
            print('Refusing to raise budgets without --allow-increase:', *regressions, sep='\n  ')
            return 1
        BASELINE.write_text(json.dumps(current, indent=2) + '\n')
        print(f'Baseline updated ({len(improvements)} improved, {len(regressions)} raised).')
        return 0

    if regressions:
        print('Quality ratchet FAILED — new debt introduced:', *regressions, sep='\n  ')
        print(
            '\nFix the new violations (`ruff check .` / `mypy adare/adare` show them). '
            'Files over the size limit must be split.'
        )
        return 1
    if improvements:
        print(
            'Debt went down — lock it in with `python scripts/quality_ratchet.py --update`:', *improvements, sep='\n  '
        )
    print('Quality ratchet OK.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
