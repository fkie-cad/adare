# external imports
import asyncio
import fnmatch
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

# internal imports
from adare.database.api.experiment import ExperimentApi
from adare.exceptions import LoggedErrorException
from adarelib.constants import StatusEnum
from adare.console import console

# configure logging
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExperimentResult:
    """Result of running a single experiment in a single environment.

    This class is immutable to ensure result integrity throughout the batch execution.
    """
    environment: str
    experiment: str
    status: StatusEnum
    duration: timedelta
    error_message: Optional[str] = None
    run_ulid: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Validate the result data after initialization."""
        if not self.environment.strip():
            raise ValueError("Environment name cannot be empty")
        if not self.experiment.strip():
            raise ValueError("Experiment name cannot be empty")
        if self.duration.total_seconds() < 0:
            raise ValueError("Duration cannot be negative")


@dataclass(frozen=True)
class BatchRunSummary:
    """Summary of a batch run containing multiple experiment-environment combinations.

    This class provides statistics and reporting for batch execution results.
    """
    results: List[ExperimentResult]
    total_combinations: int
    total_duration: timedelta

    def __post_init__(self) -> None:
        """Validate the summary data after initialization."""
        if self.total_combinations < 0:
            raise ValueError("Total combinations cannot be negative")
        if len(self.results) > self.total_combinations:
            raise ValueError("Results count cannot exceed total combinations")

    @property
    def successful_runs(self) -> int:
        """Count of successful experiment runs."""
        return len([r for r in self.results if r.status == StatusEnum.SUCCESS])

    @property
    def failed_runs(self) -> int:
        """Count of failed experiment runs."""
        return len([r for r in self.results if r.status == StatusEnum.FAILED])

    @property
    def interrupted_runs(self) -> int:
        """Count of interrupted experiment runs."""
        return len([r for r in self.results if r.status == StatusEnum.INTERRUPTED])

    @property
    def success_rate(self) -> float:
        """Success rate as a percentage (0-100)."""
        if self.total_combinations == 0:
            return 0.0
        return (self.successful_runs / self.total_combinations) * 100

    def _print_single_result(self, result: ExperimentResult) -> None:
        """Print a brief summary for a single experiment result."""
        if result.status == StatusEnum.SUCCESS:
            console.print(f"[green]✓[/green] {result.experiment} completed successfully in {result.duration.total_seconds():.1f}s")
        else:
            console.print(f"[red]✗[/red] {result.experiment} failed in {result.duration.total_seconds():.1f}s")
            if result.error_message:
                console.print(f"  [red]Error: {result.error_message}[/red]")

    def _create_results_table(self) -> Any:
        """Create a Rich table with the batch execution results."""
        from rich.table import Table

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Environment", style="cyan")
        table.add_column("Experiment", style="blue")
        table.add_column("Status", justify="center")
        table.add_column("Duration", justify="right", style="yellow")
        table.add_column("Error", style="red")

        for result in self.results:
            status_icon, status_style = self._get_status_display(result.status)
            duration_str = f"{result.duration.total_seconds():.1f}s"
            error_str = result.error_message or ""

            table.add_row(
                result.environment,
                result.experiment,
                f"[{status_style}]{status_icon}[/{status_style}]",
                duration_str,
                error_str
            )
        return table

    def _get_status_display(self, status: StatusEnum) -> tuple[str, str]:
        """Get the display icon and style for a status."""
        if status == StatusEnum.SUCCESS:
            return "✓", "green"
        elif status == StatusEnum.FAILED:
            return "✗", "red"
        else:  # INTERRUPTED or other
            return "⚠", "yellow"

    def print_summary(self) -> None:
        """Print a formatted summary table using Rich console."""
        # For single experiment, just show a brief summary
        if len(self.results) == 1:
            self._print_single_result(self.results[0])
            return

        # For multiple experiments, show full table
        console.print()
        console.print("Batch Execution Summary", style="bold underline")
        console.print()

        table = self._create_results_table()
        console.print(table)
        console.print()

        # Print statistics
        console.print(f"Summary: {self.successful_runs}/{self.total_combinations} successful ({self.success_rate:.0f}%), "
                     f"Total time: {self.total_duration.total_seconds():.1f}s", style="bold")
        console.print()


class ExperimentEnvironmentMatcher:
    """Handles pattern matching for experiments and environments.

    This class provides functionality to match experiment and environment names
    using glob patterns and validate their compatibility.
    """

    # Glob pattern characters
    _GLOB_CHARS: Set[str] = {'*', '?', '[', ']'}

    def __init__(self, project_path: Path) -> None:
        """Initialize the matcher with a project path.

        Args:
            project_path: Path to the project containing experiments and environments

        Raises:
            ValueError: If project_path is not a valid directory
        """
        if not project_path.exists():
            raise ValueError(f"Project path does not exist: {project_path}")
        if not project_path.is_dir():
            raise ValueError(f"Project path is not a directory: {project_path}")

        self.project_path = project_path

    def has_glob_pattern(self, pattern: str) -> bool:
        """Check if a string contains glob pattern characters.

        Args:
            pattern: String to check for glob patterns

        Returns:
            True if the pattern contains glob characters, False otherwise
        """
        if not pattern:
            return False
        return any(char in pattern for char in self._GLOB_CHARS)

    def match_experiments(self, pattern: str) -> List[str]:
        """Find all experiments matching the given pattern.

        Args:
            pattern: Experiment name pattern (supports glob patterns)

        Returns:
            Sorted list of experiment names matching the pattern

        Raises:
            ValueError: If pattern is empty
        """
        if not pattern.strip():
            raise ValueError("Experiment pattern cannot be empty")

        try:
            with ExperimentApi() as api:
                all_experiments = api.get_experiments(self.project_path)
                experiment_names = [exp.name for exp in all_experiments if exp.name]

                if self.has_glob_pattern(pattern):
                    matched = [name for name in experiment_names if fnmatch.fnmatch(name, pattern)]
                    return sorted(matched)
                else:
                    return [pattern] if pattern in experiment_names else []

        except Exception as e:
            log.error(f"Failed to match experiments with pattern '{pattern}': {e}")
            raise

    def match_environments(self, pattern: str) -> List[str]:
        """Find all environments matching the given pattern.

        Args:
            pattern: Environment name pattern (supports glob patterns)

        Returns:
            Sorted list of environment names matching the pattern

        Raises:
            ValueError: If pattern is empty
        """
        if not pattern.strip():
            raise ValueError("Environment pattern cannot be empty")

        try:
            from adare.database.api.environment import EnvironmentDbApi
            with EnvironmentDbApi() as api:
                all_environments = api.get_environments(self.project_path)
                environment_names = [env.name for env in all_environments if env.name]

                if self.has_glob_pattern(pattern):
                    matched = [name for name in environment_names if fnmatch.fnmatch(name, pattern)]
                    return sorted(matched)
                else:
                    return [pattern] if pattern in environment_names else []

        except Exception as e:
            log.error(f"Failed to match environments with pattern '{pattern}': {e}")
            raise

    def validate_compatibility(self, experiment_name: str, environment_name: str) -> bool:
        """Check if an experiment is compatible with an environment.

        Args:
            experiment_name: Name of the experiment
            environment_name: Name of the environment

        Returns:
            True if the experiment can run in the environment, False otherwise

        Raises:
            ValueError: If either name is empty
        """
        if not experiment_name.strip():
            raise ValueError("Experiment name cannot be empty")
        if not environment_name.strip():
            raise ValueError("Environment name cannot be empty")

        try:
            with ExperimentApi() as api:
                environment = api.get_environment(environment_name, self.project_path.name)
                if environment is None:
                    return False

                experiment = api.get_experiment(experiment_name, environment)
                return experiment is not None

        except Exception as e:
            log.warning(f"Failed to validate compatibility between '{experiment_name}' and '{environment_name}': {e}")
            return False

    def get_valid_combinations(self, exp_pattern: str, env_pattern: str) -> Dict[str, List[str]]:
        """Get all valid experiment-environment combinations.

        Args:
            exp_pattern: Experiment name pattern (supports glob patterns)
            env_pattern: Environment name pattern (supports glob patterns)

        Returns:
            Dictionary mapping environment names to lists of compatible experiment names

        Raises:
            LoggedErrorException: If no experiments, environments, or valid combinations found
        """
        matched_experiments = self.match_experiments(exp_pattern)
        matched_environments = self.match_environments(env_pattern)

        self._validate_matches(exp_pattern, env_pattern, matched_experiments, matched_environments)

        combinations = self._build_combinations(matched_experiments, matched_environments)

        self._validate_combinations(exp_pattern, env_pattern, combinations,
                                   matched_experiments, matched_environments)

        return combinations

    def _validate_matches(self, exp_pattern: str, env_pattern: str,
                         experiments: List[str], environments: List[str]) -> None:
        """Validate that we found matching experiments and environments."""
        if not experiments:
            raise LoggedErrorException(
                log,
                f'No experiments found matching pattern: {exp_pattern}',
                possible_solutions=[
                    f'Check if experiment pattern "{exp_pattern}" is correct',
                    'List available experiments with: adare experiment list',
                    'Create experiments if needed with: adare experiment create <name>'
                ]
            )

        if not environments:
            raise LoggedErrorException(
                log,
                f'No environments found matching pattern: {env_pattern}',
                possible_solutions=[
                    f'Check if environment pattern "{env_pattern}" is correct',
                    'List available environments with: adare environment list',
                    'Create environments if needed with: adare environment create <name>'
                ]
            )

    def _build_combinations(self, experiments: List[str], environments: List[str]) -> Dict[str, List[str]]:
        """Build valid experiment-environment combinations."""
        combinations = {}
        valid_count = 0
        total_possible = len(experiments) * len(environments)

        for env_name in environments:
            valid_experiments = []
            for exp_name in experiments:
                if self.validate_compatibility(exp_name, env_name):
                    valid_experiments.append(exp_name)
                    valid_count += 1

            if valid_experiments:
                combinations[env_name] = sorted(valid_experiments)

        log.info(f'Found {valid_count} valid combinations out of {total_possible} possible '
                f'({len(experiments)} experiments × {len(environments)} environments)')

        return combinations

    def _validate_combinations(self, exp_pattern: str, env_pattern: str,
                              combinations: Dict[str, List[str]],
                              experiments: List[str], environments: List[str]) -> None:
        """Validate that we found at least one valid combination."""
        if not combinations:
            raise LoggedErrorException(
                log,
                f'No valid combinations found between experiments matching "{exp_pattern}" and environments matching "{env_pattern}"',
                possible_solutions=[
                    f'Found experiments: {", ".join(experiments)}',
                    f'Found environments: {", ".join(environments)}',
                    'Check experiment-environment compatibility',
                    'Ensure experiments are properly configured for the target environments'
                ]
            )


class BatchExperimentRunner:
    """Orchestrates batch execution of multiple experiment-environment combinations.

    This class manages the execution flow, progress tracking, and result collection
    for running experiments across multiple environments in a batch operation.
    """

    def __init__(self) -> None:
        """Initialize the batch runner."""
        self.matcher: Optional[ExperimentEnvironmentMatcher] = None
        self.interrupt_requested: bool = False

    async def run_batch(
        self,
        project_path: Path,
        exp_pattern: str,
        env_pattern: str,
        show_flow_console: bool = False,
        **experiment_kwargs: Any
    ) -> BatchRunSummary:
        """Execute batch run for all matching experiment-environment combinations.

        Args:
            project_path: Path to the project
            exp_pattern: Experiment name pattern (supports globs)
            env_pattern: Environment name pattern (supports globs)
            show_flow_console: Whether to show flow console for individual runs (default: False)
            **experiment_kwargs: Additional arguments to pass to experiment_run

        Returns:
            BatchRunSummary with results of all executions

        Raises:
            ValueError: If project_path is invalid or patterns are empty
        """
        if not project_path.exists():
            raise ValueError(f"Project path does not exist: {project_path}")

        start_time = datetime.now(timezone.utc)
        self.matcher = ExperimentEnvironmentMatcher(project_path)

        combinations = self.matcher.get_valid_combinations(exp_pattern, env_pattern)
        total_combinations = sum(len(experiments) for experiments in combinations.values())

        log.info(f'Starting batch execution: {total_combinations} combinations across {len(combinations)} environments')

        self._print_execution_plan(combinations)

        results = await self._execute_all_combinations(combinations, total_combinations,
                                                      project_path, show_flow_console, **experiment_kwargs)

        end_time = datetime.now(timezone.utc)
        total_duration = end_time - start_time

        return BatchRunSummary(
            results=results,
            total_combinations=total_combinations,
            total_duration=total_duration
        )

    async def _execute_all_combinations(
        self,
        combinations: Dict[str, List[str]],
        total_combinations: int,
        project_path: Path,
        show_flow_console: bool,
        **experiment_kwargs: Any
    ) -> List[ExperimentResult]:
        """Execute all experiment-environment combinations."""
        results = []
        combination_count = 0

        try:
            for env_name in sorted(combinations.keys()):
                if self.interrupt_requested:
                    break

                experiments = combinations[env_name]
                console.print(f"\n[bold cyan]Environment: {env_name}[/bold cyan]")

                for exp_name in experiments:
                    if self.interrupt_requested:
                        break

                    combination_count += 1
                    console.print(f"  [{combination_count}/{total_combinations}] Running {exp_name}...")

                    result = await self._execute_combination(
                        project_path, exp_name, env_name, show_flow_console, **experiment_kwargs
                    )
                    results.append(result)

                    self._print_immediate_result(result)

        except KeyboardInterrupt:
            console.print("\n[yellow]Batch execution interrupted by user[/yellow]")
            self.interrupt_requested = True

        return results

    def _print_immediate_result(self, result: ExperimentResult) -> None:
        """Print the immediate result of a single experiment execution."""
        status_icon = "✓" if result.status == StatusEnum.SUCCESS else "✗"
        status_color = "green" if result.status == StatusEnum.SUCCESS else "red"
        console.print(f"    [{status_color}]{status_icon}[/{status_color}] "
                     f"{result.duration.total_seconds():.1f}s")

        if result.error_message:
            console.print(f"    [red]Error: {result.error_message}[/red]")

    def _print_execution_plan(self, combinations: Dict[str, List[str]]):
        """Print the execution plan before starting."""
        console.print("\n[bold]Execution Plan:[/bold]")

        for env_name in sorted(combinations.keys()):
            experiments = combinations[env_name]
            console.print(f"  [cyan]{env_name}[/cyan]: {', '.join(experiments)}")

        total = sum(len(experiments) for experiments in combinations.values())
        console.print(f"\nTotal combinations: [bold]{total}[/bold]")
        console.print()

    async def _execute_combination(
        self,
        project_path: Path,
        experiment_name: str,
        environment_name: str,
        show_flow_console: bool,
        **kwargs
    ) -> ExperimentResult:
        """Execute a single experiment-environment combination."""
        start_time = datetime.now(timezone.utc)

        try:
            # Import here to avoid circular imports
            from adare.backend.experiment.commands import experiment_run

            # Execute the experiment
            await experiment_run(
                project_path=project_path,
                experiment_name=experiment_name,
                environment_name=environment_name,
                disable_printing=not show_flow_console,  # Control flow console display
                **kwargs
            )

            end_time = datetime.now(timezone.utc)
            duration = end_time - start_time

            return ExperimentResult(
                environment=environment_name,
                experiment=experiment_name,
                status=StatusEnum.SUCCESS,
                duration=duration,
                start_time=start_time,
                end_time=end_time
            )

        except Exception as e:
            end_time = datetime.now(timezone.utc)
            duration = end_time - start_time

            # Determine status based on exception type
            from adare.exceptions import LoggedException
            if isinstance(e, LoggedException):
                status = StatusEnum.FAILED
                error_msg = str(e.message) if hasattr(e, 'message') else str(e)
            else:
                status = StatusEnum.ERROR
                error_msg = f"Unexpected error: {str(e)}"

            return ExperimentResult(
                environment=environment_name,
                experiment=experiment_name,
                status=status,
                duration=duration,
                error_message=error_msg,
                start_time=start_time,
                end_time=end_time
            )


def has_glob_patterns(experiment_pattern: str, environment_pattern: str) -> bool:
    """Check if either pattern contains glob characters.

    Args:
        experiment_pattern: Experiment name pattern to check
        environment_pattern: Environment name pattern to check

    Returns:
        True if either pattern contains glob characters, False otherwise
    """
    if not experiment_pattern or not environment_pattern:
        return False

    # Use class method directly to avoid creating unnecessary instance
    glob_chars = ExperimentEnvironmentMatcher._GLOB_CHARS
    return (any(char in experiment_pattern for char in glob_chars) or
            any(char in environment_pattern for char in glob_chars))


async def run_batch_experiments(
    project_path: Path,
    experiment_pattern: str,
    environment_pattern: str,
    show_flow_console: bool = False,
    **experiment_kwargs: Any
) -> BatchRunSummary:
    """Main entry point for batch experiment execution.

    This is the primary interface for running experiments in batch mode,
    supporting glob patterns for both experiment and environment names.

    Args:
        project_path: Path to the project containing experiments and environments
        experiment_pattern: Experiment name or pattern (supports glob patterns)
        environment_pattern: Environment name or pattern (supports glob patterns)
        show_flow_console: Whether to show flow console for individual runs (default: False)
        **experiment_kwargs: Additional arguments to pass to experiment_run

    Returns:
        BatchRunSummary containing results and statistics

    Raises:
        ValueError: If project_path is invalid or patterns are empty
        LoggedErrorException: If no matching experiments, environments, or valid combinations

    Example:
        >>> summary = await run_batch_experiments(
        ...     Path("/path/to/project"),
        ...     "test_*",
        ...     "ubuntu*",
        ...     test=True
        ... )
        >>> summary.print_summary()
    """
    if not experiment_pattern.strip():
        raise ValueError("Experiment pattern cannot be empty")
    if not environment_pattern.strip():
        raise ValueError("Environment pattern cannot be empty")

    runner = BatchExperimentRunner()
    return await runner.run_batch(project_path, experiment_pattern, environment_pattern, show_flow_console, **experiment_kwargs)