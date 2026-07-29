"""Tests for the GUI-automation MCP server (``adare dev mcp``).

These run with no VM, no CV server, and no external harness: the GUI executor
and CV resolver are fakes. They assert:

- a ``click`` while recording appends a ClickAction and crops the cached
  screenshot into an ``image:`` target,
- ``add_test`` validates the function against the catalog (dropping unknowns),
- ``save_playbook`` writes a ``parse_playbook``-valid playbook carrying GUI
  actions **and** a ``tests:`` block **and** a ``- test:`` action,
- ``list_testfunctions`` / catalog shaping from structured-data-shaped input,
- ``run_playbook`` wires through to the deterministic replay engine,
- an in-memory MCP client can drive the tools end-to-end (integration).
"""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from adare.backend.experiment.target_resolver import TargetMatch
from adare.backend.experiment.vlm.mcp_server import GuiMcpServer
from adare.services.devmode.mcp_serving import shape_testfunction_catalog
from adare.types.playbook import ActionTestAction, ClickAction, parse_playbook

pytestmark = pytest.mark.unit


def _png_bytes(color=(30, 30, 40), w=1280, h=800) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', (w, h), color).save(buf, format='PNG')
    return buf.getvalue()


def _png_b64(**kw) -> str:
    return base64.b64encode(_png_bytes(**kw)).decode()


class _FakeExecutor:
    """Fake QEMUHostGUIExecutor: records calls, returns success dicts."""

    def __init__(self):
        self.n = 0
        self.clicks = []
        self.keys = []
        self.scrolls = []
        self.vm = object()  # run_playbook reads executor.vm

    async def screenshot(self, region=None):
        self.n += 1
        shade = min(255, 30 + self.n * 5)
        return {'status': 'success',
                'image': {'data': _png_b64(color=(shade, shade, shade)), 'format': 'png'}}

    async def click(self, x, y, button_type='left'):
        self.clicks.append((x, y, button_type))
        return {'status': 'success'}

    async def keyboard(self, action_type, value):
        self.keys.append((action_type, value))
        return {'status': 'success'}

    async def scroll(self, direction, amount):
        self.scrolls.append((direction, amount))
        return {'status': 'success'}


class _FakeResolver:
    """Fake MCPTargetResolver: returns a fixed match; tracks images_dir."""

    def __init__(self, match=None):
        self.images_dir = None
        self._match = match

    async def resolve_target(self, target, screenshot_base64=None, offset_x=0, offset_y=0):
        return self._match


class _TF:
    """Structured-data-shaped testfunction (mirrors TestFunctionInfo)."""

    def __init__(self, name, dotnotation, description='', parameters=None, file_name=''):
        self.name = name
        self.dotnotation = dotnotation
        self.description = description
        self.parameters = parameters or []
        self.file_name = file_name
        self.file_path = file_name


def _catalog():
    return shape_testfunction_catalog([
        _TF('file_does_not_exist', 'filesystem.file_does_not_exist',
            'Assert a path is absent',
            [{'name': 'path', 'data_type': 'str', 'required': True}], 'filesystem.py'),
        _TF('file_exists', 'filesystem.file_exists', 'Assert a path is present',
            [{'name': 'path', 'data_type': 'str', 'required': True}], 'filesystem.py'),
    ])


def _server(tmp_path, resolver=None):
    return GuiMcpServer(
        executor=_FakeExecutor(),
        resolver=resolver or _FakeResolver(),
        catalog=_catalog(),
        base_dir=tmp_path,
    )


# ---------------------------------------------------------------------------
# Catalog shaping / list_testfunctions
# ---------------------------------------------------------------------------

def test_shape_catalog_maps_structured_fields():
    catalog = _catalog()
    assert {e['dotnotation'] for e in catalog} == {
        'filesystem.file_does_not_exist', 'filesystem.file_exists'}
    entry = catalog[0]
    assert entry['name'] == 'file_does_not_exist'
    assert entry['category'] == 'filesystem.py'
    assert entry['parameters'][0]['name'] == 'path'


