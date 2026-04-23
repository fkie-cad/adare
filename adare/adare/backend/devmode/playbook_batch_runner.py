"""
Batch playbook execution runner for dev mode.

Executes multiple playbooks sequentially with checkpoint restoration.
"""

import glob
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from adare.console import console
from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlaybookBatchResult:
    """Result of single playbook execution in batch."""
    playbook_path: str
    playbook_name: str
    status: StatusEnum
    execution_time: float
    total_actions: int
    successful_actions: int
    failed_actions: int
    total_tests: int
    successful_tests: int
    failed_tests: int
    error_message: str | None
    start_time: datetime
    end_time: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'playbook_path': self.playbook_path,
            'playbook_name': self.playbook_name,
            'status': self.status.name if hasattr(self.status, 'name') else str(self.status),
            'execution_time': self.execution_time,
            'total_actions': self.total_actions,
            'successful_actions': self.successful_actions,
            'failed_actions': self.failed_actions,
            'total_tests': self.total_tests,
            'successful_tests': self.successful_tests,
            'failed_tests': self.failed_tests,
            'error_message': self.error_message,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
        }


class PlaybookBatchSummary:
    """Aggregated results for batch execution."""

    def __init__(
        self,
        results: list[PlaybookBatchResult],
        total_playbooks: int,
        checkpoint_name: str
    ):
        self.results = results
        self.total_playbooks = total_playbooks
        self.checkpoint_name = checkpoint_name

    @property
    def successful_playbooks(self) -> int:
        """Count of successful playbook executions."""
        return len([r for r in self.results if r.status == StatusEnum.SUCCESS])

    @property
    def failed_playbooks(self) -> int:
        """Count of failed playbook executions."""
        return len([r for r in self.results if r.status == StatusEnum.FAILED])

    @property
    def total_duration(self) -> timedelta:
        """Total duration of batch execution."""
        if not self.results:
            return timedelta(seconds=0)
        return timedelta(seconds=sum(r.execution_time for r in self.results))

    @property
    def success_rate(self) -> float:
        """Success rate as percentage (0-100)."""
        if self.total_playbooks == 0:
            return 0.0
        return (self.successful_playbooks / self.total_playbooks) * 100

    def _get_status_display(self, status: StatusEnum) -> tuple[str, str]:
        """Get display icon and style for a status."""
        if status == StatusEnum.SUCCESS:
            return "✓", "green"
        if status == StatusEnum.FAILED:
            return "✗", "red"
        return "⚠", "yellow"

    def print_summary(self) -> None:
        """Print formatted summary table using Rich console."""
        from rich.table import Table

        console.print()
        console.print("Batch Execution Summary", style="bold underline")
        console.print("══════════════════════════════════════════════════════", style="bold")
        console.print()
        console.print(f"Checkpoint: [cyan]{self.checkpoint_name}[/cyan] (created, preserved for reuse)")
        console.print()

        # Create results table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Playbook", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Duration", justify="right", style="yellow")
        table.add_column("Actions", justify="right")
        table.add_column("Tests", justify="right")

        for result in self.results:
            status_icon, status_style = self._get_status_display(result.status)
            duration_str = f"{result.execution_time:.1f}s"
            actions_str = f"{result.successful_actions}/{result.total_actions}"
            tests_str = f"{result.successful_tests}/{result.total_tests}"

            table.add_row(
                result.playbook_name,
                f"[{status_style}]{status_icon}[/{status_style}]",
                duration_str,
                actions_str,
                tests_str
            )

        console.print(table)
        console.print()

        # Print statistics
        console.print("Statistics:", style="bold")
        console.print(f"  Total Playbooks: {self.total_playbooks}")
        console.print(f"  Successful: {self.successful_playbooks} ({self.success_rate:.1f}%)")
        console.print(f"  Failed: {self.failed_playbooks} ({100 - self.success_rate:.1f}%)")
        console.print(f"  Total Duration: {self.total_duration.total_seconds():.1f}s")

        # Calculate aggregate action/test stats
        total_actions = sum(r.total_actions for r in self.results)
        successful_actions = sum(r.successful_actions for r in self.results)
        total_tests = sum(r.total_tests for r in self.results)
        successful_tests = sum(r.successful_tests for r in self.results)

        if total_actions > 0:
            action_rate = (successful_actions / total_actions) * 100
            console.print(f"  Total Actions: {successful_actions}/{total_actions} ({action_rate:.1f}%)")
        if total_tests > 0:
            test_rate = (successful_tests / total_tests) * 100
            console.print(f"  Total Tests: {successful_tests}/{total_tests} ({test_rate:.1f}%)")

        console.print()
        console.print(f"Checkpoint Restores: {len(self.results)}/{len(self.results)} successful", style="green")
        console.print()
        console.print(f"[dim]Tip: Checkpoint '{self.checkpoint_name}' has been preserved.[/dim]")
        console.print(f"[dim]     Delete with: adare dev checkpoint-delete {self.checkpoint_name}[/dim]")
        console.print()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'summary': {
                'total_playbooks': self.total_playbooks,
                'successful': self.successful_playbooks,
                'failed': self.failed_playbooks,
                'success_rate': self.success_rate,
                'total_duration_seconds': self.total_duration.total_seconds(),
                'checkpoint_name': self.checkpoint_name
            },
            'results': [result.to_dict() for result in self.results]
        }


