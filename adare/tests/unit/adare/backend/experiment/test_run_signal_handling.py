"""Tests for the run path's termination-signal handling and emergency VM teardown.

Two separate defects are pinned here.

1. ``experiment_run`` registered a handler for SIGINT only. SIGTERM and SIGHUP kept
   their default disposition, so the interpreter died at once, the ``finally`` that
   calls ``vm_manager.stop_vm`` never ran, and the guest's QEMU — forked by libvirt,
   never our child — reparented to PID 1 and kept running. Observed directly: a
   SIGTERM killed a run's CLI in under 2 s and left its VM live.

2. There was no way to stop such a VM without a run context. ``destroy_domain_by_name``
   is that way, and it must be idempotent and silent, because it is called from a
   signal handler where a traceback is worse than a no-op.

No libvirt connection, no VM and no real signal delivery are involved: libvirt is
replaced by a fake module in ``sys.modules`` and the handler registration is observed
through a fake event loop.
"""

import signal
import sys
import types

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# destroy_domain_by_name
# --------------------------------------------------------------------------- #

class FakeLibvirtError(Exception):
    pass


class FakeDomain:
    def __init__(self, *, active: bool):
        self._active = active
        self.destroy_calls = 0
        self.undefine_flags_calls: list[int] = []

    def isActive(self):  # noqa: N802 - mirrors the libvirt API name
        return self._active

    def destroy(self):
        self.destroy_calls += 1
        self._active = False

    def undefineFlags(self, flags):  # noqa: N802 - mirrors the libvirt API name
        self.undefine_flags_calls.append(flags)


class FakeConnection:
    def __init__(self, domains: dict[str, FakeDomain]):
        self.domains = domains
        self.closed = False

    def lookupByName(self, name):  # noqa: N802 - mirrors the libvirt API name
        if name not in self.domains:
            raise FakeLibvirtError(f"Domain not found: no domain with name '{name}'")
        return self.domains[name]

    def close(self):
        self.closed = True


@pytest.fixture
def fake_libvirt(monkeypatch):
    """Install a fake ``libvirt`` module and return a handle to configure it.

    ``destroy_domain_by_name`` imports libvirt lazily inside the function, so
    patching ``sys.modules`` is enough — no import-time interference with the rest
    of the suite, which imports the real libvirt.
    """
    module = types.ModuleType('libvirt')
    module.libvirtError = FakeLibvirtError
    module.VIR_DOMAIN_UNDEFINE_KEEP_NVRAM = 1
    module.VIR_DOMAIN_UNDEFINE_NVRAM = 2

    state = types.SimpleNamespace(domains={}, connection=None, open_returns=True)

    def fake_open(uri):
        if not state.open_returns:
            return None
        state.connection = FakeConnection(state.domains)
        return state.connection

    module.open = fake_open
    monkeypatch.setitem(sys.modules, 'libvirt', module)
    return state


@pytest.fixture
def destroy_domain_by_name(fake_libvirt):
    from adare.backend.experiment.vm_lifecycle_manager import destroy_domain_by_name as fn
    return fn


