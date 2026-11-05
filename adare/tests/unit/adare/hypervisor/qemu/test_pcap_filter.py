"""Tests for removing ADARE's own traffic from a net0 pcap (adare.hypervisor.qemu.pcap_filter)."""

import asyncio
import ipaddress
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.hypervisor.qemu.pcap_filter import (
    AdareTrafficRules,
    filter_pcap_file,
    rules_for_vm_config,
    sidecar_path,
)

GUEST, HOST, SMB, DNS, WEB = '10.0.2.15', '10.0.2.2', '10.0.2.4', '10.0.2.3', '151.101.64.223'
AGENT = 18765
RULES = AdareTrafficRules(agent_ports=frozenset({AGENT}), smb_ip=SMB)


def _ip(a: str) -> bytes:
    return ipaddress.IPv4Address(a).packed


def frame(
    src: str, dst: str, sport: int = 1000, dport: int = 2000, proto: int = 6, frag: int = 0, payload=b'x'
) -> bytes:
    l4 = struct.pack('!HH', sport, dport) + b'\x00' * 16 + payload if proto in (6, 17) else payload
    ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20 + len(l4), 1, frag, 64, proto, 0, _ip(src), _ip(dst))
    return b'\x52\x54\x00\x12\x34\x56' * 2 + b'\x08\x00' + ip + l4


def write_pcap(path: Path, frames, endian: str = '<', magic: int = 0xA1B2C3D4, linktype: int = 1, tail: bytes = b''):
    with open(path, 'wb') as f:
        f.write(struct.pack(endian + 'IHHiIII', magic, 2, 4, 0, 0, 65535, linktype))
        for i, fr in enumerate(frames):
            f.write(struct.pack(endian + 'IIII', 1_700_000_000 + i, i, len(fr), len(fr)) + fr)
        f.write(tail)


def records(path: Path, endian: str = '<') -> list[bytes]:
    data = path.read_bytes()[24:]
    out = []
    while len(data) >= 16:
        n = struct.unpack(endian + 'IIII', data[:16])[2]
        out.append(data[: 16 + n])
        data = data[16 + n :]
    return out


MIXED = [
    frame(HOST, GUEST, 50000, AGENT),  # agent request      -> removed
    frame(GUEST, HOST, AGENT, 50000, payload=b'p' * 1400),  # agent pull -> removed
    frame(GUEST, SMB, 40000, 445),  # SMB share          -> removed
    frame(SMB, GUEST, 445, 40000),  # SMB share          -> removed
    frame(GUEST, DNS, 41000, 53, proto=17),  # DNS -> kept
    frame(GUEST, WEB, 52780, 443),  # guest web traffic  -> kept
    frame(HOST, GUEST, 50001, 8080),  # other host->guest port -> kept
    frame(GUEST, WEB, AGENT, 443),  # guest uses 18765 as client port to internet -> kept
    frame(GUEST, HOST, 0, 0, frag=0x00B9),  # non-first fragment -> kept
]


def test_removes_only_adare_packets_and_keeps_the_rest_byte_identical(tmp_path):
    pcap = tmp_path / 'vm.pcap'
    write_pcap(pcap, MIXED)
    original = records(pcap)

    result = filter_pcap_file(pcap, RULES)

    assert result.status == 'filtered'
    assert (result.packets_removed, result.packets_kept) == (4, 5)
    assert records(pcap) == [original[i] for i in (4, 5, 6, 7, 8)]
    assert pcap.read_bytes()[:24] == (tmp_path / 'vm.pcap').read_bytes()[:24]
    assert result.bytes_after == pcap.stat().st_size < result.bytes_before
    assert result.sha256_raw and result.sha256_filtered and result.sha256_raw != result.sha256_filtered
    assert not list(tmp_path.glob('*.filtering'))


def test_sidecar_documents_rules_counts_and_hashes(tmp_path):
    pcap = tmp_path / 'vm.pcap'
    write_pcap(pcap, MIXED)
    result = filter_pcap_file(pcap, RULES)

    sidecar = json.loads(sidecar_path(pcap).read_text())
    assert sidecar['status'] == 'filtered'
    assert sidecar['packets_removed'] == 4
    assert sidecar['sha256_raw'] == result.sha256_raw
    assert '18765' in sidecar['rules']['agent_tcp'] and SMB in sidecar['rules']['smb_share']


def test_without_smb_share_smb_address_traffic_is_kept(tmp_path):
    pcap = tmp_path / 'vm.pcap'
    write_pcap(pcap, MIXED)
    result = filter_pcap_file(pcap, AdareTrafficRules(agent_ports=frozenset({AGENT})))
    assert (result.packets_removed, result.packets_kept) == (2, 7)


