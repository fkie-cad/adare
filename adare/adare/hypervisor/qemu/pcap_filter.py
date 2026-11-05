"""
Remove ADARE's own control traffic from a finished net0 pcap.

QEMU's ``filter-dump`` cannot filter, so the capture of the SLIRP netdev also holds
the traffic ADARE itself causes on that netdev:

* the adarevm WebSocket, reached from the host through a ``hostfwd`` rule
  (host side ``10.0.2.2`` <-> guest ``10.0.2.15:<guest_port>``). File pulls go
  over it, so it is usually >90% of the capture;
* the SLIRP built-in SMB share at ``10.0.2.4``, which only exists when ADARE
  configured ``smb=`` for the run.

After the VM has stopped (QEMU closed the file), :func:`filter_pcap_file` rewrites
the pcap without those packets. Every other record (16-byte record header and
frame) is copied byte for byte, so timestamps and contents of the guest's own
traffic are unchanged. A sidecar ``<pcap>.filter.json`` records the rules, the
counts and the sha256 of the raw and of the filtered capture.

Only classic pcap with Ethernet link type (what filter-dump writes) is filtered;
anything else is left untouched and reported as skipped.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import struct
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

# QEMU SLIRP user-mode networking addresses (fixed by QEMU defaults, see guest_network.py)
SLIRP_GUEST_IP = '10.0.2.15'
SLIRP_HOST_IP = '10.0.2.2'
SLIRP_SMB_IP = '10.0.2.4'

_PCAP_MAGICS = {
    b'\xd4\xc3\xb2\xa1': '<',  # microsecond, little endian
    b'\xa1\xb2\xc3\xd4': '>',  # microsecond, big endian
    b'\x4d\x3c\xb2\xa1': '<',  # nanosecond, little endian
    b'\xa1\xb2\x3c\x4d': '>',  # nanosecond, big endian
}
_LINKTYPE_ETHERNET = 1
_ETHERTYPE_IPV4 = b'\x08\x00'
_IPPROTO_TCP = 6
_COPY_CHUNK = 1 << 20


@dataclass(frozen=True)
class AdareTrafficRules:
    """What counts as ADARE's own traffic on the SLIRP netdev."""

    agent_ports: frozenset[int] = frozenset()  # guest-side TCP ports of ADARE's hostfwd rules
    guest_ip: str = SLIRP_GUEST_IP
    host_ip: str = SLIRP_HOST_IP
    smb_ip: str | None = None  # set only when the run has a SLIRP SMB share

    def describe(self) -> dict:
        return {
            'agent_tcp': (
                f'{self.host_ip} <-> {self.guest_ip}:{sorted(self.agent_ports)}' if self.agent_ports else None
            ),
            'smb_share': f'any packet to/from {self.smb_ip}' if self.smb_ip else None,
        }


# hostfwd rules ADARE itself creates (hypervisor/qemu/lifecycle.py); any other forward is left captured
ADARE_FORWARD_RULE_NAMES = frozenset({'adarevm'})


def rules_for_vm_config(vm_config) -> AdareTrafficRules:
    """Build the rules from a QEMU VM config: ADARE's own hostfwd rules and its SMB share.

    ``vm_config.port_forwarding_rules`` is the serialized form, ``{name: {protocol, guest_ip, guest_port, ...}}``.
    """
    agent_ports: set[int] = set()
    guest_ip = SLIRP_GUEST_IP
    for name, rule in (getattr(vm_config, 'port_forwarding_rules', None) or {}).items():
        if name not in ADARE_FORWARD_RULE_NAMES or str(rule.get('protocol', 'tcp')).lower() != 'tcp':
            continue
        agent_ports.add(int(rule['guest_port']))
        if rule.get('guest_ip'):
            guest_ip = rule['guest_ip']
    smb_ip = SLIRP_SMB_IP if getattr(vm_config, 'smb_share_path', None) else None
    return AdareTrafficRules(agent_ports=frozenset(agent_ports), guest_ip=guest_ip, smb_ip=smb_ip)


@dataclass
class PcapFilterResult:
    path: str
    status: str  # 'filtered' | 'skipped'
    reason: str | None = None
    rules: dict = field(default_factory=dict)
    packets_kept: int = 0
    packets_removed: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    sha256_raw: str | None = None
    sha256_filtered: str | None = None
    truncated_tail_bytes: int = 0  # a partial last record (QEMU killed mid-write) is copied as is
    timestamp: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


