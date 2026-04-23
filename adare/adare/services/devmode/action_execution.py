"""
Action and playbook execution mixin for DevMode service.

Handles: execute_action, execute_playbook, execute_playbook_batch.
"""

import asyncio
import logging
import time
from pathlib import Path

import yaml
from sqlalchemy.exc import SQLAlchemyError

from adare.backend.devmode.playbook_batch_runner import PlaybookBatchSummary
from adare.core.dto.devmode import (
    DevActionExecuteRequest,
    DevActionResult,
    DevPlaybookBatchExecuteRequest,
    DevPlaybookExecuteRequest,
    DevPlaybookResult,
)
from adare.core.result import Result
from adare.services.devmode.input_parsing import (
    fetch_playbook_from_url,
    parse_action_from_file,
    parse_action_from_stdin,
    parse_action_from_yaml,
    parse_playbook_from_file,
    parse_playbook_from_stdin,
)

log = logging.getLogger(__name__)


class ActionExecutionMixin:
    """Mixin providing action/playbook execution methods for DevModeService."""

    async def _execute_action_async(self, request: DevActionExecuteRequest):
        """
        Execute a single action in a single event loop.

        This async helper ensures the entire action execution (session retrieval,
        parsing, and execution) happens in one event loop, keeping the WebSocket
        message handler alive throughout.

        Args:
            request: DevActionExecuteRequest with session ID and action details

        Returns:
            Tuple of (action_result, execution_time)

        Raises:
            RuntimeError: If session not found or action execution fails
            ValueError: If invalid action source
        """
        # Get or restore session (stays in same event loop)
        session = await self._manager.get_or_restore_session(request.session_id)
        if not session:
            raise RuntimeError(
                f"Dev session '{request.session_id}' not found or could not be restored"
            )

        # Parse action based on source
        if request.action_source == 'file':
            action = parse_action_from_file(request.action_content)
        elif request.action_source == 'yaml':
            action = parse_action_from_yaml(request.action_content)
        elif request.action_source == 'stdin':
            action = parse_action_from_stdin()
        else:
            raise ValueError(f"Invalid action source '{request.action_source}'")

        # Execute action (in same event loop!)
        start_time = time.time()
        action_result = await session.execute_action(action)
        execution_time = time.time() - start_time

        return action_result, execution_time

    def execute_action(self, request: DevActionExecuteRequest) -> Result[DevActionResult]:
        """
        Execute a single action.

        Args:
            request: DevActionExecuteRequest with session ID, source, and content

        Returns:
            Result[DevActionResult] with execution result
        """
        try:
            # CRITICAL: Execute entire flow in ONE asyncio.run() call
            # This keeps the WebSocket message_handler_task alive throughout execution
            action_result, execution_time = asyncio.run(
                self._execute_action_async(request)
            )

            return Result.ok(DevActionResult(
                success=action_result.success,
                message=action_result.message,
                execution_time=execution_time,
                coordinates=action_result.coordinates,
                data=action_result.data
            ))

        except RuntimeError as e:
            # Raised by _execute_action_async when session not found
            return Result.fail(
                "SESSION_NOT_FOUND",
                str(e),
                [
                    "Check active sessions with: adare dev list",
                    "VM may not be running - check with hypervisor tools"
                ]
            )
        except ValueError as e:
            # Raised by _execute_action_async for invalid action source
            return Result.fail(
                "INVALID_ACTION_SOURCE",
                str(e),
                ["Valid sources: file, yaml, stdin"]
            )
        except yaml.YAMLError as e:
            return Result.fail(
                "YAML_PARSE_ERROR",
                f"Failed to parse action YAML: {str(e)}",
                ["Check YAML syntax", "Ensure action format is valid"]
            )
        except FileNotFoundError as e:
            return Result.fail(
                "FILE_NOT_FOUND",
                f"Action file not found: {str(e)}",
                ["Check file path is correct"]
            )
        except (OSError, SQLAlchemyError, asyncio.CancelledError) as e:
            log.error(f"Error executing action: {e}", exc_info=True)
            return Result.fail(
                "ACTION_EXECUTION_ERROR",
                f"Action execution failed: {str(e)}",
                ["Check logs for details", "Verify action syntax"]
            )

    async def _execute_playbook_async(self, request: DevPlaybookExecuteRequest):
        """
        Execute playbook in a single event loop.

        This async helper ensures the entire playbook execution (session retrieval,
        parsing, and execution) happens in one event loop, keeping the WebSocket
        message handler alive throughout.

        Args:
            request: DevPlaybookExecuteRequest with session ID and playbook details

        Returns:
            Tuple of (playbook_result, execution_time)

        Raises:
            RuntimeError: If session not found or playbook execution fails
            ValueError: If invalid playbook source
        """
        # Get or restore session (stays in same event loop)
        session = await self._manager.get_or_restore_session(
            request.session_id,
            console_ulid=request.console_ulid
        )
        if not session:
            raise RuntimeError(
                f"Dev session '{request.session_id}' not found or could not be restored"
            )

        # Parse playbook based on source
        experiment_dir = None
        if request.playbook_source == 'file':
            # Identify experiment directory as parent of playbook file
            playbook_path = Path(request.playbook_content)
            experiment_dir = playbook_path.parent.resolve()
            log.info(f" inferred experiment directory from playbook file: {experiment_dir}")

            playbook = parse_playbook_from_file(request.playbook_content)
        elif request.playbook_source == 'url':
            playbook = fetch_playbook_from_url(request.playbook_content)
        elif request.playbook_source == 'stdin':
            playbook = parse_playbook_from_stdin()
        else:
            raise ValueError(f"Invalid playbook source '{request.playbook_source}'")

        # Parse indices if provided (now that we know action count)
        parsed_indices = None
        if request.indices:
            from adare.cli.dev import parse_indices_with_bounds
            try:
                parsed_indices = parse_indices_with_bounds(request.indices, len(playbook.actions))
            except ValueError as e:
                raise ValueError(f"Invalid indices specification: {e}") from e

        # Restore to initial checkpoint if requested
        if request.restore_initial:
            log.info("--restore flag set: restoring to initial checkpoint before playbook execution")
            restore_result = await session.restore_checkpoint('initial')

            if not restore_result.success:
                error_msg = restore_result.error.message if restore_result.error else "Unknown error"
                raise RuntimeError(
                    f"Failed to restore initial checkpoint: {error_msg}. "
                    "Aborting playbook execution to avoid running with stale state."
                )

            log.info("Successfully restored to initial checkpoint")

        # Execute playbook (in same event loop!)
        start_time = time.time()
        playbook_result = await session.execute_playbook(
            playbook,
            experiment_dir=experiment_dir,
            indices=parsed_indices
        )
        execution_time = time.time() - start_time

        return playbook_result, execution_time

    def execute_playbook(self, request: DevPlaybookExecuteRequest) -> Result[DevPlaybookResult]:
        """
        Execute a playbook.

        Args:
            request: DevPlaybookExecuteRequest with session ID, source, and content

        Returns:
            Result[DevPlaybookResult] with execution statistics
        """
        try:
            # CRITICAL: Execute entire flow in ONE asyncio.run() call
            # This keeps the WebSocket message_handler_task alive throughout execution
            playbook_result, execution_time = asyncio.run(
                self._execute_playbook_async(request)
            )

            # Convert action results
            action_results = [
                DevActionResult(
                    success=ar.success,
                    message=ar.message,
                    execution_time=0.0,  # Individual timing not tracked
                    coordinates=ar.coordinates,
                    data=ar.data
                )
                for ar in playbook_result.action_results
            ]

            return Result.ok(DevPlaybookResult(
                success=playbook_result.success,
                total_actions=playbook_result.total_actions,
                successful_actions=playbook_result.successful_actions,
                failed_actions=playbook_result.failed_actions,
                execution_time=execution_time,
                action_results=action_results,
                error_message=playbook_result.error_message,
                test_stats={
                    'total_tests': playbook_result.total_tests,
                    'successful_tests': playbook_result.successful_tests,
                    'failed_tests': playbook_result.failed_tests,
                } if playbook_result.total_tests > 0 else None
            ))

        except RuntimeError as e:
            # Raised by _execute_playbook_async when session not found
            return Result.fail(
                "SESSION_NOT_FOUND",
                str(e),
                [
                    "Check active sessions with: adare dev list",
                    "VM may not be running - check with hypervisor tools"
                ]
            )
        except ValueError as e:
            # Raised by _execute_playbook_async for invalid playbook source
            return Result.fail(
                "INVALID_PLAYBOOK_SOURCE",
                str(e),
                ["Valid sources: file, url, stdin"]
            )
        except yaml.YAMLError as e:
            return Result.fail(
                "YAML_PARSE_ERROR",
                f"Failed to parse playbook YAML: {str(e)}",
                ["Check YAML syntax", "Ensure playbook format is valid"]
            )
        except FileNotFoundError as e:
            return Result.fail(
                "FILE_NOT_FOUND",
                f"Playbook file not found: {str(e)}",
                ["Check file path is correct"]
            )
        except (OSError, SQLAlchemyError, asyncio.CancelledError) as e:
            log.error(f"Error executing playbook: {e}", exc_info=True)
            return Result.fail(
                "PLAYBOOK_EXECUTION_ERROR",
                f"Playbook execution failed: {str(e)}",
                ["Check logs for details", "Verify playbook syntax"]
            )

    def execute_playbook_batch(self, request: DevPlaybookBatchExecuteRequest) -> Result[PlaybookBatchSummary]:
        """
        Execute batch of playbooks with checkpoint restoration.

        Args:
            request: DevPlaybookBatchExecuteRequest

        Returns:
            Result[PlaybookBatchSummary]
        """
        try:
            summary = asyncio.run(self._manager.execute_playbook_batch(
                session_id=request.session_id,
                playbook_patterns=request.playbook_patterns,
                checkpoint_name=request.checkpoint_name,
                timeout=request.timeout,
                console_ulid=request.console_ulid
            ))

            return Result.ok(summary)

        except RuntimeError as e:
            log.error(f"Batch execution failed: {e}", exc_info=True)
            return Result.fail(
                "BATCH_EXECUTION_FAILED",
                str(e),
                ["Check session status", "Check playbook paths", "Check VM state"]
            )

        except (OSError, SQLAlchemyError, asyncio.CancelledError) as e:
            log.error(f"Error executing playbook batch: {e}", exc_info=True)
            return Result.fail(
                "INTERNAL_ERROR",
                f"Unexpected error: {str(e)}",
                ["Check logs for details"]
            )
