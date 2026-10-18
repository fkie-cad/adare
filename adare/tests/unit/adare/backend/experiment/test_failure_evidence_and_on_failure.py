"""Evidence on a failed action and the playbook-level ``on_failure:`` list (T2F gap G8).

The controller runs against a fake action executor, so no VM is needed.
"""

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

from adare.backend.experiment import failure_evidence as fe
from adare.backend.experiment.action_executor import ActionResult
from adare.backend.experiment.playbook_controller import PlaybookController
from adare.backend.experiment.vlm.authoring.author_playbook import validate as validate_yaml
from adare.types.playbook import (
    ClickAction,
    ClickVerify,
    IdleAction,
    Playbook,
    Target,
    WaitCondition,
    WaitUntilAction,
    parse_playbook,
)

PNG = base64.b64encode(b"\x89PNG-fake").decode()
PNG2 = base64.b64encode(b"\x89PNG-other").decode()


# --- playbook syntax / validator ---------------------------------------------------


def _write(tmp_path, text):
    path = tmp_path / "playbook.yml"
    path.write_text(text)
    return path


def test_on_failure_parses(tmp_path):
    pb = parse_playbook(
        _write(
            tmp_path,
            """
actions:
  - click:
      target: {text: "File"}
on_failure:
  - screenshot:
      name: failed
  - keyboard:
      combination: [ctrl, q]
""",
        )
    )
    assert [type(a).__name__ for a in pb.on_failure] == ["ScreenshotAction", "KeyboardAction"]


def test_playbook_without_on_failure_is_unchanged(tmp_path):
    pb = parse_playbook(_write(tmp_path, "actions:\n  - idle:\n      duration: 1\n"))
    assert pb.on_failure == []
    assert len(pb.actions) == 1


def test_validate_accepts_on_failure_and_rejects_a_bad_step():
    good = "actions:\n  - idle:\n      duration: 1\non_failure:\n  - idle:\n      duration: 2\n"
    assert validate_yaml(good) == (True, None)
    bad = "actions:\n  - idle:\n      duration: 1\non_failure:\n  - frobnicate: {}\n"
    ok, error = validate_yaml(bad)
    assert not ok


def test_validate_flags_an_undefined_variable_in_on_failure():
    text = "actions:\n  - idle:\n      duration: 1\non_failure:\n  - command:\n      command: \"echo {{ nope }}\"\n"
    ok, error = validate_yaml(text)
    assert not ok
    assert "on_failure step 1" in error


def test_on_failure_may_use_variables_defined_by_main_steps():
    text = (
        "actions:\n  - save_timestamp:\n      variable: t0\n"
        "on_failure:\n  - command:\n      command: \"echo {{ t0 }}\"\n"
    )
    assert validate_yaml(text) == (True, None)


def test_unknown_top_level_key_is_still_rejected():
    ok, _ = validate_yaml("actions:\n  - idle:\n      duration: 1\non_fail:\n  - idle:\n      duration: 1\n")
    assert not ok


def test_on_failure_loads_back_from_the_stored_yaml():
    from adare.database.api.playbook import PlaybookApi

    api = PlaybookApi.__new__(PlaybookApi)
    steps = api._load_on_failure_from_yaml(
        "actions:\n  - idle:\n      duration: 1\non_failure:\n  - idle:\n      duration: 2\n"
    )
    assert isinstance(steps[0], IdleAction) and steps[0].duration == 2
    assert api._load_on_failure_from_yaml("actions:\n  - idle:\n      duration: 1\n") == []
    assert api._load_on_failure_from_yaml(None) == []


# --- evidence ------------------------------------------------------------------------


class FakeTargetResolution:
    def __init__(self, fresh=PNG2, last=PNG, ocr=None, ocr_error=None):
        self.last_screenshot_base64 = last
        self.last_target = Target(text="Organize")
        self.get_current_screenshot = AsyncMock(return_value=fresh)
        self.target_resolver = MagicMock()
        if ocr_error:
            self.target_resolver.dump_all_text = AsyncMock(side_effect=ocr_error)
        else:
            self.target_resolver.dump_all_text = AsyncMock(
                return_value=ocr if ocr is not None else [{"text": "File", "location": {"x": 5, "y": 6}}]
            )


