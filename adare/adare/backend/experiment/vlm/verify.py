"""End-of-run acceptance checks for a GUI-automated install (Phase 3b).

After the installed disk is booted (CDROM detached), these checks confirm the
result matches the requested outcome. Visual checks use the vision model on a
screenshot of the booted system; structural checks use cheap, always-available
signals (domain state, disk growth) and degrade gracefully when a richer probe
(guest agent) is not reachable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..execution.qemu_host_gui_executor import QEMUHostGUIExecutor
from .actions import _extract_json_object
from .client import VLMClient
from .exceptions import VLMError

log = logging.getLogger(__name__)


@dataclass
class CheckResult:
    passed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, kind: str, passed: bool, reason: str) -> None:
        self.checks.append({'name': name, 'kind': kind, 'passed': passed, 'reason': reason})

    def to_markdown(self) -> str:
        lines = ['## Acceptance checks', '',
                 f'**Overall:** {"PASS" if self.passed else "FAIL"}', '']
        for c in self.checks:
            mark = '✅' if c['passed'] else '❌'
            lines.append(f'- {mark} [{c["kind"]}] {c["name"]}: {c["reason"]}')
        return '\n'.join(lines) + '\n'


async def _visual_check(
    executor: QEMUHostGUIExecutor,
    client: VLMClient,
    statement: str,
) -> tuple[bool, str]:
    shot = await executor.screenshot()
    if shot.get('status') != 'success':
        return False, f'screenshot failed: {shot.get("message")}'
    image = shot.get('image')
    b64 = image.get('data') if isinstance(image, dict) else shot.get('screenshot')
    if not b64:
        return False, 'no screenshot image data'

    prompt = (
        f'Look at the screenshot and decide whether this is TRUE: "{statement}".\n'
        'Reply with a single JSON object: {"pass": true|false, "reason": "<short>"}'
    )
    messages = [{'role': 'user', 'content': [
        client.text_content(prompt), client.image_content(b64)]}]
    try:
        reply = await client.chat(messages, temperature=0.0, max_tokens=200)
        obj = _extract_json_object(reply)
    except VLMError as exc:
        return False, f'model check failed: {exc}'
    return bool(obj.get('pass')), str(obj.get('reason', ''))


def _structural_checks(vm, spec: dict[str, Any], disk_path: Path | None, result: CheckResult) -> None:
    # Domain must be running (booted the installed disk).
    try:
        state = vm.get_state()
    except (OSError, RuntimeError) as exc:
        result.add('vm_running', 'structural', False, f'get_state failed: {exc}')
    else:
        result.add('vm_running', 'structural', state == 'running',
                   f'domain state = {state}')

    # Disk must have grown past a floor (installer actually wrote data).
    min_bytes = spec.get('min_disk_bytes')
    if min_bytes and disk_path is not None:
        try:
            size = Path(disk_path).stat().st_size
        except OSError as exc:
            result.add('disk_grew', 'structural', False, f'stat failed: {exc}')
        else:
            result.add('disk_grew', 'structural', size >= int(min_bytes),
                       f'disk size {size} bytes (floor {int(min_bytes)})')


async def run_acceptance_checks(
    vm,
    acceptance_spec: dict[str, Any],
    *,
    client: VLMClient | None = None,
    disk_path: str | Path | None = None,
    run_dir: str | Path | None = None,
) -> CheckResult:
    """Run structural + visual acceptance checks; return an overall result.

    ``acceptance_spec`` shape::

        visual: ["a KDE/SDDM login for user adare is shown", ...]
        min_disk_bytes: 5000000000
    """
    result = CheckResult(passed=True)
    disk = Path(disk_path) if disk_path else None

    _structural_checks(vm, acceptance_spec, disk, result)

    visual = acceptance_spec.get('visual') or []
    if visual:
        if client is None:
            result.add('visual', 'visual', False,
                       'no vLLM client available for visual acceptance checks')
        else:
            executor = QEMUHostGUIExecutor(vm=vm)
            for statement in visual:
                passed, reason = await _visual_check(executor, client, str(statement))
                result.add(str(statement), 'visual', passed, reason)

    result.passed = all(c['passed'] for c in result.checks) if result.checks else False

    if run_dir:
        report = Path(run_dir) / 'acceptance.md'
        report.write_text(result.to_markdown())

    return result
