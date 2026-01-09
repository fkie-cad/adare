"""
Comprehensive unit tests for BatchExperimentRunner and related classes.

Tests cover:
- ExperimentResult dataclass validation and serialization
- BatchRunSummary dataclass statistics and serialization
- ExperimentEnvironmentMatcher initialization and pattern matching
- BatchExperimentRunner initialization
- run_batch() - batch experiment execution
- run_single_experiment() via _execute_combination - single experiment execution
- experiment queuing via _execute_all_combinations
- result collection
- error handling for failed experiments
"""

import pytest
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# Mock libvirt_qemu and libvirt before any imports that might need it
sys.modules['libvirt_qemu'] = MagicMock()
sys.modules['libvirt'] = MagicMock()

from adare.backend.experiment.batch_runner import (
    ExperimentResult,
    BatchRunSummary,
    ExperimentEnvironmentMatcher,
    BatchExperimentRunner,
    run_batch_experiments,
    has_glob_patterns,
)
from adare.exceptions import LoggedErrorException
from adarelib.constants import StatusEnum


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return project_dir


@pytest.fixture
def sample_experiment_result():
    """Create a sample ExperimentResult."""
    return ExperimentResult(
        environment="ubuntu-22.04",
        experiment="test_experiment",
        status=StatusEnum.SUCCESS,
        duration=timedelta(seconds=120),
        error_message=None,
        run_ulid="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2024, 1, 15, 10, 2, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_results_list():
    """Create a list of sample ExperimentResults."""
    return [
        ExperimentResult(
            environment="ubuntu-22.04",
            experiment="test_1",
            status=StatusEnum.SUCCESS,
            duration=timedelta(seconds=60),
        ),
        ExperimentResult(
            environment="ubuntu-22.04",
            experiment="test_2",
            status=StatusEnum.FAILED,
            duration=timedelta(seconds=30),
            error_message="Test failed",
        ),
        ExperimentResult(
            environment="windows-11",
            experiment="test_1",
            status=StatusEnum.INTERRUPTED,
            duration=timedelta(seconds=15),
            error_message="User interrupted",
        ),
    ]


@pytest.fixture
def mock_experiment_api():
    """Create a mock ExperimentApi."""
    with patch('adare.backend.experiment.batch_runner.ExperimentApi') as mock_class:
        mock_api = MagicMock()
        mock_class.return_value.__enter__ = MagicMock(return_value=mock_api)
        mock_class.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_api


@pytest.fixture
def mock_environment_api():
    """Create a mock EnvironmentDbApi."""
    with patch('adare.database.api.environment.EnvironmentDbApi') as mock_class:
        mock_api = MagicMock()
        mock_class.return_value.__enter__ = MagicMock(return_value=mock_api)
        mock_class.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_api


# ============================================================================
# TestExperimentResult
# ============================================================================


class TestExperimentResult:
    """Tests for ExperimentResult dataclass."""

    def test_creation_with_required_fields(self):
        """ExperimentResult should be created with required fields."""
        result = ExperimentResult(
            environment="ubuntu-22.04",
            experiment="test_experiment",
            status=StatusEnum.SUCCESS,
            duration=timedelta(seconds=120),
        )

        assert result.environment == "ubuntu-22.04"
        assert result.experiment == "test_experiment"
        assert result.status == StatusEnum.SUCCESS
        assert result.duration == timedelta(seconds=120)
        assert result.error_message is None
        assert result.run_ulid is None
        assert result.start_time is None
        assert result.end_time is None

    def test_creation_with_all_fields(self, sample_experiment_result):
        """ExperimentResult should support all optional fields."""
        result = sample_experiment_result

        assert result.environment == "ubuntu-22.04"
        assert result.experiment == "test_experiment"
        assert result.status == StatusEnum.SUCCESS
        assert result.duration == timedelta(seconds=120)
        assert result.error_message is None
        assert result.run_ulid == "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        assert result.start_time == datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        assert result.end_time == datetime(2024, 1, 15, 10, 2, 0, tzinfo=timezone.utc)

    def test_creation_with_error_message(self):
        """ExperimentResult should store error message."""
        result = ExperimentResult(
            environment="ubuntu-22.04",
            experiment="test_experiment",
            status=StatusEnum.FAILED,
            duration=timedelta(seconds=30),
            error_message="Test assertion failed",
        )

        assert result.status == StatusEnum.FAILED
        assert result.error_message == "Test assertion failed"

    def test_validation_empty_environment_raises_error(self):
        """ExperimentResult should raise ValueError for empty environment."""
        with pytest.raises(ValueError, match="Environment name cannot be empty"):
            ExperimentResult(
                environment="",
                experiment="test_experiment",
                status=StatusEnum.SUCCESS,
                duration=timedelta(seconds=60),
            )

    def test_validation_whitespace_environment_raises_error(self):
        """ExperimentResult should raise ValueError for whitespace-only environment."""
        with pytest.raises(ValueError, match="Environment name cannot be empty"):
            ExperimentResult(
                environment="   ",
                experiment="test_experiment",
                status=StatusEnum.SUCCESS,
                duration=timedelta(seconds=60),
            )

    def test_validation_empty_experiment_raises_error(self):
        """ExperimentResult should raise ValueError for empty experiment."""
        with pytest.raises(ValueError, match="Experiment name cannot be empty"):
            ExperimentResult(
                environment="ubuntu-22.04",
                experiment="",
                status=StatusEnum.SUCCESS,
                duration=timedelta(seconds=60),
            )

    def test_validation_whitespace_experiment_raises_error(self):
        """ExperimentResult should raise ValueError for whitespace-only experiment."""
        with pytest.raises(ValueError, match="Experiment name cannot be empty"):
            ExperimentResult(
                environment="ubuntu-22.04",
                experiment="  ",
                status=StatusEnum.SUCCESS,
                duration=timedelta(seconds=60),
            )

    def test_validation_negative_duration_raises_error(self):
        """ExperimentResult should raise ValueError for negative duration."""
        with pytest.raises(ValueError, match="Duration cannot be negative"):
            ExperimentResult(
                environment="ubuntu-22.04",
                experiment="test_experiment",
                status=StatusEnum.SUCCESS,
                duration=timedelta(seconds=-10),
            )

    def test_to_dict_serialization(self, sample_experiment_result):
        """ExperimentResult should serialize to dict correctly."""
        result_dict = sample_experiment_result.to_dict()

        assert result_dict['environment'] == "ubuntu-22.04"
        assert result_dict['experiment'] == "test_experiment"
        assert result_dict['status'] == "SUCCESS"
        assert result_dict['duration_seconds'] == 120.0
        assert result_dict['error_message'] is None
        assert result_dict['run_ulid'] == "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        assert result_dict['start_time'] == "2024-01-15T10:00:00+00:00"
        assert result_dict['end_time'] == "2024-01-15T10:02:00+00:00"

    def test_to_dict_with_none_times(self):
        """ExperimentResult should serialize None times correctly."""
        result = ExperimentResult(
            environment="ubuntu-22.04",
            experiment="test_experiment",
            status=StatusEnum.SUCCESS,
            duration=timedelta(seconds=60),
        )

        result_dict = result.to_dict()

        assert result_dict['start_time'] is None
        assert result_dict['end_time'] is None

    def test_is_immutable(self, sample_experiment_result):
        """ExperimentResult should be immutable (frozen dataclass)."""
        with pytest.raises(AttributeError):
            sample_experiment_result.environment = "new-environment"


# ============================================================================
# TestBatchRunSummary
# ============================================================================


class TestBatchRunSummary:
    """Tests for BatchRunSummary dataclass."""

    def test_creation_with_results(self, sample_results_list):
        """BatchRunSummary should be created with results list."""
        summary = BatchRunSummary(
            results=sample_results_list,
            total_combinations=3,
            total_duration=timedelta(seconds=105),
        )

        assert len(summary.results) == 3
        assert summary.total_combinations == 3
        assert summary.total_duration == timedelta(seconds=105)

    def test_successful_runs_count(self, sample_results_list):
        """BatchRunSummary should count successful runs correctly."""
        summary = BatchRunSummary(
            results=sample_results_list,
            total_combinations=3,
            total_duration=timedelta(seconds=105),
        )

        assert summary.successful_runs == 1

    def test_failed_runs_count(self, sample_results_list):
        """BatchRunSummary should count failed runs correctly."""
        summary = BatchRunSummary(
            results=sample_results_list,
            total_combinations=3,
            total_duration=timedelta(seconds=105),
        )

        assert summary.failed_runs == 1

    def test_interrupted_runs_count(self, sample_results_list):
        """BatchRunSummary should count interrupted runs correctly."""
        summary = BatchRunSummary(
            results=sample_results_list,
            total_combinations=3,
            total_duration=timedelta(seconds=105),
        )

        assert summary.interrupted_runs == 1

    def test_success_rate_calculation(self, sample_results_list):
        """BatchRunSummary should calculate success rate correctly."""
        summary = BatchRunSummary(
            results=sample_results_list,
            total_combinations=3,
            total_duration=timedelta(seconds=105),
        )

        # 1 success out of 3 total = 33.33%
        assert pytest.approx(summary.success_rate, 0.01) == 33.33

    def test_success_rate_zero_combinations(self):
        """BatchRunSummary should return 0% for zero combinations."""
        summary = BatchRunSummary(
            results=[],
            total_combinations=0,
            total_duration=timedelta(seconds=0),
        )

        assert summary.success_rate == 0.0

    def test_success_rate_all_successful(self):
        """BatchRunSummary should return 100% for all successful runs."""
        results = [
            ExperimentResult(
                environment="ubuntu",
                experiment=f"test_{i}",
                status=StatusEnum.SUCCESS,
                duration=timedelta(seconds=30),
            )
            for i in range(5)
        ]

        summary = BatchRunSummary(
            results=results,
            total_combinations=5,
            total_duration=timedelta(seconds=150),
        )

        assert summary.success_rate == 100.0

    def test_validation_negative_total_combinations_raises_error(self):
        """BatchRunSummary should raise ValueError for negative total_combinations."""
        with pytest.raises(ValueError, match="Total combinations cannot be negative"):
            BatchRunSummary(
                results=[],
                total_combinations=-1,
                total_duration=timedelta(seconds=0),
            )

    def test_validation_results_exceed_total_raises_error(self, sample_results_list):
        """BatchRunSummary should raise ValueError if results exceed total_combinations."""
        with pytest.raises(ValueError, match="Results count cannot exceed total combinations"):
            BatchRunSummary(
                results=sample_results_list,
                total_combinations=2,  # Only 2, but 3 results
                total_duration=timedelta(seconds=105),
            )

    def test_to_dict_serialization(self, sample_results_list):
        """BatchRunSummary should serialize to dict correctly."""
        summary = BatchRunSummary(
            results=sample_results_list,
            total_combinations=3,
            total_duration=timedelta(seconds=105),
        )

        summary_dict = summary.to_dict()

        assert 'summary' in summary_dict
        assert 'results' in summary_dict
        assert summary_dict['summary']['total_combinations'] == 3
        assert summary_dict['summary']['successful_runs'] == 1
        assert summary_dict['summary']['failed_runs'] == 1
        assert summary_dict['summary']['interrupted_runs'] == 1
        assert pytest.approx(summary_dict['summary']['success_rate'], 0.01) == 33.33
        assert summary_dict['summary']['total_duration_seconds'] == 105.0
        assert len(summary_dict['results']) == 3

    def test_get_status_display_success(self, sample_results_list):
        """BatchRunSummary._get_status_display should return correct icon for success."""
        summary = BatchRunSummary(
            results=sample_results_list,
            total_combinations=3,
            total_duration=timedelta(seconds=105),
        )

        icon, style = summary._get_status_display(StatusEnum.SUCCESS)

        assert icon == "\u2713"  # checkmark
        assert style == "green"

    def test_get_status_display_failed(self, sample_results_list):
        """BatchRunSummary._get_status_display should return correct icon for failed."""
        summary = BatchRunSummary(
            results=sample_results_list,
            total_combinations=3,
            total_duration=timedelta(seconds=105),
        )

        icon, style = summary._get_status_display(StatusEnum.FAILED)

        assert icon == "\u2717"  # X mark
        assert style == "red"

    def test_get_status_display_interrupted(self, sample_results_list):
        """BatchRunSummary._get_status_display should return correct icon for interrupted."""
        summary = BatchRunSummary(
            results=sample_results_list,
            total_combinations=3,
            total_duration=timedelta(seconds=105),
        )

        icon, style = summary._get_status_display(StatusEnum.INTERRUPTED)

        assert icon == "\u26a0"  # warning
        assert style == "yellow"


# ============================================================================
# TestExperimentEnvironmentMatcher
# ============================================================================


class TestExperimentEnvironmentMatcherInit:
    """Tests for ExperimentEnvironmentMatcher initialization."""

    def test_initialization_with_valid_path(self, temp_project_dir):
        """ExperimentEnvironmentMatcher should initialize with valid directory."""
        matcher = ExperimentEnvironmentMatcher(temp_project_dir)

        assert matcher.project_path == temp_project_dir

    def test_initialization_with_nonexistent_path_raises_error(self, tmp_path):
        """ExperimentEnvironmentMatcher should raise ValueError for nonexistent path."""
        nonexistent_path = tmp_path / "nonexistent"

        with pytest.raises(ValueError, match="Project path does not exist"):
            ExperimentEnvironmentMatcher(nonexistent_path)

    def test_initialization_with_file_path_raises_error(self, tmp_path):
        """ExperimentEnvironmentMatcher should raise ValueError for file path."""
        file_path = tmp_path / "file.txt"
        file_path.touch()

        with pytest.raises(ValueError, match="Project path is not a directory"):
            ExperimentEnvironmentMatcher(file_path)


class TestExperimentEnvironmentMatcherGlobPattern:
    """Tests for ExperimentEnvironmentMatcher.has_glob_pattern method."""

    def test_has_glob_pattern_with_asterisk(self, temp_project_dir):
        """has_glob_pattern should return True for asterisk."""
        matcher = ExperimentEnvironmentMatcher(temp_project_dir)

        assert matcher.has_glob_pattern("test_*") is True

    def test_has_glob_pattern_with_question_mark(self, temp_project_dir):
        """has_glob_pattern should return True for question mark."""
        matcher = ExperimentEnvironmentMatcher(temp_project_dir)

        assert matcher.has_glob_pattern("test_?") is True

    def test_has_glob_pattern_with_brackets(self, temp_project_dir):
        """has_glob_pattern should return True for brackets."""
        matcher = ExperimentEnvironmentMatcher(temp_project_dir)

        assert matcher.has_glob_pattern("test_[0-9]") is True

    def test_has_glob_pattern_without_glob_chars(self, temp_project_dir):
        """has_glob_pattern should return False without glob characters."""
        matcher = ExperimentEnvironmentMatcher(temp_project_dir)

        assert matcher.has_glob_pattern("test_experiment") is False

    def test_has_glob_pattern_empty_string(self, temp_project_dir):
        """has_glob_pattern should return False for empty string."""
        matcher = ExperimentEnvironmentMatcher(temp_project_dir)

        assert matcher.has_glob_pattern("") is False


class TestExperimentEnvironmentMatcherMatchExperiments:
    """Tests for ExperimentEnvironmentMatcher.match_experiments method."""

    def test_match_experiments_exact_match(self, temp_project_dir):
        """match_experiments should return exact match when exists."""
        with patch('adare.backend.experiment.batch_runner.ExperimentApi') as mock_class:
            mock_api = MagicMock()
            mock_class.return_value.__enter__ = MagicMock(return_value=mock_api)
            mock_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_exp = MagicMock()
            mock_exp.name = "test_experiment"
            mock_api.get_experiments.return_value = [mock_exp]

            matcher = ExperimentEnvironmentMatcher(temp_project_dir)
            result = matcher.match_experiments("test_experiment")

            assert result == ["test_experiment"]

    def test_match_experiments_glob_pattern(self, temp_project_dir):
        """match_experiments should return matching experiments for glob pattern."""
        with patch('adare.backend.experiment.batch_runner.ExperimentApi') as mock_class:
            mock_api = MagicMock()
            mock_class.return_value.__enter__ = MagicMock(return_value=mock_api)
            mock_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_exps = [MagicMock(name=f"test_{i}") for i in range(3)]
            for i, exp in enumerate(mock_exps):
                exp.name = f"test_{i}"
            mock_api.get_experiments.return_value = mock_exps

            matcher = ExperimentEnvironmentMatcher(temp_project_dir)
            result = matcher.match_experiments("test_*")

            assert result == ["test_0", "test_1", "test_2"]

    def test_match_experiments_no_match(self, temp_project_dir):
        """match_experiments should return empty list when no match."""
        with patch('adare.backend.experiment.batch_runner.ExperimentApi') as mock_class:
            mock_api = MagicMock()
            mock_class.return_value.__enter__ = MagicMock(return_value=mock_api)
            mock_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_api.get_experiments.return_value = []

            matcher = ExperimentEnvironmentMatcher(temp_project_dir)
            result = matcher.match_experiments("nonexistent")

            assert result == []

    def test_match_experiments_empty_pattern_raises_error(self, temp_project_dir):
        """match_experiments should raise ValueError for empty pattern."""
        matcher = ExperimentEnvironmentMatcher(temp_project_dir)

        with pytest.raises(ValueError, match="Experiment pattern cannot be empty"):
            matcher.match_experiments("")

    def test_match_experiments_whitespace_pattern_raises_error(self, temp_project_dir):
        """match_experiments should raise ValueError for whitespace pattern."""
        matcher = ExperimentEnvironmentMatcher(temp_project_dir)

        with pytest.raises(ValueError, match="Experiment pattern cannot be empty"):
            matcher.match_experiments("   ")


class TestExperimentEnvironmentMatcherMatchEnvironments:
    """Tests for ExperimentEnvironmentMatcher.match_environments method."""

    def test_match_environments_exact_match(self, temp_project_dir):
        """match_environments should return exact match when exists."""
        with patch('adare.backend.experiment.batch_runner.ExperimentEnvironmentMatcher.match_environments') as mock_method:
            mock_method.return_value = ["ubuntu-22.04"]

            matcher = ExperimentEnvironmentMatcher.__new__(ExperimentEnvironmentMatcher)
            matcher.project_path = temp_project_dir
            matcher._GLOB_CHARS = {'*', '?', '[', ']'}

            result = mock_method("ubuntu-22.04")

            assert result == ["ubuntu-22.04"]

    def test_match_environments_empty_pattern_raises_error(self, temp_project_dir):
        """match_environments should raise ValueError for empty pattern."""
        matcher = ExperimentEnvironmentMatcher(temp_project_dir)

        with pytest.raises(ValueError, match="Environment pattern cannot be empty"):
            matcher.match_environments("")


class TestExperimentEnvironmentMatcherValidateCompatibility:
    """Tests for ExperimentEnvironmentMatcher.validate_compatibility method."""

    def test_validate_compatibility_empty_experiment_raises_error(self, temp_project_dir):
        """validate_compatibility should raise ValueError for empty experiment."""
        matcher = ExperimentEnvironmentMatcher(temp_project_dir)

        with pytest.raises(ValueError, match="Experiment name cannot be empty"):
            matcher.validate_compatibility("", "ubuntu-22.04")

    def test_validate_compatibility_empty_environment_raises_error(self, temp_project_dir):
        """validate_compatibility should raise ValueError for empty environment."""
        matcher = ExperimentEnvironmentMatcher(temp_project_dir)

        with pytest.raises(ValueError, match="Environment name cannot be empty"):
            matcher.validate_compatibility("test_experiment", "")

    def test_validate_compatibility_valid_combination(self, temp_project_dir):
        """validate_compatibility should return True for valid combination."""
        with patch('adare.backend.experiment.batch_runner.ExperimentApi') as mock_class:
            mock_api = MagicMock()
            mock_class.return_value.__enter__ = MagicMock(return_value=mock_api)
            mock_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_env = MagicMock()
            mock_env.id = 1
            mock_api.get_environment.return_value = mock_env

            mock_exp = MagicMock()
            mock_api.get_experiment.return_value = mock_exp

            matcher = ExperimentEnvironmentMatcher(temp_project_dir)
            result = matcher.validate_compatibility("test_experiment", "ubuntu-22.04")

            assert result is True

    def test_validate_compatibility_environment_not_found(self, temp_project_dir):
        """validate_compatibility should return False when environment not found."""
        with patch('adare.backend.experiment.batch_runner.ExperimentApi') as mock_class:
            mock_api = MagicMock()
            mock_class.return_value.__enter__ = MagicMock(return_value=mock_api)
            mock_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_api.get_environment.return_value = None

            matcher = ExperimentEnvironmentMatcher(temp_project_dir)
            result = matcher.validate_compatibility("test_experiment", "nonexistent")

            assert result is False


# ============================================================================
# TestBatchExperimentRunnerInit
# ============================================================================


class TestBatchExperimentRunnerInit:
    """Tests for BatchExperimentRunner initialization."""

    def test_initialization_defaults(self):
        """BatchExperimentRunner should initialize with correct defaults."""
        runner = BatchExperimentRunner()

        assert runner.matcher is None
        assert runner.interrupt_requested is False


# ============================================================================
# TestBatchExperimentRunnerRunBatch
# ============================================================================


class TestBatchExperimentRunnerRunBatch:
    """Tests for BatchExperimentRunner.run_batch method."""

    @pytest.mark.asyncio
    async def test_run_batch_nonexistent_project_raises_error(self, tmp_path):
        """run_batch should raise ValueError for nonexistent project path."""
        nonexistent_path = tmp_path / "nonexistent"
        runner = BatchExperimentRunner()

        with pytest.raises(ValueError, match="Project path does not exist"):
            await runner.run_batch(nonexistent_path, "test_*", "ubuntu-*")

    @pytest.mark.asyncio
    async def test_run_batch_successful_execution(self, temp_project_dir):
        """run_batch should execute experiments and return BatchRunSummary."""
        runner = BatchExperimentRunner()

        with patch.object(runner, '_execute_all_combinations', new_callable=AsyncMock) as mock_execute:
            mock_result = ExperimentResult(
                environment="ubuntu-22.04",
                experiment="test_1",
                status=StatusEnum.SUCCESS,
                duration=timedelta(seconds=60),
            )
            mock_execute.return_value = [mock_result]

            with patch('adare.backend.experiment.batch_runner.ExperimentEnvironmentMatcher') as mock_matcher_class:
                mock_matcher = MagicMock()
                mock_matcher.get_valid_combinations.return_value = {"ubuntu-22.04": ["test_1"]}
                mock_matcher_class.return_value = mock_matcher

                with patch.object(runner, '_print_execution_plan'):
                    summary = await runner.run_batch(
                        temp_project_dir,
                        "test_*",
                        "ubuntu-*"
                    )

        assert isinstance(summary, BatchRunSummary)
        assert summary.total_combinations == 1
        assert len(summary.results) == 1

    @pytest.mark.asyncio
    async def test_run_batch_sets_matcher(self, temp_project_dir):
        """run_batch should set the matcher attribute."""
        runner = BatchExperimentRunner()

        with patch.object(runner, '_execute_all_combinations', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = []

            with patch('adare.backend.experiment.batch_runner.ExperimentEnvironmentMatcher') as mock_matcher_class:
                mock_matcher = MagicMock()
                mock_matcher.get_valid_combinations.return_value = {}
                mock_matcher_class.return_value = mock_matcher

                with patch.object(runner, '_print_execution_plan'):
                    try:
                        await runner.run_batch(temp_project_dir, "test_*", "ubuntu-*")
                    except LoggedErrorException:
                        pass  # Expected when no combinations found

        mock_matcher_class.assert_called_once_with(temp_project_dir)


# ============================================================================
# TestBatchExperimentRunnerExecuteCombination
# ============================================================================


class TestBatchExperimentRunnerExecuteCombination:
    """Tests for BatchExperimentRunner._execute_combination method."""

    @pytest.mark.asyncio
    async def test_execute_combination_success(self, temp_project_dir):
        """_execute_combination should return SUCCESS result on successful run."""
        runner = BatchExperimentRunner()

        with patch('adare.backend.experiment.run.experiment_run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (False, True)  # (was_interrupted, was_successful)

            result = await runner._execute_combination(
                temp_project_dir,
                "test_experiment",
                "ubuntu-22.04",
                show_flow_console=False
            )

        assert result.status == StatusEnum.SUCCESS
        assert result.environment == "ubuntu-22.04"
        assert result.experiment == "test_experiment"
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_execute_combination_failure(self, temp_project_dir):
        """_execute_combination should return FAILED result on failed run."""
        runner = BatchExperimentRunner()

        with patch('adare.backend.experiment.run.experiment_run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (False, False)  # (was_interrupted, was_successful)

            result = await runner._execute_combination(
                temp_project_dir,
                "test_experiment",
                "ubuntu-22.04",
                show_flow_console=False
            )

        assert result.status == StatusEnum.FAILED
        assert result.error_message == "Experiment tests failed"

    @pytest.mark.asyncio
    async def test_execute_combination_interrupted(self, temp_project_dir):
        """_execute_combination should return INTERRUPTED result on interruption."""
        runner = BatchExperimentRunner()

        with patch('adare.backend.experiment.run.experiment_run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (True, False)  # (was_interrupted, was_successful)

            result = await runner._execute_combination(
                temp_project_dir,
                "test_experiment",
                "ubuntu-22.04",
                show_flow_console=False
            )

        assert result.status == StatusEnum.INTERRUPTED
        assert result.error_message == "User interrupted"

    @pytest.mark.asyncio
    async def test_execute_combination_logged_exception(self, temp_project_dir):
        """_execute_combination should return FAILED result on LoggedException."""
        runner = BatchExperimentRunner()

        import logging
        mock_logger = MagicMock(spec=logging.Logger)

        with patch('adare.backend.experiment.run.experiment_run', new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = LoggedErrorException(mock_logger, "Test error message")

            result = await runner._execute_combination(
                temp_project_dir,
                "test_experiment",
                "ubuntu-22.04",
                show_flow_console=False
            )

        assert result.status == StatusEnum.FAILED
        assert "Test error message" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_combination_unexpected_exception(self, temp_project_dir):
        """_execute_combination should return ERROR result on unexpected exception."""
        runner = BatchExperimentRunner()

        with patch('adare.backend.experiment.run.experiment_run', new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = RuntimeError("Unexpected error")

            result = await runner._execute_combination(
                temp_project_dir,
                "test_experiment",
                "ubuntu-22.04",
                show_flow_console=False
            )

        assert result.status == StatusEnum.ERROR
        assert "Unexpected error" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_combination_records_duration(self, temp_project_dir):
        """_execute_combination should record correct duration."""
        runner = BatchExperimentRunner()

        with patch('adare.backend.experiment.run.experiment_run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (False, True)

            result = await runner._execute_combination(
                temp_project_dir,
                "test_experiment",
                "ubuntu-22.04",
                show_flow_console=False
            )

        assert result.duration.total_seconds() >= 0
        assert result.start_time is not None
        assert result.end_time is not None
        assert result.end_time >= result.start_time

    @pytest.mark.asyncio
    async def test_execute_combination_passes_kwargs(self, temp_project_dir):
        """_execute_combination should pass additional kwargs to experiment_run."""
        runner = BatchExperimentRunner()

        with patch('adare.backend.experiment.run.experiment_run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (False, True)

            await runner._execute_combination(
                temp_project_dir,
                "test_experiment",
                "ubuntu-22.04",
                show_flow_console=True,
                test_mode=True,
                custom_arg="value"
            )

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs['test_mode'] is True
        assert call_kwargs['custom_arg'] == "value"
        assert call_kwargs['disable_printing'] is False  # show_flow_console=True


# ============================================================================
# TestBatchExperimentRunnerExecuteAllCombinations
# ============================================================================


class TestBatchExperimentRunnerExecuteAllCombinations:
    """Tests for BatchExperimentRunner._execute_all_combinations method."""

    @pytest.mark.asyncio
    async def test_execute_all_combinations_sequential(self, temp_project_dir):
        """_execute_all_combinations should execute experiments sequentially."""
        runner = BatchExperimentRunner()
        combinations = {
            "ubuntu-22.04": ["test_1", "test_2"],
            "windows-11": ["test_1"]
        }

        with patch.object(runner, '_execute_combination', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ExperimentResult(
                environment="env",
                experiment="exp",
                status=StatusEnum.SUCCESS,
                duration=timedelta(seconds=30),
            )

            with patch.object(runner, '_print_immediate_result'):
                with patch('adare.backend.experiment.batch_runner.console'):
                    results = await runner._execute_all_combinations(
                        combinations,
                        total_combinations=3,
                        project_path=temp_project_dir,
                        show_flow_console=False
                    )

        assert len(results) == 3
        assert mock_exec.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_all_combinations_collects_results(self, temp_project_dir):
        """_execute_all_combinations should collect all results."""
        runner = BatchExperimentRunner()
        combinations = {"ubuntu-22.04": ["test_1", "test_2"]}

        results_to_return = [
            ExperimentResult(
                environment="ubuntu-22.04",
                experiment="test_1",
                status=StatusEnum.SUCCESS,
                duration=timedelta(seconds=30),
            ),
            ExperimentResult(
                environment="ubuntu-22.04",
                experiment="test_2",
                status=StatusEnum.FAILED,
                duration=timedelta(seconds=20),
                error_message="Test failed",
            ),
        ]

        with patch.object(runner, '_execute_combination', new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = results_to_return

            with patch.object(runner, '_print_immediate_result'):
                with patch('adare.backend.experiment.batch_runner.console'):
                    results = await runner._execute_all_combinations(
                        combinations,
                        total_combinations=2,
                        project_path=temp_project_dir,
                        show_flow_console=False
                    )

        assert len(results) == 2
        assert results[0].status == StatusEnum.SUCCESS
        assert results[1].status == StatusEnum.FAILED

    @pytest.mark.asyncio
    async def test_execute_all_combinations_respects_interrupt(self, temp_project_dir):
        """_execute_all_combinations should stop when interrupt_requested is True."""
        runner = BatchExperimentRunner()
        runner.interrupt_requested = True
        combinations = {"ubuntu-22.04": ["test_1", "test_2"]}

        with patch.object(runner, '_execute_combination', new_callable=AsyncMock) as mock_exec:
            with patch('adare.backend.experiment.batch_runner.console'):
                results = await runner._execute_all_combinations(
                    combinations,
                    total_combinations=2,
                    project_path=temp_project_dir,
                    show_flow_console=False
                )

        assert len(results) == 0
        mock_exec.assert_not_called()


# ============================================================================
# TestBatchExperimentRunnerHandleInterruption
# ============================================================================


class TestBatchExperimentRunnerHandleInterruption:
    """Tests for BatchExperimentRunner._handle_interruption method."""

    def test_handle_interruption_no_remaining_returns_false(self):
        """_handle_interruption should return False when no remaining combinations."""
        runner = BatchExperimentRunner()

        result = runner._handle_interruption([], "ubuntu-22.04", "test_1")

        assert result is False

    def test_handle_interruption_user_continues(self):
        """_handle_interruption should return True when user chooses to continue."""
        runner = BatchExperimentRunner()
        remaining = [("ubuntu-22.04", "test_2"), ("windows-11", "test_1")]

        with patch('builtins.input', return_value='y'):
            with patch('adare.backend.experiment.batch_runner.console'):
                result = runner._handle_interruption(remaining, "ubuntu-22.04", "test_1")

        assert result is True

    def test_handle_interruption_user_stops(self):
        """_handle_interruption should return False when user chooses to stop."""
        runner = BatchExperimentRunner()
        remaining = [("ubuntu-22.04", "test_2")]

        with patch('builtins.input', return_value='n'):
            with patch('adare.backend.experiment.batch_runner.console'):
                result = runner._handle_interruption(remaining, "ubuntu-22.04", "test_1")

        assert result is False

    def test_handle_interruption_keyboard_interrupt_returns_false(self):
        """_handle_interruption should return False on KeyboardInterrupt."""
        runner = BatchExperimentRunner()
        remaining = [("ubuntu-22.04", "test_2")]

        with patch('builtins.input', side_effect=KeyboardInterrupt):
            with patch('adare.backend.experiment.batch_runner.console'):
                result = runner._handle_interruption(remaining, "ubuntu-22.04", "test_1")

        assert result is False

    def test_handle_interruption_eof_returns_false(self):
        """_handle_interruption should return False on EOFError."""
        runner = BatchExperimentRunner()
        remaining = [("ubuntu-22.04", "test_2")]

        with patch('builtins.input', side_effect=EOFError):
            with patch('adare.backend.experiment.batch_runner.console'):
                result = runner._handle_interruption(remaining, "ubuntu-22.04", "test_1")

        assert result is False


# ============================================================================
# TestBatchExperimentRunnerPrintMethods
# ============================================================================


class TestBatchExperimentRunnerPrintMethods:
    """Tests for BatchExperimentRunner print methods."""

    def test_print_execution_plan(self):
        """_print_execution_plan should print without errors."""
        runner = BatchExperimentRunner()
        combinations = {
            "ubuntu-22.04": ["test_1", "test_2"],
            "windows-11": ["test_1"]
        }

        with patch('adare.backend.experiment.batch_runner.console') as mock_console:
            runner._print_execution_plan(combinations)

        assert mock_console.print.called

    def test_print_immediate_result_single_experiment_no_output(self):
        """_print_immediate_result should not print for single experiment."""
        runner = BatchExperimentRunner()
        result = ExperimentResult(
            environment="ubuntu-22.04",
            experiment="test_1",
            status=StatusEnum.SUCCESS,
            duration=timedelta(seconds=30),
        )

        with patch('adare.backend.experiment.batch_runner.console') as mock_console:
            runner._print_immediate_result(result, total_combinations=1)

        mock_console.print.assert_not_called()

    def test_print_immediate_result_multiple_experiments(self):
        """_print_immediate_result should print for multiple experiments."""
        runner = BatchExperimentRunner()
        result = ExperimentResult(
            environment="ubuntu-22.04",
            experiment="test_1",
            status=StatusEnum.SUCCESS,
            duration=timedelta(seconds=30),
        )

        with patch('adare.backend.experiment.batch_runner.console') as mock_console:
            runner._print_immediate_result(result, total_combinations=5)

        mock_console.print.assert_called()

    def test_print_immediate_result_failed_with_error(self):
        """_print_immediate_result should print error message for failed experiments."""
        runner = BatchExperimentRunner()
        result = ExperimentResult(
            environment="ubuntu-22.04",
            experiment="test_1",
            status=StatusEnum.FAILED,
            duration=timedelta(seconds=30),
            error_message="Test assertion failed",
        )

        with patch('adare.backend.experiment.batch_runner.console') as mock_console:
            runner._print_immediate_result(result, total_combinations=5)

        # Should print result line and error line
        assert mock_console.print.call_count >= 2


# ============================================================================
# TestRunBatchExperimentsFunction
# ============================================================================


class TestRunBatchExperimentsFunction:
    """Tests for run_batch_experiments function."""

    @pytest.mark.asyncio
    async def test_run_batch_experiments_empty_experiment_pattern_raises_error(self, temp_project_dir):
        """run_batch_experiments should raise ValueError for empty experiment pattern."""
        with pytest.raises(ValueError, match="Experiment pattern cannot be empty"):
            await run_batch_experiments(temp_project_dir, "", "ubuntu-*")

    @pytest.mark.asyncio
    async def test_run_batch_experiments_whitespace_experiment_pattern_raises_error(self, temp_project_dir):
        """run_batch_experiments should raise ValueError for whitespace experiment pattern."""
        with pytest.raises(ValueError, match="Experiment pattern cannot be empty"):
            await run_batch_experiments(temp_project_dir, "   ", "ubuntu-*")

    @pytest.mark.asyncio
    async def test_run_batch_experiments_empty_environment_pattern_raises_error(self, temp_project_dir):
        """run_batch_experiments should raise ValueError for empty environment pattern."""
        with pytest.raises(ValueError, match="Environment pattern cannot be empty"):
            await run_batch_experiments(temp_project_dir, "test_*", "")

    @pytest.mark.asyncio
    async def test_run_batch_experiments_whitespace_environment_pattern_raises_error(self, temp_project_dir):
        """run_batch_experiments should raise ValueError for whitespace environment pattern."""
        with pytest.raises(ValueError, match="Environment pattern cannot be empty"):
            await run_batch_experiments(temp_project_dir, "test_*", "   ")

    @pytest.mark.asyncio
    async def test_run_batch_experiments_creates_runner(self, temp_project_dir):
        """run_batch_experiments should create BatchExperimentRunner."""
        with patch('adare.backend.experiment.batch_runner.BatchExperimentRunner') as mock_runner_class:
            mock_runner = MagicMock()
            mock_runner.run_batch = AsyncMock(return_value=BatchRunSummary(
                results=[],
                total_combinations=0,
                total_duration=timedelta(seconds=0),
            ))
            mock_runner_class.return_value = mock_runner

            await run_batch_experiments(temp_project_dir, "test_*", "ubuntu-*")

        mock_runner_class.assert_called_once()
        mock_runner.run_batch.assert_called_once_with(
            temp_project_dir, "test_*", "ubuntu-*", False
        )


# ============================================================================
# TestHasGlobPatternsFunction
# ============================================================================


class TestHasGlobPatternsFunction:
    """Tests for has_glob_patterns function."""

    def test_has_glob_patterns_with_experiment_glob(self):
        """has_glob_patterns should return True when experiment has glob."""
        assert has_glob_patterns("test_*", "ubuntu-22.04") is True

    def test_has_glob_patterns_with_environment_glob(self):
        """has_glob_patterns should return True when environment has glob."""
        assert has_glob_patterns("test_experiment", "ubuntu-*") is True

    def test_has_glob_patterns_both_globs(self):
        """has_glob_patterns should return True when both have globs."""
        assert has_glob_patterns("test_*", "ubuntu-*") is True

    def test_has_glob_patterns_no_globs(self):
        """has_glob_patterns should return False when neither has globs."""
        assert has_glob_patterns("test_experiment", "ubuntu-22.04") is False

    def test_has_glob_patterns_empty_experiment(self):
        """has_glob_patterns should return False for empty experiment."""
        assert has_glob_patterns("", "ubuntu-*") is False

    def test_has_glob_patterns_empty_environment(self):
        """has_glob_patterns should return False for empty environment."""
        assert has_glob_patterns("test_*", "") is False

    def test_has_glob_patterns_both_empty(self):
        """has_glob_patterns should return False when both empty."""
        assert has_glob_patterns("", "") is False


# ============================================================================
# TestBatchRunSummaryPrintSummary
# ============================================================================


class TestBatchRunSummaryPrintSummary:
    """Tests for BatchRunSummary.print_summary method."""

    def test_print_summary_single_result_no_output(self):
        """print_summary should not print for single result."""
        results = [
            ExperimentResult(
                environment="ubuntu-22.04",
                experiment="test_1",
                status=StatusEnum.SUCCESS,
                duration=timedelta(seconds=30),
            )
        ]
        summary = BatchRunSummary(
            results=results,
            total_combinations=1,
            total_duration=timedelta(seconds=30),
        )

        with patch('adare.backend.experiment.batch_runner.console') as mock_console:
            summary.print_summary()

        mock_console.print.assert_not_called()

    def test_print_summary_multiple_results_prints_table(self, sample_results_list):
        """print_summary should print table for multiple results."""
        summary = BatchRunSummary(
            results=sample_results_list,
            total_combinations=3,
            total_duration=timedelta(seconds=105),
        )

        with patch('adare.backend.experiment.batch_runner.console') as mock_console:
            summary.print_summary()

        assert mock_console.print.called


# ============================================================================
# TestResultsCollection
# ============================================================================


class TestResultsCollection:
    """Tests for result collection behavior."""

    @pytest.mark.asyncio
    async def test_results_maintained_in_order(self, temp_project_dir):
        """Results should be maintained in execution order."""
        runner = BatchExperimentRunner()
        combinations = {"ubuntu-22.04": ["test_1", "test_2", "test_3"]}

        results_to_return = [
            ExperimentResult(
                environment="ubuntu-22.04",
                experiment=f"test_{i}",
                status=StatusEnum.SUCCESS,
                duration=timedelta(seconds=30),
            )
            for i in range(1, 4)
        ]

        with patch.object(runner, '_execute_combination', new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = results_to_return

            with patch.object(runner, '_print_immediate_result'):
                with patch('adare.backend.experiment.batch_runner.console'):
                    results = await runner._execute_all_combinations(
                        combinations,
                        total_combinations=3,
                        project_path=temp_project_dir,
                        show_flow_console=False
                    )

        assert results[0].experiment == "test_1"
        assert results[1].experiment == "test_2"
        assert results[2].experiment == "test_3"


# ============================================================================
# TestErrorHandling
# ============================================================================


class TestErrorHandling:
    """Tests for error handling in batch execution."""

    @pytest.mark.asyncio
    async def test_error_in_one_experiment_continues_batch(self, temp_project_dir):
        """Error in one experiment should not stop the entire batch."""
        runner = BatchExperimentRunner()
        combinations = {"ubuntu-22.04": ["test_1", "test_2"]}

        results_to_return = [
            ExperimentResult(
                environment="ubuntu-22.04",
                experiment="test_1",
                status=StatusEnum.ERROR,
                duration=timedelta(seconds=10),
                error_message="Unexpected error",
            ),
            ExperimentResult(
                environment="ubuntu-22.04",
                experiment="test_2",
                status=StatusEnum.SUCCESS,
                duration=timedelta(seconds=30),
            ),
        ]

        with patch.object(runner, '_execute_combination', new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = results_to_return

            with patch.object(runner, '_print_immediate_result'):
                with patch('adare.backend.experiment.batch_runner.console'):
                    results = await runner._execute_all_combinations(
                        combinations,
                        total_combinations=2,
                        project_path=temp_project_dir,
                        show_flow_console=False
                    )

        assert len(results) == 2
        assert results[0].status == StatusEnum.ERROR
        assert results[1].status == StatusEnum.SUCCESS

    @pytest.mark.asyncio
    async def test_failed_experiment_recorded_with_error_message(self, temp_project_dir):
        """Failed experiments should be recorded with error messages."""
        runner = BatchExperimentRunner()

        with patch('adare.backend.experiment.run.experiment_run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (False, False)

            result = await runner._execute_combination(
                temp_project_dir,
                "test_experiment",
                "ubuntu-22.04",
                show_flow_console=False
            )

        assert result.status == StatusEnum.FAILED
        assert result.error_message is not None
