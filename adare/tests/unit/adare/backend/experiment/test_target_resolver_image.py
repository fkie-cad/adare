"""Image targets: offset ``base`` honoured, floor filter, ``min_margin`` (T2F gaps G4/G5).

The CV server is replaced by a fake MCP client, so these tests need no VM and no OpenCV.
"""

import base64
import io
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from PIL import Image

from adare.backend.experiment import target_resolver as tr
from adare.backend.experiment.execution.target_resolution import TargetResolutionExecutor
from adare.types.playbook import (
    Offset,
    SweepStrategy,
    Target,
    TopLeftStrategy,
)

SCREEN_B64 = base64.b64encode(b"not-an-image").decode()


def _fake_client(find_icon_result):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def call_tool(self, name, params):
            assert name == "find_icon"
            return SimpleNamespace(data=find_icon_result, content=[])

    return FakeClient


def _resolver(tmp_path, monkeypatch, find_icon_result, *, size=(20, 10), floor=0.7):
    img_dir = tmp_path / "img"
    img_dir.mkdir()
    Image.new("RGB", size, (255, 0, 0)).save(img_dir / "btn.png")
    monkeypatch.setattr(tr, "Client", _fake_client(find_icon_result))
    return tr.MCPTargetResolver(tmp_path, confidence_floor=floor)


@pytest.mark.asyncio
async def test_default_center_is_unchanged_and_has_no_region(tmp_path, monkeypatch):
    resolver = _resolver(tmp_path, monkeypatch, {"locations": [[100, 50]], "similarities": [0.95]})
    match = await resolver.resolve_target(Target(image="btn.png"), SCREEN_B64)
    assert match.coordinates == (100, 50)
    assert match.region is None  # byte-identical to the behaviour before G4


@pytest.mark.asyncio
async def test_center_offset_base_has_no_region(tmp_path, monkeypatch):
    resolver = _resolver(tmp_path, monkeypatch, {"locations": [[100, 50]], "similarities": [0.95]})
    target = Target(image="btn.png", offset=Offset(x=3, y=4, base="center"))
    match = await resolver.resolve_target(target, SCREEN_B64)
    assert match.region is None


@pytest.mark.asyncio
async def test_top_left_base_uses_server_size(tmp_path, monkeypatch):
    result = {"locations": [[100, 50]], "similarities": [0.95], "sizes": [[40, 20]]}
    resolver = _resolver(tmp_path, monkeypatch, result)
    target = Target(image="btn.png", offset=Offset(base="top-left"))
    match = await resolver.resolve_target(target, SCREEN_B64)
    assert match.region == (80, 40, 40, 20)


@pytest.mark.asyncio
async def test_non_center_base_falls_back_to_template_size(tmp_path, monkeypatch):
    resolver = _resolver(tmp_path, monkeypatch, {"locations": [[100, 50]], "similarities": [0.95]}, size=(20, 10))
    target = Target(image="btn.png", offset=Offset(base="bottom-right"))
    match = await resolver.resolve_target(target, SCREEN_B64)
    assert match.region == (90, 45, 20, 10)


def _final_point(match, offset):
    """Apply the offset exactly as TargetResolutionExecutor does."""
    executor = TargetResolutionExecutor(None, None)
    target = Target(image="btn.png", offset=offset)
    return executor._process_match_result(target, match, None, 0.0, None, "id", None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base,expected",
    [
        ("top-left", (90 + 5, 45 + 6)),
        ("top-right", (110 + 5, 45 + 6)),
        ("bottom-left", (90 + 5, 55 + 6)),
        ("bottom-right", (110 + 5, 55 + 6)),
        ("center-left", (90 + 5, 50 + 6)),
        ("center-right", (110 + 5, 50 + 6)),
        ("top-center", (100 + 5, 45 + 6)),
        ("bottom-center", (100 + 5, 55 + 6)),
        ("center", (105, 56)),
    ],
)
async def test_offset_base_end_to_end(tmp_path, monkeypatch, base, expected):
    resolver = _resolver(tmp_path, monkeypatch, {"locations": [[100, 50]], "similarities": [0.95]}, size=(20, 10))
    offset = Offset(x=5, y=6, base=base)
    match = await resolver.resolve_target(Target(image="btn.png", offset=offset), SCREEN_B64)
    assert _final_point(match, offset) == expected


