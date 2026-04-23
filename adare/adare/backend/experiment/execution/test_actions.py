"""
Executor for test actions.

Handles routing test execution to either VM-side, host-side, or host-mode test executors.
"""

import logging
from pathlib import Path

from adare.types.playbook import ActionTestAction

from .base import ActionResult, TestExecutionMode

log = logging.getLogger(__name__)


class TestActionsExecutor:
    """Handles execution of test actions with host/VM/host-mode routing."""

    def __init__(self, experiment_run_directory: Path | None = None, playbook = None):
        """
        Initialize test actions executor.

        Args:
            experiment_run_directory: Run directory for artifacts
            playbook: Playbook reference for test access
        """
        self.experiment_run_directory = experiment_run_directory
        self.playbook = playbook
        self.test_loader = None
        self.host_test_executor = None
        self.guest_to_host_test_executor = None
        self.test_execution_mode: TestExecutionMode | None = None

    def set_test_loader(self, test_loader):
        """Set the test loader after initialization."""
        self.test_loader = test_loader

    def set_test_execution_mode(self, mode: TestExecutionMode):
        """Set the test execution mode."""
        self.test_execution_mode = mode
        log.info(f"Test Executor: test execution mode set to {mode.value}")

    def set_guest_to_host_test_executor(self, executor):
        """Set the host-mode test executor (pre-created with QGA proxies)."""
        self.guest_to_host_test_executor = executor
        log.debug("Test Executor: GuestToHostTestExecutor set")

    async def execute_test(self, action: ActionTestAction, websocket_client,
                          target_resolver, parent_event_id: str = None,
                          event_emitter = None, execution_context: dict = None,
                          action_executor = None) -> ActionResult:
        """Execute individual test action with host/VM/host-mode routing."""
        try:
            if not self.test_loader:
                return ActionResult(success=False, message="Test loader not available")

            # Resolve test with runtime context
            resolved_test = await self.test_loader.resolve_test_with_runtime_context(
                action.name,
                execution_context or {}
            )
            if not resolved_test:
                return ActionResult(
                    success=False,
                    message=f"Test '{action.name}' not found in playbook tests"
                )

            # Check if this is a host-side test (visual tests with execute_on_host=True)
            test_class = self.test_loader.get_test_class(action.name)

            if test_class and getattr(test_class, 'execute_on_host', False):
                # HOST-SIDE EXECUTION (visual tests — unchanged path)
                return await self._execute_host_side_test(
                    action, resolved_test, test_class, target_resolver, action_executor
                )

            if self.test_execution_mode == TestExecutionMode.HOST:
                # HOST-MODE EXECUTION — all tests via QGA (no agent needed)
                return await self._execute_host_mode_test(action, resolved_test)

            # VM-SIDE EXECUTION via WebSocket (existing code path)
            return await self._execute_vm_side_test(action, resolved_test, websocket_client)

        except ValueError as e:
            log.error(f"Test execution failed: {e}")
            return ActionResult(success=False, message=str(e))
        except Exception as e:
            error_msg = str(e)
            if "No testset loaded" in error_msg or "testset" in error_msg.lower():
                return ActionResult(
                    success=False,
                    message="No tests loaded - ensure playbook.yml contains tests section and loads successfully before test actions"
                )
            log.error(f"Test execution failed: {e}", exc_info=True)
            return ActionResult(success=False, message=error_msg)

    async def _execute_host_side_test(self, action, resolved_test, test_class,
                                      target_resolver, action_executor) -> ActionResult:
        """Route test to existing HostTestExecutor (for visual tests with execute_on_host=True)."""
        log.debug(f"Test Executor: Routing test '{action.name}' to host executor (execute_on_host)")

        if not self.host_test_executor:
            from adare.backend.experiment.host_test_executor import HostTestExecutor

            playbook_dir = getattr(self.playbook, 'directory', self.experiment_run_directory)

            self.host_test_executor = HostTestExecutor(
                action_executor=action_executor,
                mcp_client=target_resolver.mcp_client,
                playbook_dir=playbook_dir,
                experiment_dir=self.experiment_run_directory
            )
            log.debug("Test Executor: Created HostTestExecutor")

        test_instance = await self.test_loader.structure_host_test(action.name, resolved_test)
        test_result = await self.host_test_executor.execute_host_test(test_instance)

        from adare.backend.experiment.test_result_processor import TestResultProcessor
        expect_to_fail = resolved_test.get('expect_to_fail', False)
        result_dict = {
            'status': test_result.status,
            'details': test_result.details if hasattr(test_result, 'details') else []
        }
        return TestResultProcessor.process_test_result(action.name, result_dict, expect_to_fail)

    async def _execute_host_mode_test(self, action, resolved_test) -> ActionResult:
        """Route test to GuestToHostTestExecutor (QGA-based, no agent)."""
        log.debug(f"Test Executor: Routing test '{action.name}' to host-mode executor (QGA)")

        if not self.guest_to_host_test_executor:
            return ActionResult(
                success=False,
                message="Host-mode test executor not available — ensure test_execution_mode=HOST is configured"
            )

        # Get the test function name from playbook
        test_function = resolved_test.get('function', '')

        # Structure test instance
        test_instance = await self.test_loader.structure_host_test(action.name, resolved_test)

        # Execute via host-mode executor
        test_result = await self.guest_to_host_test_executor.execute_test(
            test_name=action.name,
            test_function=test_function,
            test_instance=test_instance,
        )

        from adare.backend.experiment.test_result_processor import TestResultProcessor
        expect_to_fail = resolved_test.get('expect_to_fail', False)
        result_dict = {
            'status': test_result.status,
            'details': test_result.details if hasattr(test_result, 'details') else []
        }
        return TestResultProcessor.process_test_result(action.name, result_dict, expect_to_fail)

    async def _execute_vm_side_test(self, action, resolved_test, websocket_client) -> ActionResult:
        """Route test to VM via WebSocket (existing agent-based path)."""
        log.debug(f"Test Executor: Routing test '{action.name}' to VM executor")

        test_timeout = action.timeout if action.timeout is not None else resolved_test.get('timeout', 120.0)
        websocket_timeout = test_timeout + 10.0

        log.info(f"Test '{action.name}' timeout: {test_timeout}s (WebSocket timeout: {websocket_timeout}s)")

        result = await websocket_client.run_test(action.name, resolved_test, timeout=websocket_timeout)

        expect_to_fail = resolved_test.get('expect_to_fail', False)

        from adare.backend.experiment.test_result_processor import TestResultProcessor
        return TestResultProcessor.process_test_result(action.name, result, expect_to_fail)
