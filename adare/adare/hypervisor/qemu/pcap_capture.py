"""
QEMU network traffic capture (``-object filter-dump``) configuration.

Phase 2 covers ADARE's single "outside world" netdev (``net0``, the SLIRP
user-mode network every VM already gets — see ``_add_network_commandline`` in
``libvirt_xml_builder.py``). Capture config is keyed by *netdev id*, not by VM
name, so a future per-segment netdev (multi-machine networking) is just
another entry in the same dict — the emission code in
``libvirt_xml_builder.py`` does not need to change shape when that lands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PcapCaptureConfig:
    """Maps a QEMU netdev id to the pcap file its traffic should be dumped to."""

    paths: dict[str, str] = field(default_factory=dict)

    def get(self, netdev_id: str) -> str | None:
        return self.paths.get(netdev_id)

    def set(self, netdev_id: str, path: Path | str) -> None:
        self.paths[netdev_id] = str(path)

    def to_dict(self) -> dict[str, str]:
        return dict(self.paths)

    @classmethod
    def from_dict(cls, data: dict[str, str] | None) -> PcapCaptureConfig:
        return cls(paths=dict(data) if data else {})

    def __bool__(self) -> bool:
        return bool(self.paths)


def resolve_net0_pcap_path(run_directory, machine_name: str) -> Path:
    """Compute (and create) the artifacts/pcap/<machine>.pcap path under a run dir."""
    pcap_dir = Path(run_directory.path) / 'artifacts' / 'pcap'
    pcap_dir.mkdir(parents=True, exist_ok=True)
    return pcap_dir / f'{machine_name}.pcap'