@pytest.mark.asyncio
async def test_candidates_below_floor_are_dropped_before_strategy(tmp_path, monkeypatch):
    # TopLeft would pick the weak candidate at y=10; with the floor filter it picks the strong one.
    result = {"locations": [[10, 10], [200, 200]], "similarities": [0.55, 0.9]}
    resolver = _resolver(tmp_path, monkeypatch, result)
    match = await resolver.resolve_target(Target(image="btn.png", strategy=TopLeftStrategy()), SCREEN_B64)
    assert match.coordinates == (200, 200)


@pytest.mark.asyncio
async def test_only_weak_candidates_returns_none(tmp_path, monkeypatch):
    resolver = _resolver(tmp_path, monkeypatch, {"locations": [[10, 10]], "similarities": [0.65]})
    assert await resolver.resolve_target(Target(image="btn.png"), SCREEN_B64) is None


@pytest.mark.asyncio
async def test_sweep_index_counts_only_above_floor(tmp_path, monkeypatch):
    result = {"locations": [[10, 10], [20, 20], [30, 30]], "similarities": [0.5, 0.9, 0.8]}
    resolver = _resolver(tmp_path, monkeypatch, result)
    match = await resolver.resolve_target(Target(image="btn.png", strategy=SweepStrategy(index=0)), SCREEN_B64)
    assert match.coordinates == (20, 20)


@pytest.mark.asyncio
async def test_min_margin_rejects_a_close_runner_up(tmp_path, monkeypatch):
    result = {"locations": [[10, 10], [200, 200]], "similarities": [0.90, 0.88]}
    resolver = _resolver(tmp_path, monkeypatch, result)
    assert await resolver.resolve_target(Target(image="btn.png", min_margin=0.05), SCREEN_B64) is None


@pytest.mark.asyncio
async def test_min_margin_accepts_a_clear_winner(tmp_path, monkeypatch):
    result = {"locations": [[10, 10], [200, 200]], "similarities": [0.95, 0.75]}
    resolver = _resolver(tmp_path, monkeypatch, result)
    match = await resolver.resolve_target(Target(image="btn.png", min_margin=0.1), SCREEN_B64)
    assert match.coordinates == (10, 10)


@pytest.mark.asyncio
async def test_min_margin_ignores_below_floor_runner_up(tmp_path, monkeypatch):
    # The 0.69 candidate is under the floor, so it is not a runner-up.
    result = {"locations": [[10, 10], [200, 200]], "similarities": [0.72, 0.69]}
    resolver = _resolver(tmp_path, monkeypatch, result)
    match = await resolver.resolve_target(Target(image="btn.png", min_margin=0.1), SCREEN_B64)
    assert match.coordinates == (10, 10)


@pytest.mark.asyncio
async def test_min_margin_single_candidate_passes(tmp_path, monkeypatch):
    resolver = _resolver(tmp_path, monkeypatch, {"locations": [[10, 10]], "similarities": [0.8]})
    match = await resolver.resolve_target(Target(image="btn.png", min_margin=0.5), SCREEN_B64)
    assert match is not None


@pytest.mark.asyncio
async def test_without_min_margin_close_runner_up_is_accepted(tmp_path, monkeypatch):
    result = {"locations": [[10, 10], [200, 200]], "similarities": [0.90, 0.89]}
    resolver = _resolver(tmp_path, monkeypatch, result)
    match = await resolver.resolve_target(Target(image="btn.png"), SCREEN_B64)
    assert match.coordinates == (10, 10)


def test_min_margin_validated():
    with pytest.raises(ValueError):
        Target(image="x.png", min_margin=1.5)


def test_min_margin_round_trips_through_the_database_json():
    from adare.database.api.playbook import PlaybookApi

    api = PlaybookApi.__new__(PlaybookApi)
    target = Target(image="x.png", min_margin=0.07, offset=Offset(base="top-left"))
    restored = api._json_to_target(api._target_to_json(target))
    assert restored.min_margin == 0.07
    assert restored.offset.base == "top-left"