@pytest.mark.asyncio
async def test_evidence_files_are_written(tmp_path):
    action = ClickAction(
        target=Target(text="Library", text_match=None), verify=ClickVerify(exists=Target(text="Organize"))
    )
    result = ActionResult(success=False, message="Could not resolve target")
    record = await fe.collect_failure_evidence(
        run_dir=tmp_path, action_index=7, action=action, result=result, target_resolution=FakeTargetResolution()
    )
    out = tmp_path / "reporting" / "failure"
    assert (out / "a07_last_search.png").read_bytes() == b"\x89PNG-fake"
    assert (out / "a07_screen.png").read_bytes() == b"\x89PNG-other"
    assert json.loads((out / "a07_ocr.json").read_text())[0]["text"] == "File"
    info = json.loads((out / "a07_failure.json").read_text())
    assert info["message"] == "Could not resolve target"
    assert info["action_type"] == "ClickAction"
    roles = {t["role"]: t["target"] for t in info["targets"]}
    assert roles["target"]["text"] == "Library" and roles["verify.exists"]["text"] == "Organize"
    assert info["last_resolved_target"]["text"] == "Organize"
    assert set(record["files"]) == {"last_search_screenshot", "screenshot", "ocr"}


@pytest.mark.asyncio
async def test_identical_screenshots_are_stored_once(tmp_path):
    await fe.collect_failure_evidence(
        run_dir=tmp_path,
        action_index=1,
        action=IdleAction(duration=1),
        result=ActionResult(success=False, message="x"),
        target_resolution=FakeTargetResolution(fresh=PNG, last=PNG),
    )
    out = tmp_path / "reporting" / "failure"
    assert (out / "a01_last_search.png").exists() and not (out / "a01_screen.png").exists()


@pytest.mark.asyncio
async def test_wait_until_conditions_are_described(tmp_path):
    action = WaitUntilAction(
        condition=WaitCondition(
            any=[WaitCondition(exists=Target(image="a.png")), WaitCondition(not_exists=Target(text="Busy"))]
        )
    )
    await fe.collect_failure_evidence(
        run_dir=tmp_path,
        action_index=2,
        action=action,
        result=ActionResult(success=False, message="timeout"),
        target_resolution=FakeTargetResolution(),
    )
    info = json.loads((tmp_path / "reporting" / "failure" / "a02_failure.json").read_text())
    assert {t["role"] for t in info["targets"]} == {"condition.any.exists", "condition.any.not_exists"}


@pytest.mark.asyncio
async def test_ocr_failure_is_recorded_not_raised(tmp_path):
    record = await fe.collect_failure_evidence(
        run_dir=tmp_path,
        action_index=3,
        action=IdleAction(duration=1),
        result=ActionResult(success=False, message="x"),
        target_resolution=FakeTargetResolution(ocr_error=RuntimeError("cv server down")),
    )
    assert "cv server down" in record["ocr_error"]
    assert (tmp_path / "reporting" / "failure" / "a03_failure.json").exists()


@pytest.mark.asyncio
async def test_no_run_dir_or_disabled_does_nothing(tmp_path, monkeypatch):
    kwargs = dict(
        action_index=1,
        action=IdleAction(duration=1),
        result=ActionResult(success=False),
        target_resolution=FakeTargetResolution(),
    )
    assert await fe.collect_failure_evidence(run_dir=None, **kwargs) is None
    monkeypatch.setenv("ADARE_FAILURE_EVIDENCE", "0")
    assert await fe.collect_failure_evidence(run_dir=tmp_path, **kwargs) is None
    assert not (tmp_path / "reporting").exists()


@pytest.mark.asyncio
async def test_screenshot_error_still_writes_the_json(tmp_path):
    resolution = FakeTargetResolution()
    resolution.get_current_screenshot = AsyncMock(side_effect=RuntimeError("no screen"))
    record = await fe.collect_failure_evidence(
        run_dir=tmp_path,
        action_index=4,
        action=IdleAction(duration=1),
        result=ActionResult(success=False, message="x"),
        target_resolution=resolution,
    )
    assert record["screenshot_error"] == "no screen"
    assert "screenshot" not in record["files"]


# --- controller ------------------------------------------------------------------------


