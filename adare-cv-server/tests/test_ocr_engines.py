"""Golden test for the pinned default OCR profile (rapidocr-v5m-latin).

OCR decides where the client clicks, so the default profile is pinned here: the
profile and model hashes, and the exact text read from rendered German/French UI
string frames with known ground truth. A failure means OCR results - and therefore
experiment clicks - changed: a dependency, model, parameter or platform difference.
Investigate before changing a threshold.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest
from adare_cv_server import ocr_engines
from adare_cv_server.constants import OCRProfiles
from adare_cv_server.ocr_processing import OCRProcessor

FIXTURES = Path(__file__).parent / 'fixtures' / 'ocr'
RENDERED_EXACT_MIN = 0.88  # measured 0.92 on the full rendered set (2026-11-01)


def _ocr(path: Path):
    return asyncio.run(OCRProcessor.process_screenshot(path.read_bytes()))


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


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))
