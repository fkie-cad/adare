"""Concurrent runs must never pick the same CV/OCR server port (bind probe + cross-process lock)."""

import subprocess
import sys

import pytest

from adare.backend.vm import slots

pytestmark = [pytest.mark.unit, pytest.mark.skipif(not slots.slots_enabled(), reason="needs fcntl")]


@pytest.fixture(autouse=True)
def _isolated_port_locks(tmp_path, monkeypatch):
    """Port locks live under the ADARE data dir; keep each test's own."""
    monkeypatch.setattr(slots, "slots_dir", lambda: tmp_path / "vm_slots_dir")
    slots._PORT_LEASES.clear()
    yield
    for lease in list(slots._PORT_LEASES.values()):
        lease.release()
    slots._PORT_LEASES.clear()


def test_a_reserved_port_is_not_handed_to_a_second_run(tmp_path, monkeypatch):
    from adare.backend.experiment import mcp_server_manager as m

    monkeypatch.setattr("adare.helperfunctions.port.is_localhost_port_free", lambda port: True)
    # a sibling process holds 13109 (not bound yet, e.g. still importing PaddleOCR)
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys,time;from pathlib import Path;from adare.backend.vm import slots;"
            "assert slots.try_reserve_port('cv',13109,directory=Path(sys.argv[1]));print('READY',flush=True);time.sleep(30)",
            str(tmp_path / "vm_slots_dir" / "ports"),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "READY"
        first = m.find_free_cv_port(13109)
        second = m.find_free_cv_port(13109)
        assert first == 13110 and second == 13111  # skipped the sibling's, and our own first pick
    finally:
        holder.kill()
        holder.wait()


def test_a_released_port_can_be_reserved_again():
    assert slots.try_reserve_port("cv", 13109)
    assert not slots.try_reserve_port("cv", 13109)
    assert slots.try_reserve_port("cv", 13109, reentrant=True)
    slots.release_port("cv", 13109)
    assert slots.try_reserve_port("cv", 13109)