class _Matcher:
    def __init__(self, rules: AdareTrafficRules):
        self._ports = rules.agent_ports
        self._guest = ipaddress.IPv4Address(rules.guest_ip).packed
        self._host = ipaddress.IPv4Address(rules.host_ip).packed
        self._smb = ipaddress.IPv4Address(rules.smb_ip).packed if rules.smb_ip else None

    def is_adare(self, frame: bytes) -> bool:
        if len(frame) < 34 or frame[12:14] != _ETHERTYPE_IPV4:
            return False
        ip = memoryview(frame)[14:]
        src, dst = bytes(ip[12:16]), bytes(ip[16:20])
        if self._smb is not None and self._smb in (src, dst):
            return True
        if not self._ports or ip[9] != _IPPROTO_TCP:
            return False
        if (struct.unpack('!H', ip[6:8])[0] & 0x1FFF) != 0:  # non-first fragment: no TCP header
            return False
        ihl = (ip[0] & 0x0F) * 4
        if len(ip) < ihl + 4:
            return False
        sport, dport = struct.unpack('!HH', ip[ihl : ihl + 4])
        if src == self._guest and dst == self._host:
            return sport in self._ports
        if src == self._host and dst == self._guest:
            return dport in self._ports
        return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(_COPY_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sidecar_path(pcap_path: Path) -> Path:
    return pcap_path.with_name(pcap_path.name + '.filter.json')


def filter_pcap_file(pcap_path: Path | str, rules: AdareTrafficRules, write_sidecar: bool = True) -> PcapFilterResult:
    """Rewrite ``pcap_path`` in place without ADARE's own packets (see module docstring).

    The filtered capture is written to a temp file next to it and moved over the
    original only when complete, so a failure leaves the raw capture in place.
    Raises OSError on I/O failures.
    """
    pcap_path = Path(pcap_path)
    result = PcapFilterResult(
        path=str(pcap_path),
        status='skipped',
        rules=rules.describe(),
        timestamp=datetime.now(UTC).replace(tzinfo=None).isoformat(timespec='seconds'),
    )
    result.bytes_before = pcap_path.stat().st_size
    if not rules.agent_ports and not rules.smb_ip:
        result.reason = 'no ADARE traffic rules (no hostfwd, no SMB share)'
        return _finish(pcap_path, result, write_sidecar)

    with open(pcap_path, 'rb') as src:
        header = src.read(24)
        endian = _PCAP_MAGICS.get(header[:4])
        if len(header) < 24 or endian is None:
            result.reason = 'not a classic pcap file (pcapng or unknown magic)'
            return _finish(pcap_path, result, write_sidecar)
        linktype = struct.unpack(endian + 'I', header[20:24])[0] & 0x0FFFFFFF
        if linktype != _LINKTYPE_ETHERNET:
            result.reason = f'link type {linktype} is not Ethernet'
            return _finish(pcap_path, result, write_sidecar)

        result.sha256_raw = _sha256_file(pcap_path)
        matcher = _Matcher(rules)
        record_fmt = endian + 'IIII'
        tmp_path = pcap_path.with_name(pcap_path.name + '.filtering')
        try:
            with open(tmp_path, 'wb') as dst:
                dst.write(header)
                while record := src.read(16):
                    if len(record) < 16:
                        dst.write(record)
                        result.truncated_tail_bytes = len(record)
                        break
                    incl_len = struct.unpack(record_fmt, record)[2]
                    frame = src.read(incl_len)
                    if len(frame) < incl_len:
                        dst.write(record + frame)
                        result.truncated_tail_bytes = 16 + len(frame)
                        break
                    if matcher.is_adare(frame):
                        result.packets_removed += 1
                    else:
                        dst.write(record)
                        dst.write(frame)
                        result.packets_kept += 1
            os.replace(tmp_path, pcap_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    result.status = 'filtered'
    result.bytes_after = pcap_path.stat().st_size
    result.sha256_filtered = _sha256_file(pcap_path)
    return _finish(pcap_path, result, write_sidecar)


def _finish(pcap_path: Path, result: PcapFilterResult, write_sidecar: bool) -> PcapFilterResult:
    if result.status == 'skipped':
        result.bytes_after = result.bytes_before
        log.info(f"pcap filter skipped for {pcap_path.name}: {result.reason}")
    else:
        log.info(
            f"pcap filter: {pcap_path.name} removed {result.packets_removed} ADARE packets, "
            f"kept {result.packets_kept} ({result.bytes_before / 1e6:.2f} -> {result.bytes_after / 1e6:.2f} MB)"
        )
    if write_sidecar:
        sidecar_path(pcap_path).write_text(json.dumps(result.to_dict(), indent=1) + '\n', encoding='utf-8')
    return result
