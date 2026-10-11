#!/usr/bin/env python3
"""Quality ratchet: legacy debt may shrink, never grow.

Two budgets are tracked in ``quality-baseline.json`` at the repo root:

- ``ruff``: violation count per rule code. A rule absent from the baseline must
  have zero violations; a listed rule may not exceed its count.
- ``oversized_files``: Python files over ``MAX_LINES`` lines. A file not listed
  may not cross the limit; a listed file may not grow past its recorded size.

After paying debt down, run with ``--update`` to lower the baseline. Raising it
needs ``--allow-increase`` and should be a deliberate, reviewed decision.
"""

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

MAX_LINES = 1000
ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / 'quality-baseline.json'


def ruff_counts() -> dict[str, int]:
    proc = subprocess.run(
        [sys.executable, '-m', 'ruff', 'check', '.', '--output-format', 'json', '--exit-zero'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return dict(sorted(Counter(v['code'] for v in json.loads(proc.stdout)).items()))


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
    args = parser.parse_args()

    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {'ruff': {}, 'oversized_files': {}}
    current = {'ruff': ruff_counts(), 'oversized_files': oversized_files()}

    ruff_reg, ruff_imp = compare('ruff', current['ruff'], baseline['ruff'], 'violations')
    size_reg, size_imp = compare(f'size>{MAX_LINES}', current['oversized_files'], baseline['oversized_files'], 'lines')
    regressions, improvements = ruff_reg + size_reg, ruff_imp + size_imp

    if args.update:
        if regressions and BASELINE.exists() and not args.allow_increase:
            print('Refusing to raise budgets without --allow-increase:', *regressions, sep='\n  ')
            return 1
        BASELINE.write_text(json.dumps(current, indent=2) + '\n')
        print(f'Baseline updated ({len(improvements)} improved, {len(regressions)} raised).')
        return 0

    if regressions:
        print('Quality ratchet FAILED — new debt introduced:', *regressions, sep='\n  ')
        print('\nFix the new violations (`ruff check .` shows them). Files over the size limit must be split.')
        return 1
    if improvements:
        print(
            'Debt went down — lock it in with `python scripts/quality_ratchet.py --update`:', *improvements, sep='\n  '
        )
    print('Quality ratchet OK.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
