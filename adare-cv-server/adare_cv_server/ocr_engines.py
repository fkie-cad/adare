"""Pluggable OCR engines behind one pinned interface.

Every engine returns detections in the format the rest of the server (TextDetector,
debug CSV/PNG) already uses: ``[box4, (text, score)]`` with ``box4`` four ``[x, y]``
corners in original screenshot pixels.

Two profiles exist:

* ``rapidocr-v5m-<lang>`` (default): RapidOCR on onnxruntime (CPU), PP-OCRv5 mobile
  detection + mobile recognition. Model files are pinned by sha256 and verified
  before use; a mismatch is a hard error.
* ``paddle-legacy``: the previous PaddleOCR path, unchanged, for existing
  experiments until the A/B is clean. Needs the ``paddle`` extra.

The engine is chosen once per process (``configure_engine`` from the CLI, or the
``ADARE_OCR_ENGINE`` / ``ADARE_OCR_LANG`` environment for in-process callers).
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import math
import os
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

from .constants import OCRConstants, OCRProfiles
from .exceptions import OCRProcessingError

log = logging.getLogger(__name__)

Detection = list[Any]  # [box4, (text, score)]

_DOWNLOAD_TIMEOUT_S = 120


class OcrEngine(Protocol):
    """What the OCR processor needs from an engine."""

    name: str
    profile: str
    lang: str
    glyph_tolerance: bool

    def fingerprint(self) -> dict[str, Any]:
        """Everything that determines this engine's output (pinned + recorded per run)."""
        ...

    def load(self) -> None:
        """Load (and, for pinned models, verify) the models. Idempotent."""
        ...

    def detect(self, img_bgr: np.ndarray) -> list[Detection]:
        """OCR one BGR image; boxes in the image's own pixel space."""
        ...


def package_version(dist: str) -> str | None:
    """Installed version of ``dist``, or None if it is not installed."""
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return None


def adaptive_upscale(max_side: int) -> float:
    """The legacy adaptive pre-OCR upscale factor (see OCRConstants.OCR_UPSCALE)."""
    max_upscale = OCRConstants.OCR_UPSCALE
    target_side = OCRConstants.OCR_TARGET_SIDE
    if max_upscale and max_upscale > 1.0 and target_side and max_side > 0:
        return min(max_upscale, max(1.0, target_side / max_side))
    return 1.0


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def rapidocr_model_dir() -> Path:
    """Where pinned RapidOCR models live: ``ADARE_OCR_MODEL_DIR`` or RapidOCR's own model cache."""
    override = os.environ.get('ADARE_OCR_MODEL_DIR')
    if override:
        return Path(override).expanduser()
    import rapidocr

    return Path(rapidocr.__file__).resolve().parent / 'models'


def ensure_pinned_model(rel_url: str, sha256: str, model_dir: Path) -> Path:
    """Return the local path of a pinned model, downloading it once if missing.

    An existing file with the wrong hash is never silently replaced: results would
    no longer be reproducible, so it is a hard error the operator has to resolve.
    """
    path = model_dir / Path(rel_url).name
    if path.exists():
        actual = file_sha256(path)
        if actual != sha256:
            raise OCRProcessingError(
                f"OCR model {path} has sha256 {actual}, expected {sha256}. Refusing to use it: "
                f"delete the file to re-download the pinned model."
            )
        return path

    url = f"{OCRProfiles.RAPIDOCR_MODEL_BASE_URL}/{rel_url}"
    log.info(f"Downloading pinned OCR model {url} -> {path}")
    model_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=model_dir)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, 'wb') as out, urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_S) as resp:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
        actual = file_sha256(tmp)
        if actual != sha256:
            raise OCRProcessingError(f"Downloaded OCR model {url} has sha256 {actual}, expected {sha256}")
        os.replace(tmp, path)
    except (OSError, urllib.error.URLError) as e:
        raise OCRProcessingError(f"Could not download pinned OCR model {url}: {e}") from e
    finally:
        tmp.unlink(missing_ok=True)
    return path


