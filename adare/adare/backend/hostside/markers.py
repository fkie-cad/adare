"""Step markers for the qemufile evidence store.

The host-side backend writes playbook step boundaries as ``marker`` events
(``docs/SCHEMA.md`` section 5, source ``orchestrator``) into a qemufile *run
directory* (``<adare run>/qfm/``), through the ``qfm`` Python package. Every
marker carries host monotonic and wall time stamped back to back by
``qfm.store.EventWriter``, so any other sensor writing into the same run
directory (live RAM poller, qfmonitor disk events) shares the time base and a
step can be correlated with what the guest did during it.

``qfm`` is not on PyPI. It is imported by path (no install, no edit of the
qemufile tree): ``ADARE_QFM_SRC`` (a directory containing the ``qfm`` package,
i.e. ``<qemufile>/src``), else a ``qemufile`` checkout next to the ADARE
checkout, else an already importable ``qfm``.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SENSOR = 'adare-hostside'


class MarkerUnavailable(RuntimeError):
    """The qfm package could not be imported."""


def _candidate_paths() -> list[Path]:
    paths = []
    env = os.environ.get('ADARE_QFM_SRC')
    if env:
        paths.append(Path(env))
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / 'adare-cv-server').is_dir() or (parent / 'adarevm').is_dir():  # ADARE checkout root
            # next to the checkout, or next to the workspace folder that holds it
            paths.extend([parent.parent / 'qemufile' / 'src', parent.parent.parent / 'qemufile' / 'src'])
            break
    return paths


def import_qfm():
    """Import and return the ``qfm`` package (see module docstring for the search order)."""
    try:
        import qfm

        return qfm
    except ImportError:
        pass
    for path in _candidate_paths():
        if (path / 'qfm' / '__init__.py').is_file():
            sys.path.insert(0, str(path))
            import qfm

            log.info(f"qfm imported from {path}")
            return qfm
    raise MarkerUnavailable(
        'qfm (qemufile evidence store) is not importable: set ADARE_QFM_SRC to <qemufile>/src '
        '(or place a qemufile checkout next to the ADARE checkout)'
    )


class NullMarkerSink:
    """Drop-in used when markers are disabled; keeps the call sites unconditional."""

    run_dir: Path | None = None

    def marker(self, name: str, **data: Any) -> None:
        return None

    def step_start(self, index: int, action_type: str, **data: Any) -> None:
        return None

    def step_end(self, index: int, action_type: str, success: bool, **data: Any) -> None:
        return None

    def close(self) -> None:
        return None


class MarkerSink:
    """Writes ``marker`` events into a qfm run directory."""

    def __init__(self, run_dir: Path, run_id: str, spec: dict[str, Any], images: dict[str, str] | None = None):
        qfm = import_qfm()
        from qfm.store import EventWriter, RunDir, make_provenance

        self._make_provenance = make_provenance
        self.run_dir = Path(run_dir)
        self.run_id = run_id
        # hash_images=False: ADARE already records the image digests; hashing a
        # multi-GB disk per run would cost more than the run's markers are worth.
        self._run = RunDir.create(
            self.run_dir, spec=spec, run_id=run_id, images=images or {}, hash_images=False, exist_ok=True
        )
        self._writer = EventWriter(self._run, flush_every=1)
        self.qfm_version = getattr(qfm, '__version__', 'unknown')
        self.count = 0

    def marker(self, name: str, **data: Any) -> None:
        payload = {'marker': name, **{k: v for k, v in data.items() if v is not None}}
        self._writer.emit(
            'marker',
            'orchestrator',
            data=payload,
            provenance=self._make_provenance(
                SENSOR,
                reader='unknown',
                paused_ms=0,
                consistency='synchronous',
                basis='sensor-design',
                note='emitted by the ADARE host-side backend at the instant the step boundary was reached',
            ),
        )
        self.count += 1

    def step_start(self, index: int, action_type: str, **data: Any) -> None:
        self.marker('adare.step.start', step=index, action=action_type, **data)

    def step_end(self, index: int, action_type: str, success: bool, **data: Any) -> None:
        self.marker('adare.step.end', step=index, action=action_type, success=success, **data)

    def close(self) -> None:
        self._writer.close()


def open_markers(run_dir: Path, run_id: str, spec: dict[str, Any], images: dict[str, str] | None = None):
    """A :class:`MarkerSink`, or a :class:`NullMarkerSink` when ``ADARE_HOSTSIDE_MARKERS=off``."""
    if os.environ.get('ADARE_HOSTSIDE_MARKERS', 'on').lower() in ('off', '0', 'false', 'no'):
        return NullMarkerSink()
    return MarkerSink(run_dir, run_id, spec, images)