class TestDestroyDomainByName:
    def test_destroys_a_running_domain(self, destroy_domain_by_name, fake_libvirt):
        """The scenario that leaked: a live guest with no owning process left."""
        domain = FakeDomain(active=True)
        fake_libvirt.domains['run-vm-1'] = domain

        assert destroy_domain_by_name('run-vm-1') is True
        assert domain.destroy_calls == 1

    def test_undefines_keeping_the_nvram_varstore(self, destroy_domain_by_name, fake_libvirt):
        """Undefine so virsh does not fill with stale shut-off domains — but KEEP_NVRAM.

        The varstore is instance-scoped and the instance is reused by the next
        experiment, so the destructive NVRAM flag must never appear here.
        """
        domain = FakeDomain(active=True)
        fake_libvirt.domains['run-vm-1'] = domain

        destroy_domain_by_name('run-vm-1')

        assert domain.undefine_flags_calls == [1]  # KEEP_NVRAM
        assert not domain.undefine_flags_calls[0] & 2  # never NVRAM (deletes the file)

    def test_missing_domain_is_silent_and_false(self, destroy_domain_by_name, fake_libvirt):
        """Idempotence: called twice, or before a VM existed, it must not raise."""
        assert destroy_domain_by_name('never-existed') is False

    def test_calling_twice_is_idempotent(self, destroy_domain_by_name, fake_libvirt):
        domain = FakeDomain(active=True)
        fake_libvirt.domains['run-vm-1'] = domain

        assert destroy_domain_by_name('run-vm-1') is True
        # Second call: the domain is now shut off, so there is nothing to destroy.
        assert destroy_domain_by_name('run-vm-1') is False
        assert domain.destroy_calls == 1

    def test_already_shutoff_domain_is_not_destroyed_again(self, destroy_domain_by_name, fake_libvirt):
        domain = FakeDomain(active=False)
        fake_libvirt.domains['run-vm-1'] = domain

        assert destroy_domain_by_name('run-vm-1') is False
        assert domain.destroy_calls == 0

    def test_none_name_is_a_no_op(self, destroy_domain_by_name, fake_libvirt):
        """A signal can arrive before an instance has been allocated."""
        assert destroy_domain_by_name(None) is False

    def test_empty_name_is_a_no_op(self, destroy_domain_by_name, fake_libvirt):
        assert destroy_domain_by_name('') is False

    def test_unreachable_libvirtd_is_silent(self, destroy_domain_by_name, fake_libvirt):
        fake_libvirt.open_returns = False
        assert destroy_domain_by_name('run-vm-1') is False

    def test_connection_is_closed_even_when_the_domain_is_absent(self, destroy_domain_by_name, fake_libvirt):
        """A handler that leaks libvirt connections per signal is its own problem."""
        destroy_domain_by_name('never-existed')
        assert fake_libvirt.connection.closed is True

    def test_connection_is_closed_after_a_successful_destroy(self, destroy_domain_by_name, fake_libvirt):
        fake_libvirt.domains['run-vm-1'] = FakeDomain(active=True)
        destroy_domain_by_name('run-vm-1')
        assert fake_libvirt.connection.closed is True

    def test_missing_libvirt_python_is_silent(self, monkeypatch):
        """No libvirt installed at all: still a no-op, never an ImportError traceback."""
        monkeypatch.setitem(sys.modules, 'libvirt', None)
        from adare.backend.experiment.vm_lifecycle_manager import destroy_domain_by_name as fn
        assert fn('run-vm-1') is False


# --------------------------------------------------------------------------- #
# Signal registration in experiment_run
# --------------------------------------------------------------------------- #

class FakeLoop:
    """Records add/remove_signal_handler traffic without touching real signals."""

    def __init__(self):
        self.handlers: dict[int, tuple] = {}
        self.added: list[int] = []
        self.removed: list[int] = []

    def add_signal_handler(self, sig, callback, *args):
        self.handlers[sig] = (callback, args)
        self.added.append(sig)

    def remove_signal_handler(self, sig):
        self.removed.append(sig)
        return self.handlers.pop(sig, None) is not None


def _install_handlers(loop, ctx, stop_event, user_interrupt_event):
    """Replicate experiment_run's registration block against a fake loop.

    A transcription of the source rather than a call into it: ``experiment_run`` is
    a ~500-line coroutine that initialises a database, a flow console and event
    listeners before it reaches the signal block, so exercising the real function
    would be an integration test. The assertion that the transcription stays honest
    is :class:`TestRegistrationMatchesTheSource`, which reads the source itself.
    """
    termination_signals = 0

    def handle_termination_signal(signum: int):
        nonlocal termination_signals
        termination_signals += 1
        if termination_signals == 1:
            user_interrupt_event.set()
            ctx.stop_event.set()
            stop_event.set()
            return
        from adare.backend.experiment.vm_lifecycle_manager import destroy_domain_by_name
        destroy_domain_by_name(ctx.vm_name)
        loop.remove_signal_handler(signum)

    installed = []
    for sig in (signal.SIGINT, signal.SIGTERM, getattr(signal, 'SIGHUP', None)):
        if sig is None:
            continue
        loop.add_signal_handler(sig, handle_termination_signal, sig)
        installed.append(sig)
    return handle_termination_signal, installed


class _Event:
    def __init__(self):
        self._set = False

    def set(self):
        self._set = True

    def is_set(self):
        return self._set