def test_list_testfunctions_returns_catalog(tmp_path):
    server = _server(tmp_path)
    got = server.list_testfunctions()
    assert {e['dotnotation'] for e in got} == {
        'filesystem.file_does_not_exist', 'filesystem.file_exists'}


# ---------------------------------------------------------------------------
# Recording: click auto-crops
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_click_while_recording_appends_and_crops(tmp_path):
    server = _server(tmp_path)
    server.start_recording(goal='delete a file')
    await server.screenshot()  # caches the pre-click screenshot
    await server.click(640, 400, describe='trash icon')

    recorder = server._recorder
    assert recorder.action_count == 1
    crops = list(recorder.img_dir.glob('*.png'))
    assert len(crops) == 1  # the click cropped an image target
    action = recorder._actions[0]
    assert 'click' in action
    assert action['click']['target']['image'] == crops[0].name
    assert action['click']['description'] == 'trash icon'
    # find_icon points the resolver at this recording's crops
    assert server._resolver.images_dir == recorder.img_dir


@pytest.mark.asyncio
async def test_click_without_prior_screenshot_still_crops(tmp_path):
    server = _server(tmp_path)
    server.start_recording()
    await server.click(10, 10, describe='corner')  # no screenshot() first
    assert server._recorder.action_count == 1
    assert list(server._recorder.img_dir.glob('*.png'))


# ---------------------------------------------------------------------------
# add_test validation against the catalog
# ---------------------------------------------------------------------------

def test_add_test_accepts_known_function(tmp_path):
    server = _server(tmp_path)
    server.start_recording()
    res = server.add_test('verify_gone', 'filesystem.file_does_not_exist',
                          parameters={'path': '/home/user/testfile.txt'},
                          description='file removed')
    assert res['status'] == 'success'
    assert server._recorder._tests == [{
        'name': 'verify_gone',
        'function': 'filesystem.file_does_not_exist',
        'description': 'file removed',
        'parameter': {'path': '/home/user/testfile.txt'},
    }]
    # also appended a `- test:` action to run it in sequence
    assert {'test': {'name': 'verify_gone', 'description': 'file removed'}} in server._recorder._actions


def test_add_test_rejects_unknown_function(tmp_path):
    server = _server(tmp_path)
    server.start_recording()
    res = server.add_test('bogus', 'not.a.real.function')
    assert res['status'] == 'error'
    assert server._recorder._tests == []
    assert server._recorder._actions == []


def test_add_test_requires_recording(tmp_path):
    server = _server(tmp_path)
    res = server.add_test('x', 'filesystem.file_exists')
    assert res['status'] == 'error'


# ---------------------------------------------------------------------------
# save_playbook -> parse_playbook-valid playbook with actions + tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_playbook_is_parseable_with_actions_and_tests(tmp_path):
    server = _server(tmp_path)
    server.start_recording(goal='delete a file and verify it is gone')
    await server.screenshot()
    await server.click(500, 300, describe='testfile.txt')
    await server.key('Delete', describe='delete key')
    server.add_variable('target', '/home/user/testfile.txt')
    server.add_test('verify_gone', 'filesystem.file_does_not_exist',
                    parameters={'path': '{{ target }}'}, description='file removed')

    out = tmp_path / 'saved' / 'delete_file.play.yaml'
    res = server.save_playbook(out)
    assert res['status'] == 'success'
    assert out.exists()
    # crops carried alongside so relative img/ references resolve
    assert (out.parent / 'img').is_dir()
    assert list((out.parent / 'img').glob('*.png'))

    playbook = parse_playbook(out)
    kinds = [type(a).__name__ for a in playbook.actions]
    assert 'ClickAction' in kinds
    assert 'ActionTestAction' in kinds
    click = next(a for a in playbook.actions if isinstance(a, ClickAction))
    assert click.target.image  # image-targeted for CV replay
    test_action = next(a for a in playbook.actions if isinstance(a, ActionTestAction))
    assert test_action.name == 'verify_gone'
    # top-level tests: block defines the assertion
    assert len(playbook.tests) == 1
    assert playbook.tests[0].name == 'verify_gone'
    assert playbook.tests[0].function == 'filesystem.file_does_not_exist'
    # variables: block for parameterized replay
    assert playbook.variables is not None


