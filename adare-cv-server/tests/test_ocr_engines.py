"""Golden test for the pinned default OCR profile (rapidocr-v5m-latin).

OCR decides where the client clicks, so the default profile's output on real
screenshots is pinned here: line recall, the real text queries experiments use
(found, at the same place) and the model hashes. A failure means OCR results -
and therefore experiment clicks - changed: a dependency, model, parameter or
platform difference. Investigate before regenerating.

Fixtures (tests/fixtures/ocr/): eight 1080p T2F Firefox screenshots and two
rendered German/French UI-string frames with exact ground truth.

Regenerate the expectations (only after an intended, A/B-validated change)::

    uv run --no-sync python adare-cv-server/tests/test_ocr_engines.py --regenerate
"""

import asyncio
import json
import math
import sys
from pathlib import Path

import pytest
from adare_cv_server import ocr_engines
from adare_cv_server.constants import OCRProfiles
from adare_cv_server.ocr_processing import OCRProcessor, TextDetector

FIXTURES = Path(__file__).parent / 'fixtures' / 'ocr'
EXPECTED = FIXTURES / 'expected_rapidocr-v5m-latin.json'

# Text queries real experiments issue (from T2F mcp_gui.log), plus tree rows the
# Latin model reads with a leading '>' (leading-glyph tolerance must find them).
QUERIES = [
    ('Organize', 'substring'),
    ('Manage Bookmarks', 'substring'),
    ('Browsing & download history', 'substring'),
    ('Show all downloads', 'substring'),
    (r'^\s*Everything\s*[.…]*\s*$', 'regex'),
    (r'^\s*Cancel\s*[.…]*\s*$', 'regex'),
    (r'^\s*Clear\s*[.…]*\s*$', 'regex'),
    (r'^\s*Bookmarks\ Menu\s*[.…]*\s*$', 'regex'),
    (r'^\s*Bookmarks\ Toolbar\s*[.…]*\s*$', 'regex'),
    (r'^\s*Other\ Bookmarks\s*[.…]*\s*$', 'regex'),
    (r'^\s*New\ Tab\s*[.…]*\s*$', 'regex'),
    (r'^\s*History\s*[.…]*\s*$', 'regex'),
    ('Mozilla Firefox', 'substring'),
]

LINE_RECALL_MIN = 0.95  # expected lines found with identical text near the same place
LINE_TOLERANCE_PX = 8
QUERY_TOLERANCE_PX = 10
RENDERED_EXACT_MIN = 0.88  # measured 0.92 on the full rendered set (2026-11-01)


def _real_frames() -> list[Path]:
    return sorted(FIXTURES.glob('t2f_*.png'))


def _center(box) -> tuple[float, float]:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def _ocr(path: Path):
    return asyncio.run(OCRProcessor.process_screenshot(path.read_bytes()))


def _query_hits(path: Path, text: str, mode: str) -> list[tuple[int, int]]:
    result = asyncio.run(TextDetector.find_text(text, path.read_bytes(), match_mode=mode))
    return [(loc['location']['x'], loc['location']['y']) for loc in result['locations']]


@pytest.fixture(scope='module')
def rapid_engine():
    """Run this module with the pinned default profile, restoring the previous engine after."""
    previous = ocr_engines._engine
    engine = ocr_engines.configure_engine(OCRProfiles.ENGINE_RAPIDOCR, 'latin')
    yield engine
    ocr_engines._engine = previous


def test_default_profile_is_rapidocr_latin():
    assert OCRProfiles.DEFAULT_ENGINE == 'rapidocr'
    assert OCRProfiles.DEFAULT_LANG == 'latin'
    assert ocr_engines.build_engine('rapidocr', 'latin').profile == 'rapidocr-v5m-latin'


def test_model_files_match_pins(rapid_engine):
    rapid_engine.load()
    model_dir = ocr_engines.rapidocr_model_dir()
    for rel, sha in (OCRProfiles.RAPIDOCR_DET_MODEL, OCRProfiles.RAPIDOCR_REC_MODELS['latin']):
        assert ocr_engines.file_sha256(model_dir / Path(rel).name) == sha


