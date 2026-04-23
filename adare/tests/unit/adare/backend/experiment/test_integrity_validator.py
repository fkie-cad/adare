"""Tests for IntegrityValidator extracted from run.py."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adare.backend.experiment.exceptions import ExperimentIntegrityError
from adare.backend.experiment.integrity_validator import IntegrityValidator

LOG = logging.getLogger("test_integrity_validator")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_playbook(test_names: list[str] | None = None):
    """Create a minimal playbook mock with optional testfunction names."""
    playbook = MagicMock()
    if test_names is None:
        playbook.tests = None
    else:
        tests = []
        for name in test_names:
            t = MagicMock()
            t.testfunction = name
            tests.append(t)
        playbook.tests = tests
    return playbook


# ---------------------------------------------------------------------------
# verify_playbook_testfunctions
# ---------------------------------------------------------------------------

class TestVerifyPlaybookTestfunctions:
    """Tests for IntegrityValidator.verify_playbook_testfunctions()."""

    def test_valid_playbook_no_error(self):
        """A playbook whose testfunctions are all present and have matching hashes should pass."""
        validator = IntegrityValidator(project_path=Path("/fake/project"))
        playbook = _make_playbook(["standard", "csv"])

        tf_data = [
            {"path": "testfunctions/standard/standard.py", "requirements_path": "testfunctions/standard/requirements.txt", "sha256hash": "abc123", "name": "standard"},
            {"path": "testfunctions/csv/csv.py", "requirements_path": "testfunctions/csv/requirements.txt", "sha256hash": "def456", "name": "csv"},
        ]

        with (
            patch("adare.backend.testfunction.database.get_testfunction_files_data", return_value=tf_data),
            patch("adare.helperfunctions.integrity.verify_testfunction_integrity") as mock_verify,
        ):
            # Should not raise
            validator.verify_playbook_testfunctions(playbook)

            assert mock_verify.call_count == 2

    def test_missing_testfunction_raises_error(self):
        """A playbook referencing a testfunction not in the database should raise."""
        validator = IntegrityValidator(project_path=Path("/fake/project"))
        playbook = _make_playbook(["nonexistent_tf"])

        tf_data = [
            {"path": "testfunctions/standard/standard.py", "requirements_path": "testfunctions/standard/requirements.txt", "sha256hash": "abc123", "name": "standard"},
        ]

        with patch("adare.backend.testfunction.database.get_testfunction_files_data", return_value=tf_data):
            with pytest.raises(ExperimentIntegrityError, match="not loaded in database"):
                validator.verify_playbook_testfunctions(playbook)

    def test_hash_mismatch_raises_error(self):
        """If verify_testfunction_integrity raises, it should propagate."""
        validator = IntegrityValidator(project_path=Path("/fake/project"))
        playbook = _make_playbook(["standard"])

        tf_data = [
            {"path": "testfunctions/standard/standard.py", "requirements_path": "testfunctions/standard/requirements.txt", "sha256hash": "abc123", "name": "standard"},
        ]

        with (
            patch("adare.backend.testfunction.database.get_testfunction_files_data", return_value=tf_data),
            patch(
                "adare.helperfunctions.integrity.verify_testfunction_integrity",
                side_effect=ExperimentIntegrityError(LOG, "hash mismatch"),
            ),pytest.raises(ExperimentIntegrityError, match="hash mismatch")
        ):
            validator.verify_playbook_testfunctions(playbook)

    def test_no_tests_in_playbook_skips(self):
        """A playbook with no tests should return without error."""
        validator = IntegrityValidator(project_path=Path("/fake/project"))
        playbook = _make_playbook(None)

        # Should not raise and should not call any database functions
        validator.verify_playbook_testfunctions(playbook)


# ---------------------------------------------------------------------------
# check_project
# ---------------------------------------------------------------------------

class TestCheckProject:
    """Tests for IntegrityValidator.check_project()."""

    def test_all_files_intact(self):
        """No error when all testfunction and environment hashes match."""
        validator = IntegrityValidator(project_path=Path("/fake/project"))

        tf_hashes = [
            {"file": "testfunctions/standard/standard.py", "requirements": "testfunctions/standard/requirements.txt", "hash": "abc123"},
        ]
        env_hashes = {
            "environments/ubuntu.yml": "env_hash_ok",
        }

        with (
            patch("adare.backend.project.database.get_global_testfunction_hashes", return_value=tf_hashes),
            patch("adare.backend.project.database.get_global_environment_hashes", return_value=env_hashes),
            patch("adare.helperfunctions.integrity.verify_testfunction_integrity"),
            patch("adare.helperfunctions.integrity.verify_environment_integrity"),
        ):
            # Should not raise
            validator.check_project()

    def test_modified_environment_raises_error(self):
        """A modified environment file should raise ExperimentIntegrityError."""
        validator = IntegrityValidator(project_path=Path("/fake/project"))

        tf_hashes = []  # No testfunctions
        env_hashes = {
            "environments/ubuntu.yml": "expected_hash",
        }

        with (
            patch("adare.backend.project.database.get_global_testfunction_hashes", return_value=tf_hashes),
            patch("adare.backend.project.database.get_global_environment_hashes", return_value=env_hashes),
            patch(
                "adare.helperfunctions.integrity.verify_environment_integrity",
                side_effect=ExperimentIntegrityError(LOG, "env modified"),
            ),pytest.raises(ExperimentIntegrityError, match="environment files have changed")
        ):
            validator.check_project()

    def test_modified_testfunction_raises_error(self):
        """A modified testfunction should raise ExperimentIntegrityError."""
        validator = IntegrityValidator(project_path=Path("/fake/project"))

        tf_hashes = [
            {"file": "testfunctions/standard/standard.py", "requirements": "testfunctions/standard/requirements.txt", "hash": "abc123"},
        ]
        env_hashes = {}

        with (
            patch("adare.backend.project.database.get_global_testfunction_hashes", return_value=tf_hashes),
            patch("adare.backend.project.database.get_global_environment_hashes", return_value=env_hashes),
            patch(
                "adare.helperfunctions.integrity.verify_testfunction_integrity",
                side_effect=ExperimentIntegrityError(LOG, "tf modified"),
            ),pytest.raises(ExperimentIntegrityError, match="testfunction files have changed")
        ):
            validator.check_project()


# ---------------------------------------------------------------------------
# check_experiment
# ---------------------------------------------------------------------------

class TestCheckExperiment:
    """Tests for IntegrityValidator.check_experiment()."""

    def test_valid_experiment(self):
        """No error when playbook hash matches."""
        validator = IntegrityValidator(project_path=Path("/fake/project"))

        experiment_dir = MagicMock()
        experiment_dir.sha256_playbook = "matching_hash"
        experiment_dir.playbookfile = Path("playbook.yml")

        with (
            patch("adare.backend.experiment.database.get_experiment_hashes", return_value={"playbook": "matching_hash"}),
            patch("adare.backend.experiment.database.get_experiment_by_project_and_name", return_value="exp_ulid"),
            patch("adare.backend.experiment.database.get_experiment_run_count", return_value=0),
        ):
            # Should not raise
            validator.check_experiment("test_exp", "test_env", experiment_dir)

    def test_missing_experiment_raises_error(self):
        """Mismatched playbook hash should raise ExperimentIntegrityError."""
        validator = IntegrityValidator(project_path=Path("/fake/project"))

        experiment_dir = MagicMock()
        experiment_dir.sha256_playbook = "current_hash"
        experiment_dir.playbookfile = Path("playbook.yml")

        with (
            patch("adare.backend.experiment.database.get_experiment_hashes", return_value={"playbook": "different_hash"}),
            patch("adare.backend.experiment.database.get_experiment_by_project_and_name", return_value="exp_ulid"),
            patch("adare.backend.experiment.database.get_experiment_run_count", return_value=0),
        ):
            with pytest.raises(ExperimentIntegrityError, match="files have been changed"):
                validator.check_experiment("test_exp", "test_env", experiment_dir)

    def test_experiment_with_runs_gives_different_solutions(self):
        """When experiment runs exist, solutions should mention deletion."""
        validator = IntegrityValidator(project_path=Path("/fake/project"))

        experiment_dir = MagicMock()
        experiment_dir.sha256_playbook = "current_hash"
        experiment_dir.playbookfile = Path("playbook.yml")

        with (
            patch("adare.backend.experiment.database.get_experiment_hashes", return_value={"playbook": "different_hash"}),
            patch("adare.backend.experiment.database.get_experiment_by_project_and_name", return_value="exp_ulid"),
            patch("adare.backend.experiment.database.get_experiment_run_count", return_value=5),
        ):
            with pytest.raises(ExperimentIntegrityError, match="files have been changed") as exc_info:
                validator.check_experiment("test_exp", "test_env", experiment_dir)

            # Verify that solutions mention deletion (not simple reload)
            solutions = exc_info.value.possible_solutions
            assert any("delete all related experiment runs" in s for s in solutions)