class PlaybookBatchRunner:
    """Orchestrates batch playbook execution with checkpoints."""

    def __init__(self, session: 'DevModeSession'):
        """
        Initialize batch runner.

        Args:
            session: DevModeSession to use for execution
        """
        self.session = session

    def _resolve_playbook_paths(self, patterns: list[str]) -> list[Path]:
        """
        Resolve glob patterns to concrete playbook paths.

        Args:
            patterns: List of file paths or glob patterns

        Returns:
            List of existing playbook file paths
        """
        all_paths = []
        for pattern in patterns:
            if '*' in pattern or '?' in pattern:
                # Glob pattern
                matches = glob.glob(pattern, recursive=True)
                all_paths.extend(Path(p) for p in matches)
            else:
                # Explicit path
                all_paths.append(Path(pattern))

        # Filter to existing files only
        existing_paths = [p for p in all_paths if p.exists() and p.is_file()]

        # Deduplicate while preserving order
        seen = set()
        unique_paths = []
        for p in existing_paths:
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                unique_paths.append(resolved)

        return unique_paths

    async def execute_batch(
        self,
        playbook_patterns: list[str],
        checkpoint_name: str,
        timeout: int,
        console_ulid: str | None
    ) -> PlaybookBatchSummary:
        """
        Execute batch of playbooks with checkpoint restoration.

        Args:
            playbook_patterns: List of file paths or glob patterns
            checkpoint_name: Name for the base checkpoint
            timeout: Checkpoint restore timeout in seconds
            console_ulid: Optional console ULID for flow events

        Returns:
            PlaybookBatchSummary with execution results

        Raises:
            RuntimeError: If critical errors occur (checkpoint creation/restore failure)
        """
        start_time = datetime.now(UTC)

        # 1. Resolve playbook paths
        playbook_paths = self._resolve_playbook_paths(playbook_patterns)

        if not playbook_paths:
            from adare.exceptions import LoggedErrorException
            raise LoggedErrorException(
                log,
                'No playbooks found matching patterns',
                possible_solutions=[
                    f'Patterns: {playbook_patterns}',
                    'Check paths and try: ls experiments/*/playbook.yml'
                ]
            )

        log.info(f"Resolved {len(playbook_paths)} playbook(s) from patterns")
        for p in playbook_paths:
            log.debug(f"  - {p}")

        # 2. Create base checkpoint (CRITICAL)
        log.info(f"Creating base checkpoint '{checkpoint_name}'...")
        try:
            # Delete existing checkpoint with same name if it exists
            from adare.database.api.devmode import DevModeApi
            with DevModeApi() as api:
                existing = api.get_checkpoint(self.session.session_id, checkpoint_name)
                if existing:
                    log.warning(f"Checkpoint '{checkpoint_name}' already exists, deleting...")
                    # Delete from VM first
                    if self.session.experiment_ctx.hypervisor_type == 'qemu':
                        try:
                            self.session.experiment_ctx.vm.delete_external_snapshot(
                                snapshot_name=existing.snapshot_name,
                                memory_path=existing.memory_file_path,
                                disk_path=existing.disk_file_path
                            )
                        except Exception as e:
                            log.warning(f"Failed to delete existing snapshot files: {e}")
                    # Delete from database
                    api.delete_checkpoint(self.session.session_id, checkpoint_name)

            checkpoint_result = await self.session.create_checkpoint(checkpoint_name, "Base checkpoint for batch execution")
            if not checkpoint_result.success:
                error_msg = checkpoint_result.error.message if checkpoint_result.error else "Unknown error"
                raise RuntimeError(
                    f"Failed to create base checkpoint '{checkpoint_name}': {error_msg}. "
                    "Check VM state and disk space."
                )
        except Exception as e:
            raise RuntimeError(
                f"Failed to create base checkpoint '{checkpoint_name}': {e}"
            )

        log.info(f"Base checkpoint '{checkpoint_name}' created successfully")

        # 3. Execute playbooks sequentially
        results = []
        for idx, playbook_path in enumerate(playbook_paths, 1):
            console.print(f"\n[bold cyan][{idx}/{len(playbook_paths)}] Executing: {playbook_path.name}[/bold cyan]")

            result = await self._execute_single_playbook(playbook_path)
            results.append(result)

            # Print immediate result
            status_icon, status_color = self._get_status_display(result.status)
            console.print(f"  [{status_color}]{status_icon}[/{status_color}] "
                         f"{result.execution_time:.1f}s - "
                         f"Actions: {result.successful_actions}/{result.total_actions}, "
                         f"Tests: {result.successful_tests}/{result.total_tests}")

            if result.error_message:
                console.print(f"  [red]Error: {result.error_message}[/red]")

            # Restore checkpoint after each playbook (CRITICAL)
            if idx < len(playbook_paths):  # Don't restore after last playbook
                console.print(f"  [dim]Restoring checkpoint '{checkpoint_name}'...[/dim]")
                try:
                    restore_result = await self.session.restore_checkpoint(checkpoint_name)
                    if not restore_result.success:
                        error_msg = restore_result.error.message if restore_result.error else "Unknown error"
                        raise RuntimeError(
                            f"Failed to restore checkpoint '{checkpoint_name}' after playbook {idx}: {error_msg}. "
                            f"Stopping batch to prevent state corruption. "
                            f"Results: {len(results)}/{len(playbook_paths)} playbooks completed."
                        )
                except Exception as e:
                    raise RuntimeError(
                        f"Failed to restore checkpoint '{checkpoint_name}': {e}"
                    )

        # 4. Create summary
        summary = PlaybookBatchSummary(
            results=results,
            total_playbooks=len(playbook_paths),
            checkpoint_name=checkpoint_name
        )

        end_time = datetime.now(UTC)
        log.info(f"Batch execution completed in {(end_time - start_time).total_seconds():.1f}s")

        return summary

    async def _execute_single_playbook(self, playbook_path: Path) -> PlaybookBatchResult:
        """Execute a single playbook and return result."""
        start_time = datetime.now(UTC)

        try:
            # Parse playbook
            from adare.types.playbook import parse_playbook_file
            playbook = parse_playbook_file(playbook_path)

            # Execute playbook
            execution_result = await self.session.execute_playbook(
                playbook,
                experiment_dir=playbook_path.parent
            )

            end_time = datetime.now(UTC)
            execution_time = (end_time - start_time).total_seconds()

            # Determine status
            if execution_result.successful_actions == execution_result.total_actions:
                status = StatusEnum.SUCCESS
                error_msg = None
            else:
                status = StatusEnum.FAILED
                error_msg = f"{execution_result.failed_actions} action(s) failed"

            return PlaybookBatchResult(
                playbook_path=str(playbook_path),
                playbook_name=playbook_path.name,
                status=status,
                execution_time=execution_time,
                total_actions=execution_result.total_actions,
                successful_actions=execution_result.successful_actions,
                failed_actions=execution_result.failed_actions,
                total_tests=execution_result.total_tests,
                successful_tests=execution_result.successful_tests,
                failed_tests=execution_result.failed_tests,
                error_message=error_msg,
                start_time=start_time,
                end_time=end_time
            )

        except Exception as e:
            end_time = datetime.now(UTC)
            execution_time = (end_time - start_time).total_seconds()

            log.error(f"Failed to execute playbook {playbook_path}: {e}", exc_info=True)

            return PlaybookBatchResult(
                playbook_path=str(playbook_path),
                playbook_name=playbook_path.name,
                status=StatusEnum.FAILED,
                execution_time=execution_time,
                total_actions=0,
                successful_actions=0,
                failed_actions=0,
                total_tests=0,
                successful_tests=0,
                failed_tests=0,
                error_message=str(e),
                start_time=start_time,
                end_time=end_time
            )

    def _get_status_display(self, status: StatusEnum) -> tuple[str, str]:
        """Get display icon and style for a status."""
        if status == StatusEnum.SUCCESS:
            return "✓", "green"
        if status == StatusEnum.FAILED:
            return "✗", "red"
        return "⚠", "yellow"