def test_model_hash_mismatch_is_a_hard_error(tmp_path):
    rel, sha = OCRProfiles.RAPIDOCR_DET_MODEL
    (tmp_path / Path(rel).name).write_bytes(b'not the pinned model')
    with pytest.raises(ocr_engines.OCRProcessingError, match='sha256'):
        ocr_engines.ensure_pinned_model(rel, sha, tmp_path)
    # Never silently replaced.
    assert (tmp_path / Path(rel).name).read_bytes() == b'not the pinned model'


@pytest.mark.parametrize('frame', _real_frames(), ids=lambda p: p.stem)
def test_golden_lines(rapid_engine, frame):
    expected = json.loads(EXPECTED.read_text(encoding='utf-8'))['frames'][frame.name]['lines']
    got = [(text, _center(box)) for box, (text, _score) in _ocr(frame)]
    found = sum(
        any(t == line['text'] and math.dist(c, line['center']) <= LINE_TOLERANCE_PX for t, c in got)
        for line in expected
    )
    recall = found / len(expected)
    assert recall >= LINE_RECALL_MIN, f'{frame.name}: line recall {recall:.1%} < {LINE_RECALL_MIN:.0%}'


@pytest.mark.parametrize('frame', _real_frames(), ids=lambda p: p.stem)
def test_golden_queries(rapid_engine, frame):
    expected = json.loads(EXPECTED.read_text(encoding='utf-8'))['frames'][frame.name]['queries']
    for text, mode in QUERIES:
        want = expected[f'{mode}:{text}']
        got = _query_hits(frame, text, mode)
        assert len(got) == len(want), f'{frame.name} {text!r}: {len(got)} hits, expected {len(want)}'
        for point in want:
            assert any(math.dist(point, g) <= QUERY_TOLERANCE_PX for g in got), (
                f'{frame.name} {text!r}: no hit near {point} (got {got})'
            )


def test_leading_glyph_tolerance_finds_tree_rows(rapid_engine):
    """The Latin model reads Firefox's tree arrow as '>'; anchored queries must still hit."""
    frame = FIXTURES / 't2f_add_bookmark_library.png'
    assert _query_hits(frame, r'^\s*Bookmarks\ Menu\s*[.…]*\s*$', 'regex')


def test_rendered_german_strings(rapid_engine):
    truth = json.loads((FIXTURES / 'rendered_strings.json').read_text(encoding='utf-8'))
    exact = total = 0
    for name, boxes in truth.items():
        dets = _ocr(FIXTURES / name)
        for string, (x0, y0, x1, y1) in boxes:
            cy = (y0 + y1) / 2
            parts = [
                text
                for box, (text, _s) in dets
                if min(p[1] for p in box) - 4 <= cy <= max(p[1] for p in box) + 4
                and min(p[0] for p in box) < x1
                and max(p[0] for p in box) > x0
            ]
            total += 1
            exact += ' '.join(parts).strip() == string
    assert exact / total >= RENDERED_EXACT_MIN, f'rendered exact lines {exact / total:.1%}'


def _regenerate() -> None:
    ocr_engines.configure_engine(OCRProfiles.ENGINE_RAPIDOCR, 'latin')
    frames = {}
    for frame in _real_frames():
        lines = [
            {'text': text, 'center': [round(v, 1) for v in _center(box)]}
            for box, (text, score) in _ocr(frame)
            if len(text.strip()) >= 2 and score >= 0.8
        ]
        queries = {f'{mode}:{text}': [list(p) for p in _query_hits(frame, text, mode)] for text, mode in QUERIES}
        frames[frame.name] = {'lines': lines, 'queries': queries}
    payload = {'profile': ocr_engines.get_engine().fingerprint(), 'frames': frames}
    EXPECTED.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'wrote {EXPECTED}')


if __name__ == '__main__':
    if '--regenerate' in sys.argv:
        _regenerate()
    else:
        sys.exit(pytest.main([__file__, '-q']))
