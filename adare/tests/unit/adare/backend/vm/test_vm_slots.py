"""Cross-process VM slot counter (``adare.backend.vm.slots``) and its wiring into VmInstanceManager.

Real flock on temp files, real second processes: no VM and no mocks of the locking itself.
"""

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from adare.backend.vm import slots
from adare.backend.vm.slots import (
    VMSlotTimeout,
    acquire_all_slots,
    acquire_slot,
    exclusive_env,
    max_vm_slots,
    slot_status,
)

pytestmark = [pytest.mark.unit, pytest.mark.skipif(not slots.slots_enabled(), reason="needs fcntl")]

FAST = 0.4  # timeout (s) for expected-failure waits


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (slots.MAX_VMS_ENV, slots.SLOT_TIMEOUT_ENV, slots.EXCLUSIVE_PID_ENV):
        monkeypatch.delenv(name, raising=False)


def _holder_process(directory, count, mode="one", n=1):
    """Start a Python process that takes slots (via the real module), prints READY, then sleeps."""
    code = textwrap.dedent(
        f"""
        import sys, time
        from pathlib import Path
        from adare.backend.vm import slots
        d = Path({str(directory)!r})
        leases = []
        if {mode!r} == "one":
            for _ in range({n}):
                leases.append(slots.acquire_slot(5, max_slots={count}, directory=d))
        else:
            leases.append(slots.acquire_all_slots(5, max_slots={count}, directory=d))
        print("READY", flush=True)
        time.sleep(60)
        """
    )
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "READY"
    return proc


def _kill(proc):
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=10)


# --- N: env > config > default ---------------------------------------------------


def test_default_is_the_previous_instance_limit():
    from adare.backend.vm.instance_manager import VmInstanceManager

    assert max_vm_slots() == 20 == VmInstanceManager.MAX_INSTANCES_PER_VM


def test_env_sets_the_slot_count(monkeypatch):
    monkeypatch.setenv("ADARE_MAX_VMS", "3")
    assert max_vm_slots() == 3


def test_user_config_sets_the_slot_count(monkeypatch):
    from adare.config import userconfig

    monkeypatch.setattr(userconfig, "get", lambda name: "7" if name == "ADARE_MAX_VMS" else None)
    assert max_vm_slots() == 7
    monkeypatch.setenv("ADARE_MAX_VMS", "2")  # env beats config
    assert max_vm_slots() == 2


@pytest.mark.parametrize("bad", ["0", "-3", "many", ""])
def test_bad_values_fall_back_to_default(monkeypatch, bad):
    monkeypatch.setenv("ADARE_MAX_VMS", bad)
    assert max_vm_slots() == 20


# --- single slots ------------------------------------------------------------------


def test_n_slots_then_timeout_then_release_frees_one(tmp_path):
    leases = [acquire_slot(FAST, max_slots=3, directory=tmp_path) for _ in range(3)]
    assert sorted(i for lease in leases for i in lease.indices) == [0, 1, 2]
    with pytest.raises(VMSlotTimeout):
        acquire_slot(FAST, max_slots=3, directory=tmp_path)
    leases[1].release()
    again = acquire_slot(FAST, max_slots=3, directory=tmp_path)
    assert again.indices == [1]


def test_lease_context_manager_releases(tmp_path):
    with acquire_slot(FAST, max_slots=1, directory=tmp_path), pytest.raises(VMSlotTimeout):
        acquire_slot(0.1, max_slots=1, directory=tmp_path)
    acquire_slot(FAST, max_slots=1, directory=tmp_path).release()


def test_two_processes_cannot_exceed_n(tmp_path):
    """The point of the feature: another adare process holding slots counts against this one."""
    other = _holder_process(tmp_path, count=2, n=2)
    try:
        with pytest.raises(VMSlotTimeout):
            acquire_slot(FAST, max_slots=2, directory=tmp_path)
        assert slot_status(max_slots=2, directory=tmp_path)["taken"] == 2
    finally:
        _kill(other)
    # A killed holder leaks nothing: the kernel dropped its flocks.
    assert slot_status(max_slots=2, directory=tmp_path)["taken"] == 0
    acquire_slot(FAST, max_slots=2, directory=tmp_path).release()


def test_partial_use_by_another_process(tmp_path):
    other = _holder_process(tmp_path, count=3, n=2)
    try:
        mine = acquire_slot(FAST, max_slots=3, directory=tmp_path)
        assert mine.indices == [2]
        with pytest.raises(VMSlotTimeout):
            acquire_slot(0.1, max_slots=3, directory=tmp_path)
    finally:
        _kill(other)


def test_waiting_taker_gets_the_slot_when_it_frees(tmp_path):
    other = _holder_process(tmp_path, count=1, n=1)
    killer = subprocess.Popen(
        [sys.executable, "-c", f"import os,signal,time; time.sleep(0.5); os.kill({other.pid}, signal.SIGKILL)"]
    )
    try:
        start = time.monotonic()
        lease = acquire_slot(10, max_slots=1, directory=tmp_path)
        assert 0.3 < time.monotonic() - start < 8
        lease.release()
    finally:
        killer.wait(timeout=10)
        other.wait(timeout=10)


