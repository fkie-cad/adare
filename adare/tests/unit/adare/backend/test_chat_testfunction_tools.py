"""Chat/MCP control-plane testfunction tools: catalog-backed, compact, with fix hints on errors."""

import pytest

from adare.backend.chat.tools import build_tools, call_tool
from adare.backend.testfunction import catalog

pytestmark = pytest.mark.unit


@pytest.fixture()
def tools(tmp_path, monkeypatch):
    root = tmp_path / 'tf' / 'demo'
    root.mkdir(parents=True)
    (root / 'demo.py').write_text(
        "@testfunction(name='file_exists', description='tests if file exists')\n"
        "def file_exists(ctx, dst: str):\n    pass\n\n"
        "@testfunction(name='file_does_not_exist', description='tests if file does NOT exist')\n"
        "def file_does_not_exist(ctx, dst: str):\n    pass\n")
    monkeypatch.setattr(catalog, 'default_sources', lambda: [(tmp_path / 'tf', True)])
    return {t.name: t for t in build_tools(api=object())}


def test_list_is_compact(tools):
    result = call_tool(tools['testfunction_list'], {})
    assert result['ok'] and [e['dotnotation'] for e in result['data']] == ['demo.file_does_not_exist',
                                                                           'demo.file_exists']
    assert 'example' not in result['data'][0]


def test_search_ranks_goal_and_includes_example(tools):
    result = call_tool(tools['testfunction_search'], {'query': 'the file was deleted', 'limit': 1})
    assert [e['dotnotation'] for e in result['data']] == ['demo.file_does_not_exist']
    assert result['data'][0]['example']['parameter'] == {'dst': '<str>'}


def test_info_unknown_returns_error_envelope_with_suggestions(tools):
    result = call_tool(tools['testfunction_info'], {'dotnotation': 'demo.file_exsts'})
    assert not result['ok'] and result['error']['code'] == 'TestFunctionNotFoundError'
    assert any('demo.file_exists' in s for s in result['error']['solutions'])
