"""Per-frame OCR cache, leading-glyph tolerance and engine info - with a fake engine (no models)."""

import asyncio
import threading
import time

import cv2
import numpy as np
import pytest
from adare_cv_server import ocr_engines, server
from adare_cv_server.exceptions import OCRProcessingError
from adare_cv_server.ocr_processing import OCRProcessor, TextDetector

BOX = [[10.0, 10.0], [110.0, 10.0], [110.0, 30.0], [10.0, 30.0]]


class FakeEngine:
    name = 'fake'
    lang = 'latin'

    def __init__(self, lines=('>Bookmarks Menu',), glyph_tolerance=True, profile='fake-1', delay=0.0, fail=False):
        self.lines = list(lines)
        self.glyph_tolerance = glyph_tolerance
        self.profile = profile
        self.delay = delay
        self.fail = fail
        self.calls = 0
        self._lock = threading.Lock()

    def fingerprint(self):
        return {
            'profile': self.profile,
            'engine': self.name,
            'models': {'det': {'name': 'd', 'sha256': 'x'}},
            'glyph_tolerance': self.glyph_tolerance,
        }

    def load(self):
        pass

    def detect(self, img):
        with self._lock:
            self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise OCRProcessingError('boom')
        return [[BOX, (text, 0.99)] for text in self.lines]


def _png(seed: int = 0) -> bytes:
    img = np.full((40, 120, 3), 255, np.uint8)
    img[0, 0] = (seed % 256, 0, 0)
    return cv2.imencode('.png', img)[1].tobytes()


@pytest.fixture
def use_engine():
    previous = ocr_engines._engine
    OCRProcessor._cache.clear()

    def _use(engine):
        ocr_engines._engine = engine
        return engine

    yield _use
    ocr_engines._engine = previous
    OCRProcessor._cache.clear()


def test_identical_frame_is_ocrd_once(use_engine):
    engine = use_engine(FakeEngine())
    first = asyncio.run(OCRProcessor.process_screenshot(_png()))
    second = asyncio.run(OCRProcessor.process_screenshot(_png()))
    assert first == second
    assert engine.calls == 1


def test_different_frame_or_engine_misses(use_engine):
    engine = use_engine(FakeEngine())
    asyncio.run(OCRProcessor.process_screenshot(_png(1)))
    asyncio.run(OCRProcessor.process_screenshot(_png(2)))
    assert engine.calls == 2
    other = use_engine(FakeEngine(profile='fake-2'))
    asyncio.run(OCRProcessor.process_screenshot(_png(1)))
    assert other.calls == 1


def test_concurrent_identical_requests_share_one_run(use_engine):
    engine = use_engine(FakeEngine(delay=0.2))

    async def both():
        return await asyncio.gather(*(OCRProcessor.process_screenshot(_png()) for _ in range(4)))

    results = asyncio.run(both())
    assert all(r == results[0] for r in results)
    assert engine.calls == 1


def test_failures_are_not_cached(use_engine):
    engine = use_engine(FakeEngine(fail=True))
    for _ in range(2):
        with pytest.raises(OCRProcessingError):
            asyncio.run(OCRProcessor.process_screenshot(_png()))
    assert engine.calls == 2


def test_lru_evicts_oldest(use_engine, monkeypatch):
    monkeypatch.setattr(OCRProcessor._cache, 'maxsize', 2)
    engine = use_engine(FakeEngine())
    for seed in (1, 2, 3, 1):
        asyncio.run(OCRProcessor.process_screenshot(_png(seed)))
    assert engine.calls == 4  # frame 1 was evicted by frame 3


def test_undecodable_bytes_raise(use_engine):
    use_engine(FakeEngine())
    with pytest.raises(OCRProcessingError, match='decode'):
        asyncio.run(OCRProcessor.process_screenshot(b'not an image'))


ANCHORED = r'^\s*Bookmarks\ Menu\s*[.…]*\s*$'


@pytest.mark.parametrize(
    ('line', 'glyph_tolerance', 'found'),
    [
        ('>Bookmarks Menu', True, True),
        ('> Bookmarks Menu', True, True),
        ('• Bookmarks Menu', True, True),
        ('★Bookmarks Menu', True, True),
        ('>Bookmarks Menu', False, False),  # paddle-legacy: unchanged behaviour
        ('Bookmarks Menu', False, True),
        ('>>>Bookmarks Menu', True, False),  # at most two leading glyphs
        ('Old Bookmarks Menu', True, False),
    ],
)
def test_leading_glyph_tolerance(use_engine, line, glyph_tolerance, found):
    use_engine(FakeEngine(lines=[line], glyph_tolerance=glyph_tolerance))
    result = asyncio.run(TextDetector.find_text(ANCHORED, _png(), match_mode='regex'))
    assert bool(result['locations']) is found
    if found:
        assert result['locations'][0]['text'] == line  # reported text is the OCR line as read


def test_fuzzy_match_uses_stripped_line(use_engine):
    use_engine(FakeEngine(lines=['>Other']))
    result = asyncio.run(TextDetector.find_text('Other', _png(), match_mode='fuzzy', min_similarity=1.0))
    assert result['locations']


def test_engine_info_reports_fingerprint_and_server_version(use_engine):
    use_engine(FakeEngine())
    info = asyncio.run(server.get_engine_info())
    assert info['profile'] == 'fake-1'
    assert info['glyph_tolerance'] is True
    assert 'adare-cv-server' in info['versions']


def test_profile_selection_from_env(monkeypatch):
    previous = ocr_engines._engine
    try:
        monkeypatch.setenv('ADARE_OCR_ENGINE', 'rapidocr')
        monkeypatch.setenv('ADARE_OCR_LANG', 'en')
        assert ocr_engines.configure_engine().profile == 'rapidocr-v5m-en'
        assert ocr_engines.configure_engine('paddle').profile == 'paddle-legacy'
        with pytest.raises(OCRProcessingError):
            ocr_engines.configure_engine('tesseract')
    finally:
        ocr_engines._engine = previous