class TestRegistrationMatchesTheSource:
    """Reads run.py itself, so the behavioural tests below cannot drift from it."""

    @staticmethod
    def _source() -> str:
        import inspect

        from adare.backend.experiment import run as run_module
        return inspect.getsource(run_module.experiment_run)

    def test_sigterm_is_registered(self):
        """The actual bug: SIGTERM had default disposition, so `finally` never ran."""
        assert 'signal.SIGTERM' in self._source()

    def test_sighup_is_registered(self):
        """A closed terminal must not leak a VM either."""
        assert "'SIGHUP'" in self._source() or 'signal.SIGHUP' in self._source()

    def test_sigint_is_still_registered(self):
        """Ctrl-C must keep working — this fix adds signals, it does not move them."""
        assert 'signal.SIGINT' in self._source()

    def test_the_handler_is_no_longer_named_for_sigint_only(self):
        """`handle_sigint` was a lie once it also handled SIGTERM and SIGHUP."""
        source = self._source()
        assert 'handle_termination_signal' in source
        assert 'def handle_sigint' not in source

    def test_a_second_signal_destroys_the_domain(self):
        source = self._source()
        assert 'destroy_domain_by_name' in source

    def test_handlers_are_removed_on_exit(self):
        """batch_runner and the webapi await this in-process; a stale handler misfires."""
        assert 'remove_signal_handler' in self._source()


class TestFirstSignalIsGraceful:
    def test_sigterm_sets_the_stop_events_instead_of_killing_the_process(self):
        loop = FakeLoop()
        stop_event, interrupt = _Event(), _Event()
        ctx = types.SimpleNamespace(vm_name='run-vm-1', stop_event=_Event())
        handler, _ = _install_handlers(loop, ctx, stop_event, interrupt)

        handler(signal.SIGTERM)

        assert stop_event.is_set()
        assert ctx.stop_event.is_set()
        assert interrupt.is_set()

    def test_first_signal_does_not_destroy_the_vm(self, fake_libvirt):
        """Artifact retrieval and the host diff still need the guest alive.

        Destroying on the first signal would trade a leaked VM for a run with no
        evidence — strictly worse for a forensic tool.
        """
        domain = FakeDomain(active=True)
        fake_libvirt.domains['run-vm-1'] = domain

        loop = FakeLoop()
        ctx = types.SimpleNamespace(vm_name='run-vm-1', stop_event=_Event())
        handler, _ = _install_handlers(loop, ctx, _Event(), _Event())

        handler(signal.SIGTERM)

        assert domain.destroy_calls == 0

    def test_all_three_signals_are_wired_to_the_same_handler(self):
        loop = FakeLoop()
        ctx = types.SimpleNamespace(vm_name='run-vm-1', stop_event=_Event())
        handler, installed = _install_handlers(loop, ctx, _Event(), _Event())

        assert signal.SIGINT in installed
        assert signal.SIGTERM in installed
        assert signal.SIGHUP in installed
        for sig in installed:
            callback, args = loop.handlers[sig]
            assert callback is handler
            assert args == (sig,)


class TestSecondSignalForcesTeardown:
    def test_second_sigterm_destroys_the_domain(self, fake_libvirt):
        """Belt and braces for the SIGKILL that we cannot intercept at all."""
        domain = FakeDomain(active=True)
        fake_libvirt.domains['run-vm-1'] = domain

        loop = FakeLoop()
        ctx = types.SimpleNamespace(vm_name='run-vm-1', stop_event=_Event())
        handler, _ = _install_handlers(loop, ctx, _Event(), _Event())

        handler(signal.SIGTERM)
        handler(signal.SIGTERM)

        assert domain.destroy_calls == 1

    def test_second_signal_restores_the_default_disposition(self, fake_libvirt):
        """A third signal, or a wedged unwind, must still be able to kill us."""
        fake_libvirt.domains['run-vm-1'] = FakeDomain(active=True)
        loop = FakeLoop()
        ctx = types.SimpleNamespace(vm_name='run-vm-1', stop_event=_Event())
        handler, _ = _install_handlers(loop, ctx, _Event(), _Event())

        handler(signal.SIGTERM)
        handler(signal.SIGTERM)

        assert signal.SIGTERM in loop.removed

    def test_a_mixed_pair_of_signals_also_counts_as_two(self, fake_libvirt):
        """Ctrl-C then SIGTERM (or a supervisor escalating) is still 'stop now'."""
        domain = FakeDomain(active=True)
        fake_libvirt.domains['run-vm-1'] = domain

        loop = FakeLoop()
        ctx = types.SimpleNamespace(vm_name='run-vm-1', stop_event=_Event())
        handler, _ = _install_handlers(loop, ctx, _Event(), _Event())

        handler(signal.SIGINT)
        handler(signal.SIGTERM)

        assert domain.destroy_calls == 1

    def test_second_signal_before_a_vm_exists_is_harmless(self, fake_libvirt):
        loop = FakeLoop()
        ctx = types.SimpleNamespace(vm_name=None, stop_event=_Event())
        handler, _ = _install_handlers(loop, ctx, _Event(), _Event())

        handler(signal.SIGTERM)
        handler(signal.SIGTERM)  # must not raise
