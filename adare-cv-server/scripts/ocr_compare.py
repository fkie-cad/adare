"""Offline A/B of two OCR profiles over a project's recorded runs.

For each sampled experiment, OCR the screenshots its runs recorded
(``run/<exp>/<ts>/reporting/screenshots/*.png``) with both profiles and replay the
text queries those runs issued (``logs/mcp_gui.log``: "Starting text search for:
'<text>' (mode: <mode>)", or the client's ``logs/adare.log``) with each profile's
matching rules. A query/frame pair is
*relevant* when either profile finds the text; it *agrees* when both find it the
same number of times at the same places (within --tolerance px). Which query ran on
which frame is not logged, so every query of an experiment is tried on every
sampled frame of it - a superset of what the runs did.

    uv run --no-sync python adare-cv-server/scripts/ocr_compare.py \\
        ~/Documents/Projects/SoftwareTestsToArtifactResearch/adare \\
        --experiments 100 --frames 3 --out ocr_compare.json

Detections are cached per (frame sha256, profile) under --cache-dir, so a rerun or
a larger sample only OCRs new frames. PaddleOCR needs the cv-server `paddle` extra
and takes ~11 s per frame on CPU.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

from adare_cv_server import ocr_engines
from adare_cv_server.ocr_processing import TextDetector, decode_screenshot

QUERY_RE = re.compile(r"Starting text search for: '(.*)' \(mode: (\w+)\)")
# Client side (adare.log), for runs whose cv-server log lacks the queries; no mode there.
CLIENT_QUERY_RE = re.compile(r"(?:Found \d+ matches for text '(.*)':|Text '(.*)' not found via MCP)")
REGEX_HINT_RE = re.compile(r"[\\^$\[\](){}|*+?]")


def _profile(spec: str) -> ocr_engines.OcrEngine:
    engine, _, lang = spec.partition(':')
    return ocr_engines.build_engine(engine, lang or 'latin')


def _runs_by_experiment(project: Path) -> dict[str, list[Path]]:
    runs: dict[str, list[Path]] = defaultdict(list)
    for exp_dir in (project / 'run').iterdir():
        if not exp_dir.is_dir():
            continue
        for run in exp_dir.iterdir():
            if (run / 'reporting' / 'screenshots').is_dir() and (run / 'logs').is_dir():
                runs[exp_dir.name].append(run)
    return runs


def _queries(runs: list[Path]) -> list[tuple[str, str]]:
    """Text queries the runs issued: from the cv-server log, else from the client log
    (where the match mode is not logged: regex syntax means regex, else substring)."""
    found: set[tuple[str, str]] = set()
    for run in runs:
        server_log = run / 'logs' / 'mcp_gui.log'
        if server_log.is_file():
            text = server_log.read_text(errors='replace')
            found.update((m.group(1), m.group(2)) for m in QUERY_RE.finditer(text))
        client_log = run / 'logs' / 'adare.log'
        if client_log.is_file():
            for m in CLIENT_QUERY_RE.finditer(client_log.read_text(errors='replace')):
                query = m.group(1) if m.group(1) is not None else m.group(2)
                mode = 'regex' if REGEX_HINT_RE.search(query) else 'substring'
                found.add((query, mode))
    return sorted(found)


def _sample(project: Path, n_experiments: int, n_frames: int) -> list[dict]:
    """The most recently run experiments that issued text queries, with up to n_frames unique frames each."""
    picked = []
    runs = _runs_by_experiment(project)
    order = sorted(runs, key=lambda e: max(r.stat().st_mtime for r in runs[e]), reverse=True)
    for exp in order:
        queries = _queries(runs[exp])
        if not queries:
            continue
        frames, seen = [], set()
        for run in sorted(runs[exp], key=lambda r: r.stat().st_mtime, reverse=True):
            for png in sorted((run / 'reporting' / 'screenshots').glob('*.png')):
                digest = hashlib.sha256(png.read_bytes()).hexdigest()
                if digest not in seen:
                    seen.add(digest)
                    frames.append((png, digest))
        if not frames:
            continue
        # Spread over the experiment's steps rather than taking the first few.
        step = max(1, len(frames) // n_frames)
        picked.append({'experiment': exp, 'queries': queries, 'frames': frames[::step][:n_frames]})
        if len(picked) >= n_experiments:
            break
    return picked


def _detect(engine, png: Path, digest: str, cache_dir: Path) -> list:
    cache = cache_dir / f'{digest}.{engine.profile}.json'
    if cache.exists():
        return json.loads(cache.read_text())
    dets = engine.detect(decode_screenshot(png.read_bytes()))
    dets = [[box, [text, float(score)]] for box, (text, score) in dets]
    cache.write_text(json.dumps(dets))
    return dets


def _hits(engine, dets: list, text: str, mode: str) -> list[tuple[float, float]]:
    out = []
    for box, (line, _score) in dets:
        candidates = TextDetector._match_candidates(line, engine.glyph_tolerance)
        if any(TextDetector._line_matches(text, c, mode, None, None, None, None, False) for c in candidates):
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            out.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
    return out


def _agrees(a: list, b: list, tolerance: float) -> bool:
    return len(a) == len(b) and all(any(math.dist(p, q) <= tolerance for q in b) for p in a)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('project', type=Path, help='ADARE project directory (contains run/)')
    parser.add_argument('--a', default='paddle', help='baseline profile, engine[:lang] (default: paddle)')
    parser.add_argument('--b', default='rapidocr:latin', help='candidate profile (default: rapidocr:latin)')
    parser.add_argument('--experiments', type=int, default=50, help='most recent experiments to sample')
    parser.add_argument('--frames', type=int, default=3, help='unique frames per experiment')
    parser.add_argument('--tolerance', type=float, default=20.0, help='same place = centres within N px')
    parser.add_argument('--cache-dir', type=Path, default=Path('.ocr_compare_cache'))
    parser.add_argument('--out', type=Path, help='write the full report as JSON')
    args = parser.parse_args()

    engine_a, engine_b = _profile(args.a), _profile(args.b)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    sample = _sample(args.project.expanduser(), args.experiments, args.frames)
    n_frames = sum(len(s['frames']) for s in sample)
    print(f'{len(sample)} experiments, {n_frames} frames: {engine_a.profile} vs {engine_b.profile}', flush=True)

    report = {'a': engine_a.fingerprint(), 'b': engine_b.fingerprint(), 'experiments': []}
    total_relevant = total_agree = done = 0
    for entry in sample:
        relevant = agree = 0
        disagreements = []
        for png, digest in entry['frames']:
            dets = {}
            for engine in (engine_a, engine_b):
                dets[engine.profile] = _detect(engine, png, digest, args.cache_dir)
            done += 1
            for text, mode in entry['queries']:
                hits_a = _hits(engine_a, dets[engine_a.profile], text, mode)
                hits_b = _hits(engine_b, dets[engine_b.profile], text, mode)
                if not hits_a and not hits_b:
                    continue
                relevant += 1
                if _agrees(hits_a, hits_b, args.tolerance):
                    agree += 1
                else:
                    disagreements.append({'frame': str(png), 'query': text, 'mode': mode, 'a': hits_a, 'b': hits_b})
        total_relevant += relevant
        total_agree += agree
        report['experiments'].append(
            {
                'experiment': entry['experiment'],
                'frames': len(entry['frames']),
                'queries': len(entry['queries']),
                'relevant': relevant,
                'agree': agree,
                'disagreements': disagreements,
            }
        )
        print(f'[{done}/{n_frames}] {entry["experiment"]}: {agree}/{relevant} agree', flush=True)

    report['summary'] = {
        'experiments': len(sample),
        'frames': n_frames,
        'relevant_pairs': total_relevant,
        'agreeing_pairs': total_agree,
        'experiments_fully_agreeing': sum(e['agree'] == e['relevant'] for e in report['experiments']),
    }
    print(json.dumps(report['summary'], indent=1))
    if args.out:
        args.out.write_text(json.dumps(report, indent=1))
        print(f'report: {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