def _controller(tmp_path, playbook, results):
    """A controller whose executor returns the scripted ActionResults, in call order."""
    controller = PlaybookController(websocket_client=AsyncMock(), playbook=playbook, experiment_run_directory=tmp_path)
    calls = []

    async def execute_action(action, **kwargs):
        calls.append(action)
        return results.pop(0)

    controller.action_executor = SimpleNamespace(
        execute_action=execute_action,
        target_resolution=FakeTargetResolution(),
        debug_screenshots=False,
        clock=MagicMock(),
    )
    controller.client.idle = AsyncMock()
    return controller, calls


def _pb(n_main, on_failure):
    return Playbook(actions=[IdleAction(duration=i + 1) for i in range(n_main)], on_failure=on_failure)


@pytest.mark.asyncio
async def test_on_failure_runs_after_a_failed_action_and_keeps_failed_status(tmp_path):
    pb = _pb(3, [IdleAction(duration=100), IdleAction(duration=101)])
    ok, bad = ActionResult(success=True, message="ok"), ActionResult(success=False, message="Could not resolve")
    controller, calls = _controller(tmp_path, pb, [ok, bad, ActionResult(success=True), ActionResult(success=True)])
    outcome = await controller.execute_playbook()
    assert [a.duration for a in calls] == [1, 2, 100, 101]  # action 3 never ran, both recovery steps did
    assert outcome.success is False
    assert outcome.total_actions == 3 and outcome.failed_actions == 1 and outcome.successful_actions == 1
    assert len(outcome.on_failure_results) == 2 and all(r.success for r in outcome.on_failure_results)
    assert (tmp_path / "reporting" / "failure" / "a02_failure.json").exists()


@pytest.mark.asyncio
async def test_a_failing_on_failure_step_does_not_stop_the_rest_or_change_status(tmp_path):
    pb = _pb(1, [IdleAction(duration=100), IdleAction(duration=101)])
    controller, calls = _controller(
        tmp_path,
        pb,
        [
            ActionResult(success=False, message="boom"),
            ActionResult(success=False, message="x"),
            ActionResult(success=True),
        ],
    )
    outcome = await controller.execute_playbook()
    assert [a.duration for a in calls] == [1, 100, 101]
    assert outcome.success is False and outcome.failed_actions == 1
    assert [r.success for r in outcome.on_failure_results] == [False, True]


@pytest.mark.asyncio
async def test_an_exception_in_an_on_failure_step_is_contained(tmp_path):
    pb = _pb(1, [IdleAction(duration=100), IdleAction(duration=101)])
    controller, calls = _controller(tmp_path, pb, [ActionResult(success=False, message="boom")])

    async def execute_action(action, **kwargs):
        calls.append(action)
        if action.duration == 100:
            raise RuntimeError("guest gone")
        if action.duration == 101:
            return ActionResult(success=True)
        return ActionResult(success=False, message="boom")

    controller.action_executor.execute_action = execute_action
    outcome = await controller.execute_playbook()
    assert [r.success for r in outcome.on_failure_results] == [False, True]
    assert "guest gone" in outcome.on_failure_results[0].message


@pytest.mark.asyncio
async def test_on_failure_does_not_run_on_success(tmp_path):
    pb = _pb(2, [IdleAction(duration=100)])
    controller, calls = _controller(tmp_path, pb, [ActionResult(success=True), ActionResult(success=True)])
    outcome = await controller.execute_playbook()
    assert [a.duration for a in calls] == [1, 2]
    assert outcome.success and outcome.on_failure_results == []
    assert not (tmp_path / "reporting" / "failure").exists()


@pytest.mark.asyncio
async def test_failure_without_on_failure_behaves_as_before(tmp_path):
    pb = _pb(3, [])
    controller, calls = _controller(
        tmp_path, pb, [ActionResult(success=True), ActionResult(success=False, message="x")]
    )
    outcome = await controller.execute_playbook()
    assert [a.duration for a in calls] == [1, 2]
    assert outcome.success is False and outcome.failed_actions == 1 and outcome.on_failure_results == []
    assert (tmp_path / "reporting" / "failure" / "a02_failure.json").exists()  # evidence is always collected


@pytest.mark.asyncio
async def test_evidence_failure_cannot_break_the_run(tmp_path, monkeypatch):
    pb = _pb(2, [IdleAction(duration=100)])
    controller, calls = _controller(
        tmp_path, pb, [ActionResult(success=False, message="x"), ActionResult(success=True)]
    )

    async def explode(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(fe, "collect_failure_evidence", explode)
    outcome = await controller.execute_playbook()
    assert outcome.success is False and [a.duration for a in calls] == [1, 100]