class RapidOcrEngine:
    """RapidOCR (onnxruntime, CPU) with pinned PP-OCRv5 mobile det + mobile rec."""

    name = OCRProfiles.ENGINE_RAPIDOCR
    glyph_tolerance = True

    def __init__(self, lang: str = OCRProfiles.DEFAULT_LANG, threads: int | None = None):
        if lang not in OCRProfiles.RAPIDOCR_REC_MODELS:
            raise OCRProcessingError(f"Unsupported OCR language {lang!r}; choose one of {list(OCRProfiles.LANGS)}")
        self.lang = lang
        self.profile = OCRProfiles.RAPIDOCR_PROFILE[lang]
        self.threads = threads or int(os.environ.get('ADARE_OCR_THREADS', OCRProfiles.DEFAULT_THREADS))
        self._ocr = None
        self._lock = threading.Lock()

    def fingerprint(self) -> dict[str, Any]:
        det_file, det_sha = OCRProfiles.RAPIDOCR_DET_MODEL
        rec_file, rec_sha = OCRProfiles.RAPIDOCR_REC_MODELS[self.lang]
        return {
            'profile': self.profile,
            'engine': self.name,
            'lang': self.lang,
            'models': {
                'det': {'name': Path(det_file).name, 'sha256': det_sha},
                'rec': {'name': Path(rec_file).name, 'sha256': rec_sha},
            },
            'params': dict(OCRProfiles.RAPIDOCR_PARAMS),
            'upscale': {
                'max': OCRConstants.OCR_UPSCALE,
                'target_side': OCRConstants.OCR_TARGET_SIDE,
                'min_factor': OCRConstants.OCR_MIN_UPSCALE,
            },
            'glyph_tolerance': self.glyph_tolerance,
            'versions': {
                'rapidocr': package_version('rapidocr'),
                'onnxruntime': package_version('onnxruntime'),
                'cv2': cv2.__version__,
            },
        }

    def load(self) -> None:
        if self._ocr is not None:
            return
        with self._lock:
            if self._ocr is not None:
                return
            from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

            model_dir = rapidocr_model_dir()
            det_path = ensure_pinned_model(*OCRProfiles.RAPIDOCR_DET_MODEL, model_dir)
            rec_path = ensure_pinned_model(*OCRProfiles.RAPIDOCR_REC_MODELS[self.lang], model_dir)
            rec_lang = {'latin': LangRec.LATIN, 'en': LangRec.EN}[self.lang]
            log.info(f"Initializing RapidOCR profile {self.profile} ({self.threads} threads)")
            self._ocr = RapidOCR(
                params={
                    **OCRProfiles.RAPIDOCR_PARAMS,
                    'Global.log_level': 'warning',
                    'Det.ocr_version': OCRVersion.PPOCRV5,
                    'Det.model_type': ModelType.MOBILE,
                    'Det.model_path': str(det_path),
                    'Rec.ocr_version': OCRVersion.PPOCRV5,
                    'Rec.model_type': ModelType.MOBILE,
                    'Rec.lang_type': rec_lang,
                    'Rec.model_path': str(rec_path),
                    'EngineConfig.onnxruntime.intra_op_num_threads': self.threads,
                }
            )

    def detect(self, img_bgr: np.ndarray) -> list[Detection]:
        self.load()
        upscale = adaptive_upscale(max(img_bgr.shape[:2]))
        if upscale < OCRConstants.OCR_MIN_UPSCALE:
            upscale = 1.0
        if upscale != 1.0:
            log.info(f"Upscaling screenshot {upscale:.2f}x before OCR ({img_bgr.shape[1]}x{img_bgr.shape[0]})")
            img_bgr = cv2.resize(img_bgr, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)

        result = self._ocr(img_bgr)
        if result.boxes is None or result.txts is None:
            return []
        detections = []
        for box, text, score in zip(result.boxes, result.txts, result.scores, strict=True):
            box = np.asarray(box, dtype=np.float64)
            if upscale != 1.0:
                box = box / upscale
            detections.append([box.tolist(), (text, float(score))])
        return detections


