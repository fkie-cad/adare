"""Tests for ExperimentRunCtx convenience properties."""

from pathlib import Path

from adare.backend.experiment.runctx import ExperimentConfig, ExperimentRunCtx


def _make_ctx(
    *,
    test_execution_mode: str | None = None,
    gui_mode_override: str | None = None,
    hypervisor_type: str | None = None,
) -> ExperimentRunCtx:
    """Create an ExperimentRunCtx with minimal required fields for testing."""
    config = ExperimentConfig(
        project_path=Path("/tmp/test-project"),
        environment_name="test-env",
        gui_mode_override=gui_mode_override,
    )
    return ExperimentRunCtx(
        config=config,
        test_execution_mode=test_execution_mode,
        hypervisor_type=hypervisor_type,
    )


# --- is_interrupted ---

class TestIsInterrupted:
    def test_false_initially(self):
        ctx = _make_ctx()
        assert ctx.is_interrupted is False

    def test_true_after_set(self):
        ctx = _make_ctx()
        ctx.user_interrupt_event.set()
        assert ctx.is_interrupted is True

    def test_false_after_clear(self):
        ctx = _make_ctx()
        ctx.user_interrupt_event.set()
        ctx.user_interrupt_event.clear()
        assert ctx.is_interrupted is False


# --- is_host_test_mode ---

class TestIsHostTestMode:
    def test_true_when_host(self):
        ctx = _make_ctx(test_execution_mode="host")
        assert ctx.is_host_test_mode is True

    def test_false_when_agent(self):
        ctx = _make_ctx(test_execution_mode="agent")
        assert ctx.is_host_test_mode is False

    def test_false_when_none(self):
        ctx = _make_ctx(test_execution_mode=None)
        assert ctx.is_host_test_mode is False

    def test_false_when_auto(self):
        ctx = _make_ctx(test_execution_mode="auto")
        assert ctx.is_host_test_mode is False


# --- is_host_gui_mode ---

class TestIsHostGuiMode:
    def test_true_with_explicit_host_override(self):
        ctx = _make_ctx(gui_mode_override="host")
        assert ctx.is_host_gui_mode is True

    def test_true_with_host_override_regardless_of_hypervisor(self):
        """Explicit host override wins even for non-QEMU hypervisors."""
        ctx = _make_ctx(gui_mode_override="host", hypervisor_type="virtualbox")
        assert ctx.is_host_gui_mode is True

    def test_false_with_explicit_agent_override(self):
        ctx = _make_ctx(gui_mode_override="agent")
        assert ctx.is_host_gui_mode is False

    def test_false_with_agent_override_even_for_qemu(self):
        """Explicit agent override wins even for QEMU."""
        ctx = _make_ctx(gui_mode_override="agent", hypervisor_type="qemu")
        assert ctx.is_host_gui_mode is False

    def test_auto_detect_qemu(self):
        """QEMU auto-detects to host GUI mode."""
        ctx = _make_ctx(hypervisor_type="qemu")
        assert ctx.is_host_gui_mode is True

    def test_auto_detect_virtualbox(self):
        """VirtualBox auto-detects to agent GUI mode."""
        ctx = _make_ctx(hypervisor_type="virtualbox")
        assert ctx.is_host_gui_mode is False

    def test_auto_detect_none_hypervisor(self):
        """No hypervisor type defaults to agent GUI mode."""
        ctx = _make_ctx(hypervisor_type=None)
        assert ctx.is_host_gui_mode is False


# --- needs_agent ---

class TestNeedsAgent:
    def test_false_when_both_host(self):
        """Full host mode: both test and GUI on host -> no agent needed."""
        ctx = _make_ctx(
            test_execution_mode="host",
            gui_mode_override="host",
        )
        assert ctx.needs_agent is False

    def test_true_when_test_is_agent(self):
        """Agent test mode requires the agent."""
        ctx = _make_ctx(
            test_execution_mode="agent",
            gui_mode_override="host",
        )
        assert ctx.needs_agent is True

    def test_true_when_gui_is_agent(self):
        """Agent GUI mode requires the agent."""
        ctx = _make_ctx(
            test_execution_mode="host",
            gui_mode_override="agent",
        )
        assert ctx.needs_agent is True

    def test_true_when_both_agent(self):
        ctx = _make_ctx(
            test_execution_mode="agent",
            gui_mode_override="agent",
        )
        assert ctx.needs_agent is True

    def test_true_when_defaults(self):
        """Default (no overrides, no hypervisor) needs agent."""
        ctx = _make_ctx()
        assert ctx.needs_agent is True

    def test_false_with_qemu_auto_detect_and_host_test(self):
        """QEMU auto-detects host GUI + explicit host test -> no agent."""
        ctx = _make_ctx(
            test_execution_mode="host",
            hypervisor_type="qemu",
        )
        assert ctx.needs_agent is False

    def test_true_with_qemu_but_agent_test(self):
        """QEMU auto-detects host GUI, but agent test -> still needs agent."""
        ctx = _make_ctx(
            test_execution_mode="agent",
            hypervisor_type="qemu",
        )
        assert ctx.needs_agent is True
