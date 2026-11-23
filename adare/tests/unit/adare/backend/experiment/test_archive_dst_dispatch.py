"""The mapping form of ``dst`` reaches every executor as its string form."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.backend.experiment.execution.test_actions import TestActionsExecutor
from adarelib.constants import StatusEnum

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_vm_side_test_gets_string_dst():
    executor = TestActionsExecutor()
    loader = MagicMock()
    loader.resolve_test_with_runtime_context = AsyncMock(
        return_value={
            'name': 'cfg',
            'function': 'json.value_matches',
            'parameter': {'dst': {'archive': '/home/u/backup.tar.gz', 'member': 'etc/app.json'}, 'key_path': 'a'},
        }
    )
    loader.get_test_class.return_value = None
    executor.set_test_loader(loader)
    websocket = MagicMock()
    websocket.run_test = AsyncMock(
        return_value={'status': 'success', 'result': {'status': StatusEnum.SUCCESS, 'details': []}}
    )
    action = MagicMock()
    action.name = 'cfg'
    action.timeout = None

    await executor.execute_test(action, websocket, target_resolver=MagicMock())

    sent = websocket.run_test.await_args.args[1]
    assert sent['parameter'] == {'dst': '/home/u/backup.tar.gz!/etc/app.json', 'key_path': 'a'}
