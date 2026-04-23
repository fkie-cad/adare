"""
Host Test Executor for ADARE.

This module handles execution of host-side tests, providing service injection
via HostTestContext and proper async execution handling.
"""

import asyncio
import logging
from pathlib import Path

from adare.backend.experiment.host_test_context import HostTestContext
from adarelib.event.event import TestResult
from adarelib.testset.basictest import BasicTest

log = logging.getLogger(__name__)


class HostTestExecutor:
    """
    Executor for host-side tests.

    This executor handles tests marked with execute_on_host=True,
    providing them with a HostTestContext containing all necessary
    services for visual analysis, screenshots, and VM file access.
    """

    def __init__(
        self,
        action_executor,
        mcp_client,
        playbook_dir: Path,
        experiment_dir: Path
    ):
        """
        Initialize host test executor.

        Args:
            action_executor: ActionExecutor instance (for pull reuse)
            mcp_client: MCP client for CV server
            playbook_dir: Path to playbook directory
            experiment_dir: Path to experiment directory
        """
        self.action_executor = action_executor
        self.mcp_client = mcp_client
        self.playbook_dir = playbook_dir
        self.experiment_dir = experiment_dir

        # Context is created lazily when needed
        self._context: HostTestContext | None = None

    def _get_context(self) -> HostTestContext:
        """
        Get or create HostTestContext.

        Returns:
            HostTestContext instance with all services
        """
        if self._context is None:
            self._context = HostTestContext.create(
                mcp_client=self.mcp_client,
                websocket_client=self.action_executor.client,
                action_executor=self.action_executor,
                playbook_dir=self.playbook_dir,
                experiment_dir=self.experiment_dir
            )
            log.debug("Host Test Executor: Created HostTestContext")

        return self._context

    async def execute_host_test(self, test_instance: BasicTest) -> TestResult:
        """
        Execute a host-side test with service context.

        Args:
            test_instance: Structured test instance (BasicTest subclass)

        Returns:
            TestResult from test execution

        Raises:
            TypeError: If test is not async or has wrong signature
            RuntimeError: If test execution fails unexpectedly
        """
        test_name = getattr(test_instance, 'name', 'unknown')
        test_class = test_instance.__class__.__name__

        try:
            log.debug(f"Host Test Executor: Executing {test_class} '{test_name}'")

            # Get service context
            context = self._get_context()

            # Check if test method is async
            if not asyncio.iscoroutinefunction(test_instance.test):
                error_msg = (
                    f"Host-side test {test_class} must have async test() method. "
                    f"Expected: async def test(self, context: HostTestContext)"
                )
                log.error(f"Host Test Executor: {error_msg}")
                return TestResult.execution_error(
                    TypeError(error_msg),
                    "Host test must be async"
                )

            # Execute test with context
            log.debug(f"Host Test Executor: Calling test method for '{test_name}'")
            result = await test_instance.test(context)

            # Validate result type
            if not isinstance(result, TestResult):
                error_msg = (
                    f"Host-side test {test_class} returned invalid type {type(result)}. "
                    f"Expected: TestResult"
                )
                log.error(f"Host Test Executor: {error_msg}")
                return TestResult.execution_error(
                    TypeError(error_msg),
                    "Invalid return type from test"
                )

            log.debug(f"Host Test Executor: Test '{test_name}' completed with status {result.status}")
            return result

        except TypeError as e:
            # Signature mismatch or type errors
            log.error(f"Host Test Executor: Type error executing '{test_name}': {e}")
            return TestResult.execution_error(e, f"Test signature error: {e}")

        except Exception as e:
            # Unexpected errors during test execution
            log.error(f"Host Test Executor: Unexpected error executing '{test_name}': {e}", exc_info=True)
            return TestResult.execution_error(e, f"Test execution failed: {e}")

    def supports_test(self, test_class: type) -> bool:
        """
        Check if a test class is supported by this executor.

        Args:
            test_class: Test class to check

        Returns:
            True if test has execute_on_host=True flag
        """
        return getattr(test_class, 'execute_on_host', False)