class PaddleOcrEngine:
    """The legacy PaddleOCR path, moved here unchanged (needs the ``paddle`` extra)."""

    name = OCRProfiles.ENGINE_PADDLE
    profile = OCRProfiles.PADDLE_PROFILE
    lang = 'en'
    glyph_tolerance = False

    # PaddleOCR's constructor is expensive (model-availability checks that can
    # involve network I/O) and was previously rebuilt on every single call, which
    # is why a single find_text call could intermittently take 10s of minutes
    # instead of its usual sub-second cost. Cache one instance for the process
    # lifetime instead. Guarded by a lock since the first callers can race to
    # build it (OCR runs on the module-level executor's MAX_WORKERS threads).
    _ocr_instance = None
    _ocr_instance_lock = threading.Lock()

    def fingerprint(self) -> dict[str, Any]:
        return {
            'profile': self.profile,
            'engine': self.name,
            'lang': self.lang,
            'models': {
                'det': {
                    'name': OCRProfiles.PADDLE_DET_MODEL,
                    'sha256': _paddle_model_sha(OCRProfiles.PADDLE_DET_MODEL),
                },
                'rec': {
                    'name': OCRProfiles.PADDLE_REC_MODEL,
                    'sha256': _paddle_model_sha(OCRProfiles.PADDLE_REC_MODEL),
                },
            },
            'params': {
                'text_det_unclip_ratio': OCRConstants.OCR_DET_UNCLIP_RATIO,
                'text_det_thresh': OCRConstants.OCR_DET_DB_THRESH,
                'text_det_box_thresh': OCRConstants.OCR_DET_BOX_THRESH,
                'text_det_limit_type': OCRConstants.OCR_DET_LIMIT_TYPE,
                'text_det_limit_side_len_floor': OCRConstants.OCR_DET_LIMIT_SIDE_LEN,
            },
            'upscale': {'max': OCRConstants.OCR_UPSCALE, 'target_side': OCRConstants.OCR_TARGET_SIDE},
            'glyph_tolerance': self.glyph_tolerance,
            'versions': {
                'paddleocr': package_version('paddleocr'),
                'paddlepaddle': package_version('paddlepaddle'),
                'cv2': cv2.__version__,
            },
        }

    def load(self) -> None:
        self._get_paddle_ocr()

    @classmethod
    def _get_paddle_ocr(cls):
        """Return the cached PaddleOCR instance, building it on first use."""
        if cls._ocr_instance is None:
            with cls._ocr_instance_lock:
                if cls._ocr_instance is None:
                    try:
                        from paddleocr import PaddleOCR
                    except ImportError as e:
                        raise OCRProcessingError(
                            "The paddle OCR engine needs the 'paddle' extra: install adare-cv-server[paddle]"
                        ) from e

                    log.info("Initializing PaddleOCR (first use - cached for process lifetime)...")

                    # Capture current logging level as PaddleOCR might change it
                    root_logger = logging.getLogger()
                    original_level = root_logger.getEffectiveLevel()

                    cls._ocr_instance = PaddleOCR(
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                        text_det_unclip_ratio=OCRConstants.OCR_DET_UNCLIP_RATIO,
                        text_det_thresh=OCRConstants.OCR_DET_DB_THRESH,
                        text_det_box_thresh=OCRConstants.OCR_DET_BOX_THRESH,
                        lang='en',  # Explicitly set language
                    )

                    # Restore logging level
                    root_logger.setLevel(original_level)
        return cls._ocr_instance

    def detect(self, img: np.ndarray) -> list[Detection]:
        ocr = self._get_paddle_ocr()
        original_max_side = max(img.shape[:2])

        # Pre-OCR upscaling: PaddleOCR recognizes tiny text poorly (e.g. a
        # wrapped desktop-icon caption), so small images benefit from being
        # upscaled before predict(). But scaling is adaptive, not flat: we
        # only scale up to OCR_TARGET_SIDE (the detector's sweet spot), never
        # beyond OCR_UPSCALE, and not at all once the image already meets it.
        # A flat upscale on an already-large screenshot pushes it past the
        # detection-side-length limit, silently defeating itself (PaddleOCR
        # downscales back down for detection) and wrecking recall on
        # ordinary-sized UI text - see OCR_UPSCALE's docstring in constants.py.
        upscale = adaptive_upscale(original_max_side)

        if upscale != 1.0:
            log.info(f"Upscaling screenshot {upscale:.2f}x before OCR ({img.shape[1]}x{img.shape[0]})")
            img = cv2.resize(img, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)

        # The detection-side limit must never be smaller than the image we're
        # about to hand PaddleOCR, or "max" limit_type will downscale it right
        # back down before detection - undoing any upscale above and, just as
        # importantly, shrinking already-large native screenshots (e.g. 4K)
        # that never went through the upscale path at all.
        processed_max_side = max(img.shape[:2])
        det_limit_side_len = max(OCRConstants.OCR_DET_LIMIT_SIDE_LEN, math.ceil(processed_max_side))

        log.info("Running OCR prediction with numpy array...")
        result = ocr.predict(
            input=img,
            text_det_limit_side_len=det_limit_side_len,
            text_det_limit_type=OCRConstants.OCR_DET_LIMIT_TYPE,
        )

        # Extract detection results from predict() format
        detections = []
        for res in result:
            rec_texts = res['rec_texts']
            rec_polys = res['rec_polys']
            rec_scores = res['rec_scores']

            # Combine texts, boxes and scores
            for text, box, score in zip(rec_texts, rec_polys, rec_scores, strict=False):
                # Rescale box back to original screenshot-pixel space
                if upscale and upscale != 1.0:
                    box = box / upscale
                box_points = box.tolist()
                detections.append([box_points, (text, score)])
        return detections