# --- exclusive use -----------------------------------------------------------------


def test_take_all_blocks_every_other_taker(tmp_path):
    lease = acquire_all_slots(FAST, max_slots=3, directory=tmp_path)
    assert lease.exclusive and lease.indices == [0, 1, 2]
    with pytest.raises(VMSlotTimeout):
        acquire_slot(0.1, max_slots=3, directory=tmp_path)
    with pytest.raises(VMSlotTimeout):
        acquire_all_slots(0.1, max_slots=3, directory=tmp_path)
    lease.release()
    acquire_slot(FAST, max_slots=3, directory=tmp_path).release()


def test_take_all_waits_for_a_running_vm_and_times_out_holding_nothing(tmp_path):
    other = _holder_process(tmp_path, count=3, n=1)
    try:
        with pytest.raises(VMSlotTimeout, match="only"):
            acquire_all_slots(FAST, max_slots=3, directory=tmp_path)
        # the failed attempt released what it had collected and the guard
        assert slot_status(max_slots=3, directory=tmp_path)["taken"] == 1
        assert len(acquire_slot(FAST, max_slots=3, directory=tmp_path)) == 1
    finally:
        _kill(other)
    acquire_all_slots(FAST, max_slots=3, directory=tmp_path).release()


def test_take_all_in_another_process_blocks_us(tmp_path):
    other = _holder_process(tmp_path, count=2, mode="all")
    try:
        with pytest.raises(VMSlotTimeout):
            acquire_slot(FAST, max_slots=2, directory=tmp_path)
    finally:
        _kill(other)
    acquire_slot(FAST, max_slots=2, directory=tmp_path).release()


def test_take_all_covers_slots_beyond_a_lowered_n(tmp_path):
    held = [acquire_slot(FAST, max_slots=4, directory=tmp_path) for _ in range(4)]
    with pytest.raises(VMSlotTimeout):
        acquire_all_slots(0.1, max_slots=2, directory=tmp_path)  # slots 2 and 3 still exist and are held
    for lease in held:
        lease.release()
    assert acquire_all_slots(FAST, max_slots=2, directory=tmp_path).indices == [0, 1, 2, 3]


def test_a_stream_of_single_takers_cannot_starve_take_all(tmp_path):
    """While an exclusive taker collects slots it holds the guard, so singles wait."""
    one = acquire_slot(FAST, max_slots=2, directory=tmp_path)
    waiter = subprocess.Popen(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                f"""
                from pathlib import Path
                from adare.backend.vm import slots
                lease = slots.acquire_all_slots(10, max_slots=2, directory=Path({str(tmp_path)!r}))
                print("GOT_ALL", flush=True)
                """
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.8)  # the waiter holds the guard exclusively and waits for slot 0
        with pytest.raises(VMSlotTimeout):
            acquire_slot(0.3, max_slots=2, directory=tmp_path)  # slot 1 is free, but the guard keeps us out
        one.release()
        assert waiter.stdout.readline().strip() == "GOT_ALL"
    finally:
        waiter.kill()
        waiter.wait(timeout=10)


# --- subprocess under an exclusive lease -------------------------------------------


def test_descendants_of_the_exclusive_holder_do_not_wait(tmp_path):
    lease = acquire_all_slots(FAST, max_slots=1, directory=tmp_path)
    code = (
        "from pathlib import Path\n"
        "from adare.backend.vm import slots\n"
        f"l = slots.acquire_slot(0.2, max_slots=1, directory=Path({str(tmp_path)!r}))\n"
        "print(len(l))\n"
    )
    blocked = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert blocked.returncode != 0 and "VMSlotTimeout" in blocked.stderr
    ok = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=exclusive_env())
    assert ok.returncode == 0 and ok.stdout.strip() == "0"
    lease.release()


def test_the_holder_itself_is_not_exempt(tmp_path, monkeypatch):
    lease = acquire_all_slots(FAST, max_slots=1, directory=tmp_path)
    monkeypatch.setenv(slots.EXCLUSIVE_PID_ENV, str(os.getpid()))
    with pytest.raises(VMSlotTimeout):
        acquire_slot(0.1, max_slots=1, directory=tmp_path)
    lease.release()


def test_stale_exclusive_marker_is_ignored(tmp_path, monkeypatch):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    monkeypatch.setenv(slots.EXCLUSIVE_PID_ENV, str(dead.pid))
    assert len(acquire_slot(FAST, max_slots=1, directory=tmp_path)) == 1


# --- status -------------------------------------------------------------------------


def test_status_lists_holder_pids(tmp_path):
    other = _holder_process(tmp_path, count=3, n=2)
    try:
        status = slot_status(max_slots=3, directory=tmp_path)
        assert status["total"] == 3 and status["taken"] == 2 and status["free"] == 1
        assert set(status["holders"].values()) == {str(other.pid)}
    finally:
        _kill(other)