# ---------------------------------------------------------------------------
# Grounding aids
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_text_returns_coordinates(tmp_path):
    match = TargetMatch(coordinates=(120, 240), confidence=0.91, method='text')
    server = _server(tmp_path, resolver=_FakeResolver(match=match))
    res = await server.find_text('Trash')
    assert res == {'status': 'success', 'x': 120, 'y': 240,
                   'confidence': pytest.approx(0.91), 'method': 'text'}


@pytest.mark.asyncio
async def test_find_icon_not_found(tmp_path):
    server = _server(tmp_path, resolver=_FakeResolver(match=None))
    res = await server.find_icon('missing.png')
    assert res == {'status': 'not_found'}


# ---------------------------------------------------------------------------
# run_playbook wiring (no real VM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_playbook_wires_to_replay(tmp_path, monkeypatch):
    from adare.backend.experiment.vlm import replay as replay_mod

    seen = {}

    async def _fake_run_playbook(vm, path, *, mcp_gui_url, os_key):
        seen['vm'] = vm
        seen['path'] = path
        seen['cv_url'] = mcp_gui_url
        return replay_mod.ReplayResult(success=True, total=3, executed=3)

    monkeypatch.setattr(replay_mod, 'run_playbook', _fake_run_playbook)
    server = _server(tmp_path)
    res = await server.run_playbook(tmp_path / 'foo.play.yaml')
    assert res['success'] is True
    assert res['total'] == 3 and res['executed'] == 3
    assert seen['cv_url'] == server._cv_url
    assert seen['vm'] is server._executor.vm


# ---------------------------------------------------------------------------
# Integration: drive the tools via an in-memory MCP client
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_in_memory_mcp_client_records_and_parses(tmp_path):
    from fastmcp import Client

    server = _server(tmp_path)
    out = tmp_path / 'authored' / 'trivial.play.yaml'

    async with Client(server.mcp) as client:
        tools = {t.name for t in await client.list_tools()}
        assert {'screenshot', 'click', 'type', 'key', 'list_testfunctions',
                'start_recording', 'add_test', 'save_playbook', 'run_playbook'} <= tools

        await client.call_tool('start_recording', {'goal': 'delete a file and verify'})
        await client.call_tool('screenshot', {})
        await client.call_tool('click', {'x': 500, 'y': 300, 'describe': 'testfile.txt'})
        await client.call_tool('key', {'combo': 'Delete', 'describe': 'delete'})
        await client.call_tool('add_test', {
            'name': 'verify_gone',
            'function': 'filesystem.file_does_not_exist',
            'parameters': {'path': '/home/user/testfile.txt'},
            'description': 'file removed',
        })
        await client.call_tool('save_playbook', {'path': str(out)})

    assert out.exists()
    playbook = parse_playbook(out)
    assert any(isinstance(a, ClickAction) for a in playbook.actions)
    assert any(isinstance(a, ActionTestAction) for a in playbook.actions)
    assert playbook.tests and playbook.tests[0].function == 'filesystem.file_does_not_exist'


@pytest.mark.integration
@pytest.mark.asyncio
async def test_screenshot_tool_yields_image_block(tmp_path):
    """The ``screenshot`` *tool* returns a real image block (not a base64 text
    blob), so a vision harness actually sees the screen.
    """
    from fastmcp import Client
    from mcp.types import ImageContent

    server = _server(tmp_path)
    async with Client(server.mcp) as client:
        result = await client.call_tool('screenshot', {})

    image_blocks = [b for b in result.content if isinstance(b, ImageContent)]
    assert image_blocks, f'expected an image content block, got {[type(b).__name__ for b in result.content]}'
    assert image_blocks[0].mimeType == 'image/png'
    # the internal dict method still caches the PNG for the crop-on-click path
    assert server._last_png is not None
