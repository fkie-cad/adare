"""Evidence on a failed playbook action (T2F gap G8).

When an action fails (target not found, ``wait_until`` timeout, command error, ...) the run
used to keep only the error message; the screenshot of the failing search existed only with
``--debug-screenshots``. :func:`collect_failure_evidence` writes, under
``<run>/reporting/failure/``:

* ``aNN_last_search.png``  the screenshot the target resolver last searched (what it saw),
* ``aNN_screen.png``       a fresh screenshot taken after the failure (skipped if identical),
* ``aNN_ocr.json``         the full OCR dump (``get_all_text``) of that fresh screenshot,
* ``aNN_failure.json``     the action, its target description(s), the result message and the
  target of the last resolution attempt (which is the failing inner step for a block/loop).

``NN`` is the 1-based playbook index. Collection is best effort and never raises: the run's
failed status and its error message must not depend on it. ``ADARE_FAILURE_EVIDENCE=0``
turns it off.
"""

import asyncio
import base64
import binascii
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import attrs

log = logging.getLogger(__name__)

EVIDENCE_ENV = "ADARE_FAILURE_EVIDENCE"
FAILURE_DIRNAME = "failure"
OCR_TIMEOUT_SECONDS = 150.0


def evidence_enabled() -> bool:
    return os.environ.get(EVIDENCE_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def describe_target(target) -> dict[str, Any] | None:
    """JSON-safe description of a Target: every set field, strategy by class name."""
    if target is None:
        return None
    if not attrs.has(type(target)):
        return {"repr": repr(target)}
    out = attrs.asdict(target, recurse=True, filter=lambda attribute, value: value is not None)
    strategy = getattr(target, "strategy", None)
    if strategy is not None:
        out["strategy"] = {type(strategy).__name__: attrs.asdict(strategy) if attrs.has(type(strategy)) else {}}
    return out


def _condition_targets(condition, role: str = "condition") -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if condition is None:
        return found
    if getattr(condition, "exists", None) is not None:
        found.append({"role": f"{role}.exists", "target": describe_target(condition.exists)})
    if getattr(condition, "not_exists", None) is not None:
        found.append({"role": f"{role}.not_exists", "target": describe_target(condition.not_exists)})
    for group in ("all", "any"):
        for child in getattr(condition, group, None) or []:
            found.extend(_condition_targets(child, f"{role}.{group}"))
    if getattr(condition, "negate", None) is not None:
        found.extend(_condition_targets(condition.negate, f"{role}.not"))
    return found


def describe_action_targets(action) -> list[dict[str, Any]]:
    """Every target an action refers to, with its role (target, src, dst, verify.*, condition.*)."""
    found: list[dict[str, Any]] = []
    for role in ("target", "src", "dst"):
        target = getattr(action, role, None)
        if target is not None and attrs.has(type(target)):
            found.append({"role": role, "target": describe_target(target)})
    verify = getattr(action, "verify", None)
    if verify is not None:
        for name in ("exists", "not_exists"):
            if getattr(verify, name, None) is not None:
                found.append({"role": f"verify.{name}", "target": describe_target(getattr(verify, name))})
    found.extend(_condition_targets(getattr(action, "condition", None)))
    for cond in getattr(action, "when", None) or []:
        found.append(
            {
                "role": f"when.{type(cond).__name__.replace('Condition', '').lower()}",
                "target": {k: v for k, v in (("text", cond.text), ("image", cond.image)) if v},
            }
        )
    return found


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _write_png(path: Path, screenshot_base64: str | None) -> bool:
    if not screenshot_base64:
        return False
    try:
        path.write_bytes(base64.b64decode(screenshot_base64))
        return True
    except (OSError, ValueError, binascii.Error) as exc:
        log.warning(f"Could not write failure screenshot {path}: {exc}")
        return False


async def collect_failure_evidence(
    *, run_dir: Path | None, action_index: int, action, result, target_resolution
) -> dict[str, Any] | None:
    """Write the failure evidence for ``action`` (1-based ``action_index``). Returns the record, or None."""
    if not evidence_enabled():
        return None
    if run_dir is None:
        log.warning("Failure evidence skipped: no run directory")
        return None
    try:
        out_dir = Path(run_dir) / "reporting" / FAILURE_DIRNAME
        out_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"a{action_index:02d}"
        record: dict[str, Any] = {
            "action_index": action_index,
            "action_type": type(action).__name__,
            "description": getattr(action, "description", "") or "",
            "message": getattr(result, "message", ""),
            "coordinates": getattr(result, "coordinates", None),
            "targets": describe_action_targets(action),
            "last_resolved_target": describe_target(getattr(target_resolution, "last_target", None)),
            "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "files": {},
        }

        last_search = getattr(target_resolution, "last_screenshot_base64", None)
        if _write_png(out_dir / f"{prefix}_last_search.png", last_search):
            record["files"]["last_search_screenshot"] = f"{prefix}_last_search.png"

        fresh = None
        try:
            fresh = await target_resolution.get_current_screenshot()
        except Exception as exc:  # noqa: BLE001 - evidence is best effort
            record["screenshot_error"] = str(exc)
        if fresh and fresh != last_search and _write_png(out_dir / f"{prefix}_screen.png", fresh):
            record["files"]["screenshot"] = f"{prefix}_screen.png"
        screen_for_ocr = fresh or last_search

        resolver = getattr(target_resolution, "target_resolver", None)
        if screen_for_ocr and resolver is not None and hasattr(resolver, "dump_all_text"):
            try:
                ocr = await asyncio.wait_for(resolver.dump_all_text(screen_for_ocr), OCR_TIMEOUT_SECONDS)
                if ocr is not None:
                    (out_dir / f"{prefix}_ocr.json").write_text(json.dumps(_json_safe(ocr), indent=2))
                    record["files"]["ocr"] = f"{prefix}_ocr.json"
                else:
                    record["ocr_error"] = "OCR dump returned nothing"
            except Exception as exc:  # noqa: BLE001
                record["ocr_error"] = f"{type(exc).__name__}: {exc}"

        (out_dir / f"{prefix}_failure.json").write_text(json.dumps(_json_safe(record), indent=2))
        log.info(f"Failure evidence for action {action_index} written to {out_dir}")
        return record
    except Exception as exc:  # noqa: BLE001
        log.error(f"Could not collect failure evidence for action {action_index}: {exc}", exc_info=True)
        return None