def _paddle_model_sha(model_name: str) -> str | None:
    """Best-effort sha256 of a PaddleX-cached model's weights (None if not cached yet)."""
    cache_home = Path(os.environ.get('PADDLE_PDX_CACHE_HOME', Path.home() / '.paddlex'))
    weights = cache_home / 'official_models' / model_name / 'inference.pdiparams'
    try:
        return file_sha256(weights)
    except OSError:
        return None


def fingerprint_key(engine: OcrEngine) -> str:
    """Stable short hash of everything that determines the engine's output.

    Computed once per engine instance: an engine's configuration is fixed for its
    lifetime, and fingerprint() can be costly (paddle hashes its weight files).
    """
    cached = engine.__dict__.get('_fingerprint_key')
    if cached is not None:
        return cached
    fp = engine.fingerprint()
    # Paddle's best-effort file hashes appear once the models are cached; the
    # cache key must not change mid-process because of that.
    stable = {k: v for k, v in fp.items() if k != 'models'} | {
        'models': {role: m['name'] for role, m in fp['models'].items()}
    }
    key = hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()[:16]
    engine.__dict__['_fingerprint_key'] = key
    return key


# ---------------------------------------------------------------------------
# Process-wide engine selection
# ---------------------------------------------------------------------------

_engine: OcrEngine | None = None
_engine_lock = threading.Lock()


def build_engine(engine: str, lang: str = OCRProfiles.DEFAULT_LANG) -> OcrEngine:
    if engine == OCRProfiles.ENGINE_RAPIDOCR:
        return RapidOcrEngine(lang)
    if engine == OCRProfiles.ENGINE_PADDLE:
        return PaddleOcrEngine()
    raise OCRProcessingError(f"Unknown OCR engine {engine!r}; choose one of {list(OCRProfiles.ENGINES)}")


def configure_engine(engine: str | None = None, lang: str | None = None) -> OcrEngine:
    """Select the process's OCR engine (CLI options > ADARE_OCR_* env > defaults)."""
    global _engine
    engine = engine or os.environ.get('ADARE_OCR_ENGINE') or OCRProfiles.DEFAULT_ENGINE
    lang = lang or os.environ.get('ADARE_OCR_LANG') or OCRProfiles.DEFAULT_LANG
    with _engine_lock:
        _engine = build_engine(engine, lang)
        log.info(f"OCR profile: {_engine.profile}")
        return _engine


def get_engine() -> OcrEngine:
    """The process's OCR engine, configured from the environment on first use."""
    if _engine is None:
        return configure_engine()
    return _engine
