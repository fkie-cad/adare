"""Port forwards bind to loopback unless ADARE_FORWARD_BIND says otherwise."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from adare.hypervisor import port_forward

pytestmark = pytest.mark.unit


@pytest.fixture
def no_bind_env(monkeypatch):
    monkeypatch.delenv(port_forward.FORWARD_BIND_ENV_VAR, raising=False)


@pytest.mark.usefixtures('no_bind_env')
def test_defaults_to_loopback():
    assert port_forward.forward_bind_host() == '127.0.0.1'
    assert port_forward.forward_connect_host() == '127.0.0.1'


@pytest.mark.parametrize(
    ('env', 'bind', 'connect'),
    [
        ('10.0.0.5', '10.0.0.5', '10.0.0.5'),
        ('0.0.0.0', '0.0.0.0', '127.0.0.1'),
        ('::', '::', '127.0.0.1'),
        ('  ', '127.0.0.1', '127.0.0.1'),
    ],
)
def test_env_override(monkeypatch, env, bind, connect):
    monkeypatch.setenv(port_forward.FORWARD_BIND_ENV_VAR, env)
    assert port_forward.forward_bind_host() == bind
    assert port_forward.forward_connect_host() == connect


@pytest.mark.usefixtures('no_bind_env')
def test_qemu_hostfwd_fills_missing_host_ip():
    assert port_forward.qemu_hostfwd('tcp', 40000, 18765) == 'tcp:127.0.0.1:40000-:18765'
    assert port_forward.qemu_hostfwd('udp', 1, 2, '192.168.1.2', '10.0.2.15') == 'udp:192.168.1.2:1-10.0.2.15:2'


def _context(port=40123):
    vm = SimpleNamespace(
        remove_port_forwarding=AsyncMock(return_value=0), add_port_forwarding=AsyncMock(return_value=0)
    )
    return SimpleNamespace(vm=vm, config=SimpleNamespace(websocket_port=port), user_interrupt_event=None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('module', 'cls_name'),
    [
        ('adare.hypervisor.qemu.lifecycle', 'QEMULifecycleStrategy'),
        ('adare.hypervisor.virtualbox.lifecycle', 'VirtualBoxLifecycleStrategy'),
    ],
)
@pytest.mark.parametrize(('env', 'expected'), [(None, '127.0.0.1'), ('10.0.0.5', '10.0.0.5')])
async def test_lifecycle_agent_forward_binds_host(monkeypatch, module, cls_name, env, expected):
    import importlib

    if env is None:
        monkeypatch.delenv(port_forward.FORWARD_BIND_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(port_forward.FORWARD_BIND_ENV_VAR, env)
    strategy_cls = getattr(importlib.import_module(module), cls_name)
    strategy = strategy_cls.__new__(strategy_cls)  # setup_networking needs no constructor state
    ctx = _context()

    await strategy.setup_networking(ctx)

    kwargs = ctx.vm.add_port_forwarding.await_args.kwargs
    assert kwargs['host_ip'] == expected
    assert kwargs['host_port'] == 40123
    assert kwargs['guest_port'] == 18765


def test_vbox_rule_string_carries_host_ip():
    from adare.hypervisor.virtualbox.models import PortForwardingRule

    rule = PortForwardingRule(
        name='adarevm', protocol='tcp', host_ip='127.0.0.1', host_port=40123, guest_ip='', guest_port=18765
    )
    assert rule.to_vbox_format() == 'adarevm,tcp,127.0.0.1,40123,,18765'


@pytest.mark.usefixtures('no_bind_env')
def test_agent_client_defaults_to_connect_host(monkeypatch):
    from adare.backend.experiment.websocket_client import AdareVMClient

    assert AdareVMClient(port=40123).server_url == 'ws://127.0.0.1:40123'
    monkeypatch.setenv(port_forward.FORWARD_BIND_ENV_VAR, '10.0.0.5')
    assert AdareVMClient(port=40123).server_url == 'ws://10.0.0.5:40123'
