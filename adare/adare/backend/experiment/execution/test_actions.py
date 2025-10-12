"""
Executor for test actions.

Handles routing test execution to either VM-side or host-side test executors.
"""

import logging
from pathlib import Path
from typing import Optional

from adare.types.playbook import ActionTestAction
from .base import ActionResult

log = logging.getLogger(__name__)


class TestActionsExecutor:
    """Handles execution of test actions with host/VM routing."""

    def __init__(self, experiment_run_directory: Optional[Path] = None, playbook = None):
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

    def set_test_loader(self, test_loader):
        """Set the test loader after initialization."""
        self.test_loader = test_loader

    async def execute_test(self, action: ActionTestAction, websocket_client,
                          target_resolver, parent_event_id: str = None,
                          event_emitter = None, execution_context: dict = None,
                          action_executor = None) -> ActionResult:
        """Execute individual test action with host/VM routing."""
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

            # Check if this is a host-side test
            test_class = self.test_loader.get_test_class(action.name)

            if test_class and getattr(test_class, 'execute_on_host', False):
                # HOST-SIDE EXECUTION
                log.debug(f"Test Executor: Routing test '{action.name}' to host executor")

                # Create host test executor if not exists (lazy init)
                if not self.host_test_executor:
                    from adare.backend.experiment.host_test_executor import HostTestExecutor

                    # Get playbook directory
                    playbook_dir = getattr(self.playbook, 'directory', self.experiment_run_directory)

                    self.host_test_executor = HostTestExecutor(
                        action_executor=action_executor,
                        mcp_client=target_resolver.mcp_client,
                        playbook_dir=playbook_dir,
                        experiment_dir=self.experiment_run_directory
                    )
                    log.debug("Test Executor: Created HostTestExecutor")

                # Structure test instance for host execution
                test_instance = await self.test_loader.structure_host_test(action.name, resolved_test)

                # Execute on host
                test_result = await self.host_test_executor.execute_host_test(test_instance)

                # Process result
                from adare.backend.experiment.test_result_processor import TestResultProcessor
                expect_to_fail = resolved_test.get('expect_to_fail', False)

                # Convert TestResult to dict format expected by processor
                result_dict = {
                    'status': test_result.status,
                    'details': test_result.details if hasattr(test_result, 'details') else []
                }

                return TestResultProcessor.process_test_result(action.name, result_dict, expect_to_fail)

            else:
                # VM-SIDE EXECUTION (existing code path)
                log.debug(f"Test Executor: Routing test '{action.name}' to VM executor")

                # Send resolved test to VM for execution
                result = await websocket_client.run_test(action.name, resolved_test)

                # Extract expect_to_fail flag from resolved test
                expect_to_fail = resolved_test.get('expect_to_fail', False)

                # Use TestResultProcessor to handle result processing
                from adare.backend.experiment.test_result_processor import TestResultProcessor
                return TestResultProcessor.process_test_result(action.name, result, expect_to_fail)

        except ValueError as e:
            # Structuring or validation errors
            log.error(f"Test execution failed: {e}")
            return ActionResult(success=False, message=str(e))
        except Exception as e:
            error_msg = str(e)
            if "No testset loaded" in error_msg or "testset" in error_msg.lower():
                return ActionResult(
                    success=False,
                    message=f"No tests loaded - ensure playbook.yml contains tests section and loads successfully before test actions"
                )
            log.error(f"Test execution failed: {e}", exc_info=True)
            return ActionResult(success=False, message=error_msg)