@pytest.mark.parametrize('endian,magic', [('<', 0xA1B2C3D4), ('>', 0xA1B2C3D4), ('<', 0xA1B23C4D), ('>', 0xA1B23C4D)])
def test_all_classic_pcap_variants(tmp_path, endian, magic):
    pcap = tmp_path / 'vm.pcap'
    write_pcap(pcap, MIXED, endian=endian, magic=magic)
    result = filter_pcap_file(pcap, RULES)
    assert result.packets_removed == 4
    assert len(records(pcap, endian)) == 5


def test_truncated_last_record_is_copied_as_is(tmp_path):
    pcap = tmp_path / 'vm.pcap'
    partial = struct.pack('<IIII', 1, 2, 100, 100) + b'\x00' * 10
    write_pcap(pcap, MIXED, tail=partial)
    result = filter_pcap_file(pcap, RULES)
    assert result.truncated_tail_bytes == len(partial)
    assert pcap.read_bytes().endswith(partial)


@pytest.mark.parametrize(
    'kwargs,reason',
    [({'linktype': 101}, 'link type'), ({'magic': 0x0A0D0D0A}, 'not a classic pcap')],
)
def test_unsupported_files_are_left_untouched(tmp_path, kwargs, reason):
    pcap = tmp_path / 'vm.pcap'
    write_pcap(pcap, MIXED, **kwargs)
    before = pcap.read_bytes()
    result = filter_pcap_file(pcap, RULES)
    assert result.status == 'skipped' and reason in result.reason
    assert pcap.read_bytes() == before


def test_no_rules_skips(tmp_path):
    pcap = tmp_path / 'vm.pcap'
    write_pcap(pcap, MIXED)
    before = pcap.read_bytes()
    assert filter_pcap_file(pcap, AdareTrafficRules()).status == 'skipped'
    assert pcap.read_bytes() == before


def test_rules_for_vm_config_uses_only_adare_forwards_and_smb():
    config = SimpleNamespace(
        port_forwarding_rules={
            'adarevm': {'name': 'adarevm', 'protocol': 'tcp', 'guest_ip': '', 'guest_port': AGENT, 'host_port': 18770},
            'user-web': {'name': 'user-web', 'protocol': 'tcp', 'guest_ip': '', 'guest_port': 80, 'host_port': 8080},
        },
        smb_share_path='/tmp/smb',
    )
    rules = rules_for_vm_config(config)
    assert rules.agent_ports == frozenset({AGENT})
    assert rules.smb_ip == SMB and rules.guest_ip == GUEST

    bare = rules_for_vm_config(SimpleNamespace(port_forwarding_rules={}, smb_share_path=None))
    assert not bare.agent_ports and bare.smb_ip is None


def _ctx(pcap: Path, cli=None, setting=None):
    vm_config = SimpleNamespace(
        pcap_paths={'net0': str(pcap)},
        port_forwarding_rules={'adarevm': {'protocol': 'tcp', 'guest_port': AGENT}},
        smb_share_path='/tmp/smb',
    )
    settings = SimpleNamespace() if setting is None else SimpleNamespace(filter_pcap=setting)
    return SimpleNamespace(
        vm=SimpleNamespace(config=vm_config),
        config=SimpleNamespace(filter_pcap=cli),
        playbook=SimpleNamespace(settings=settings),
    )


@pytest.mark.parametrize(
    'cli,setting,filtered',
    [(None, None, True), (None, False, False), (False, True, False), (True, False, True), (None, True, True)],
)
def test_lifecycle_filter_switch(tmp_path, cli, setting, filtered):
    pcap = tmp_path / 'vm.pcap'
    write_pcap(pcap, MIXED)
    before = pcap.read_bytes()
    manager = VMLifecycleManager.__new__(VMLifecycleManager)
    manager.hypervisor_type = 'qemu'

    asyncio.run(manager.perform_pcap_filter(_ctx(pcap, cli, setting)))

    assert (pcap.read_bytes() != before) is filtered
    assert sidecar_path(pcap).exists() is filtered


def test_lifecycle_without_capture_is_a_noop(tmp_path):
    manager = VMLifecycleManager.__new__(VMLifecycleManager)
    manager.hypervisor_type = 'qemu'
    ctx = _ctx(tmp_path / 'missing.pcap')
    asyncio.run(manager.perform_pcap_filter(ctx))  # missing file: warning only
    ctx.vm.config.pcap_paths = {}
    asyncio.run(manager.perform_pcap_filter(ctx))
    assert not list(tmp_path.iterdir())