def test_cli_status_json(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from adare.run import cli

    monkeypatch.setattr(slots, "slots_dir", lambda: tmp_path)
    monkeypatch.setenv("ADARE_MAX_VMS", "4")
    with acquire_slot(FAST, max_slots=4, directory=tmp_path):
        result = CliRunner().invoke(cli, ["vm", "slots", "status", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip().splitlines()[-1])
    assert data["total"] == 4 and data["taken"] == 1


def test_cli_exclusive_runs_command_under_the_lease(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from adare.run import cli

    monkeypatch.setattr(slots, "slots_dir", lambda: tmp_path)
    monkeypatch.setenv("ADARE_MAX_VMS", "2")
    probe = (
        "import json,sys\nfrom pathlib import Path\nfrom adare.backend.vm import slots\n"
        f"Path({str(tmp_path / 'probe.json')!r}).write_text(json.dumps(slots.slot_status(max_slots=2, directory=Path({str(tmp_path)!r}))))\n"
    )
    result = CliRunner().invoke(cli, ["vm", "slots", "exclusive", "--timeout", "1", "--", sys.executable, "-c", probe])
    assert result.exit_code == 0, result.output
    assert json.loads((tmp_path / "probe.json").read_text())["taken"] == 2
    assert slot_status(max_slots=2, directory=tmp_path)["taken"] == 0  # released on exit


def test_cli_exclusive_exits_75_when_vms_are_running(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from adare.run import cli

    monkeypatch.setattr(slots, "slots_dir", lambda: tmp_path)
    monkeypatch.setenv("ADARE_MAX_VMS", "1")
    with acquire_slot(FAST, max_slots=1, directory=tmp_path):
        result = CliRunner().invoke(cli, ["vm", "slots", "exclusive", "--timeout", "0.2", "--", "true"])
    assert result.exit_code == 75


# --- VmInstanceManager wiring --------------------------------------------------------


def _manager(monkeypatch, tmp_path, instance_id="inst-1"):
    from adare.backend.vm import instance_manager as im

    monkeypatch.setattr(slots, "slots_dir", lambda: tmp_path)
    monkeypatch.setenv("ADARE_MAX_VMS", "1")
    monkeypatch.setenv("ADARE_VM_SLOT_TIMEOUT", "0.3")

    import adare.backend.experiment.stagectxmanager as stage_mod
    import adare.database.api.vm as vm_api_mod

    class FakeApi:
        def __enter__(self):
            return SimpleNamespace(get_vm_instances_for_vm=lambda vm_id: [])

        def __exit__(self, *a):
            return False

    stage_ctx = MagicMock()
    monkeypatch.setattr(stage_mod, "StageCtxManager", lambda *a, **k: nullcontext(stage_ctx))
    monkeypatch.setattr(vm_api_mod, "VmApi", FakeApi)

    manager = im.VmInstanceManager()
    manager.sync_instance_states = AsyncMock(return_value=0)
    manager.find_available_instance = MagicMock(return_value=None)
    manager.create_new_instance = AsyncMock(return_value=SimpleNamespace(id=instance_id))
    return manager


@pytest.mark.asyncio
async def test_allocation_holds_a_slot_until_release(monkeypatch, tmp_path):
    manager = _manager(monkeypatch, tmp_path)
    instance = await manager.allocate_instance_for_experiment("vm-1", "run-1")
    assert instance.id == "inst-1"
    assert slot_status(max_slots=1, directory=tmp_path)["taken"] == 1

    # the only slot is in use: a second allocation (even in another process) times out
    manager.create_new_instance = AsyncMock(return_value=SimpleNamespace(id="inst-2"))
    with pytest.raises(VMSlotTimeout):
        await manager.allocate_instance_for_experiment("vm-1", "run-2")

    manager._release_slot("inst-1")
    assert slot_status(max_slots=1, directory=tmp_path)["taken"] == 0
    await manager.allocate_instance_for_experiment("vm-1", "run-2")


@pytest.mark.asyncio
async def test_failed_allocation_gives_the_slot_back(monkeypatch, tmp_path):
    manager = _manager(monkeypatch, tmp_path)
    manager.create_new_instance = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        await manager.allocate_instance_for_experiment("vm-1", "run-1")
    assert slot_status(max_slots=1, directory=tmp_path)["taken"] == 0


@pytest.mark.asyncio
async def test_allocation_waits_while_another_process_has_exclusive_use(monkeypatch, tmp_path):
    manager = _manager(monkeypatch, tmp_path)
    other = _holder_process(tmp_path, count=1, mode="all")
    try:
        with pytest.raises(VMSlotTimeout):
            await manager.allocate_instance_for_experiment("vm-1", "run-1")
        manager.create_new_instance.assert_not_called()
    finally:
        _kill(other)
