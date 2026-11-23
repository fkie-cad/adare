#!/usr/bin/env python3
"""Check testfunction contracts: schema, consistency with the code, and every example.

    python scripts/check_contract.py binary            # one collection
    python scripts/check_contract.py binary json csv   # several
    python scripts/check_contract.py --all

Prints each problem and each example's outcome; exits 1 when anything is wrong. The unit
suite runs the same checks (adare/tests/unit/adare/backend/testfunction/test_contracts.py).
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from adare.backend.testfunction.catalog import PACKAGE_APPDATA, bundled_sources, load_catalog
from adare.backend.testfunction.contract_checks import collection_problems
from adare.backend.testfunction.contract_examples import OUTCOME_STATUS, offline_blocker, run_example


def check(collection: str, entries) -> int:
    from adarelib.constants import StatusEnum

    bad = 0
    print(f'== {collection}')
    for problem in collection_problems(PACKAGE_APPDATA / collection / f'{collection}.py', entries):
        print(f'  PROBLEM {problem}')
        bad += 1
    for entry in (e for e in entries if e.collection == collection):
        if entry.contract is None:
            print(f'  PROBLEM {entry.dotnotation}: no contract')
            bad += 1
            continue
        for example in entry.contract.examples:
            label = f'{entry.dotnotation}: {example.title}'
            blocker = offline_blocker(entry, example)
            if blocker:
                print(f'  skip    {label} ({blocker})')
                continue
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    result = run_example(entry, example, Path(tmp))
                except (ValueError, TypeError, OSError, KeyError) as e:
                    print(f'  BROKEN  {label}: {type(e).__name__}: {e}')
                    bad += 1
                    continue
            status = StatusEnum(result.status).name
            if status == OUTCOME_STATUS[example.expect]:
                print(f'  ok      {label} -> {status}')
            else:
                print(f'  WRONG   {label}: expected {example.expect}, got {status}: {result.details}')
                bad += 1
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('collections', nargs='*')
    parser.add_argument('--all', action='store_true')
    args = parser.parse_args()
    entries = load_catalog(bundled_sources())
    collections = sorted({e.collection for e in entries}) if args.all else args.collections
    if not collections:
        parser.error('name collections or pass --all')
    bad = sum(check(c, entries) for c in collections)
    print(f'{bad} problem(s)')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
