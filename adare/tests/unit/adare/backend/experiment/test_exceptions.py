"""Tests for the experiment exception hierarchy and factory methods."""

import logging

import pytest

pytestmark = pytest.mark.unit

from adare.backend.experiment.exceptions import (
    AdareVMProcessDiedError,
    EnvironmentIntegrityError,
    # Direct children
    ExperimentAlreadyExistsError,
    ExperimentCommandError,
    # Config group
    ExperimentConfigError,
    ExperimentDirectoryAlreadyExistsError,
    ExperimentDirectoryCreationError,
    ExperimentDirectoryDoesNotExistError,
    # Root
    ExperimentException,
    ExperimentFileCreationError,
    ExperimentFileMissingError,
    # Filesystem group
    ExperimentFileSystemError,
    # Integrity group
    ExperimentIntegrityError,
    # Non-error
    ExperimentNotChanged,
    ExperimentRemovalError,
    MultipleEnvironmentsError,
    NoEnvironmentError,
    TestfunctionIntegrityError,
    VMSetupError,
)
from adare.exceptions import LoggedErrorException, LoggedException

LOG = logging.getLogger("test_exceptions")


# ---------------------------------------------------------------------------
# Hierarchy tests
# ---------------------------------------------------------------------------

class TestExperimentExceptionHierarchy:
    """Verify the MRO / isinstance relationships for every exception class."""

    def test_experiment_exception_extends_logged_error_exception(self):
        assert issubclass(ExperimentException, LoggedErrorException)

    # -- Filesystem group --------------------------------------------------

    def test_filesystem_error_extends_experiment_exception(self):
        assert issubclass(ExperimentFileSystemError, ExperimentException)

    @pytest.mark.parametrize("exc_cls", [
        ExperimentFileCreationError,
        ExperimentDirectoryCreationError,
        ExperimentRemovalError,
        ExperimentDirectoryAlreadyExistsError,
        ExperimentDirectoryDoesNotExistError,
        ExperimentFileMissingError,
    ])
    def test_filesystem_subclass_isinstance_filesystem_error(self, exc_cls):
        exc = exc_cls(LOG, "test")
        assert isinstance(exc, ExperimentFileSystemError)

    @pytest.mark.parametrize("exc_cls", [
        ExperimentFileCreationError,
        ExperimentDirectoryCreationError,
        ExperimentRemovalError,
        ExperimentDirectoryAlreadyExistsError,
        ExperimentDirectoryDoesNotExistError,
        ExperimentFileMissingError,
    ])
    def test_filesystem_subclass_backward_compat_logged_error(self, exc_cls):
        exc = exc_cls(LOG, "test")
        assert isinstance(exc, LoggedErrorException)

    @pytest.mark.parametrize("exc_cls", [
        ExperimentFileCreationError,
        ExperimentDirectoryCreationError,
        ExperimentRemovalError,
        ExperimentDirectoryAlreadyExistsError,
        ExperimentDirectoryDoesNotExistError,
        ExperimentFileMissingError,
    ])
    def test_filesystem_subclass_isinstance_experiment_exception(self, exc_cls):
        exc = exc_cls(LOG, "test")
        assert isinstance(exc, ExperimentException)

    # -- Integrity group ---------------------------------------------------

    def test_integrity_error_extends_experiment_exception(self):
        assert issubclass(ExperimentIntegrityError, ExperimentException)

    def test_environment_integrity_extends_integrity(self):
        exc = EnvironmentIntegrityError(LOG, "test")
        assert isinstance(exc, ExperimentIntegrityError)
        assert isinstance(exc, LoggedErrorException)

    def test_testfunction_integrity_extends_integrity(self):
        exc = TestfunctionIntegrityError(LOG, "test")
        assert isinstance(exc, ExperimentIntegrityError)
        assert isinstance(exc, LoggedErrorException)

    # -- Config group ------------------------------------------------------

    def test_config_error_extends_experiment_exception(self):
        assert issubclass(ExperimentConfigError, ExperimentException)

    def test_no_environment_error_extends_config(self):
        exc = NoEnvironmentError(LOG, "test")
        assert isinstance(exc, ExperimentConfigError)
        assert isinstance(exc, LoggedErrorException)

    def test_multiple_environments_error_extends_config(self):
        exc = MultipleEnvironmentsError(LOG, "test")
        assert isinstance(exc, ExperimentConfigError)
        assert isinstance(exc, LoggedErrorException)

    # -- Direct children ---------------------------------------------------

    def test_already_exists_extends_experiment_exception(self):
        exc = ExperimentAlreadyExistsError(LOG, "test")
        assert isinstance(exc, ExperimentException)
        assert isinstance(exc, LoggedErrorException)

    def test_command_error_extends_experiment_exception(self):
        exc = ExperimentCommandError(LOG, "ls", 1)
        assert isinstance(exc, ExperimentException)
        assert isinstance(exc, LoggedErrorException)

    def test_vm_setup_error_extends_experiment_exception(self):
        exc = VMSetupError(LOG, "myvm", "apt install", 1)
        assert isinstance(exc, ExperimentException)
        assert isinstance(exc, LoggedErrorException)

    def test_adarevm_process_died_extends_experiment_exception(self):
        exc = AdareVMProcessDiedError(LOG, exit_code=1)
        assert isinstance(exc, ExperimentException)
        assert isinstance(exc, LoggedErrorException)

    # -- ExperimentNotChanged stays outside the error hierarchy ------------

    def test_not_changed_extends_logged_exception(self):
        exc = ExperimentNotChanged(LOG, "nothing changed")
        assert isinstance(exc, LoggedException)
        assert not isinstance(exc, LoggedErrorException)
        assert not isinstance(exc, ExperimentException)


# ---------------------------------------------------------------------------
# Group catch tests
# ---------------------------------------------------------------------------

class TestGroupCatching:
    """Verify that catching a group base catches all its children."""

    def test_except_filesystem_error_catches_file_creation(self):
        with pytest.raises(ExperimentFileSystemError):
            raise ExperimentFileCreationError(LOG, "cannot create file")

    def test_except_filesystem_error_catches_directory_creation(self):
        with pytest.raises(ExperimentFileSystemError):
            raise ExperimentDirectoryCreationError(LOG, "cannot create dir")

    def test_except_filesystem_error_catches_removal(self):
        with pytest.raises(ExperimentFileSystemError):
            raise ExperimentRemovalError(LOG, "cannot remove")

    def test_except_filesystem_error_catches_dir_already_exists(self):
        with pytest.raises(ExperimentFileSystemError):
            raise ExperimentDirectoryAlreadyExistsError(LOG, "already exists")

    def test_except_filesystem_error_catches_dir_does_not_exist(self):
        with pytest.raises(ExperimentFileSystemError):
            raise ExperimentDirectoryDoesNotExistError(LOG, "not found")

    def test_except_filesystem_error_catches_file_missing(self):
        with pytest.raises(ExperimentFileSystemError):
            raise ExperimentFileMissingError(LOG, "missing")

    def test_except_config_error_catches_no_environment(self):
        with pytest.raises(ExperimentConfigError):
            raise NoEnvironmentError(LOG, "no env")

    def test_except_config_error_catches_multiple_environments(self):
        with pytest.raises(ExperimentConfigError):
            raise MultipleEnvironmentsError(LOG, "too many envs")

    def test_except_integrity_error_catches_environment_integrity(self):
        with pytest.raises(ExperimentIntegrityError):
            raise EnvironmentIntegrityError(LOG, "env broken")

    def test_except_integrity_error_catches_testfunction_integrity(self):
        with pytest.raises(ExperimentIntegrityError):
            raise TestfunctionIntegrityError(LOG, "tf broken")

    def test_except_experiment_exception_catches_all_error_subclasses(self):
        """ExperimentException is the common base for every error subclass."""
        for exc_cls, args in [
            (ExperimentFileCreationError, (LOG, "x")),
            (ExperimentDirectoryCreationError, (LOG, "x")),
            (ExperimentRemovalError, (LOG, "x")),
            (ExperimentDirectoryAlreadyExistsError, (LOG, "x")),
            (ExperimentDirectoryDoesNotExistError, (LOG, "x")),
            (ExperimentFileMissingError, (LOG, "x")),
            (ExperimentIntegrityError, (LOG, "x")),
            (EnvironmentIntegrityError, (LOG, "x")),
            (TestfunctionIntegrityError, (LOG, "x")),
            (NoEnvironmentError, (LOG, "x")),
            (MultipleEnvironmentsError, (LOG, "x")),
            (ExperimentAlreadyExistsError, (LOG, "x")),
            (ExperimentCommandError, (LOG, "cmd", 1)),
            (VMSetupError, (LOG, "vm", "cmd", 1)),
            (AdareVMProcessDiedError, (LOG, 1)),
        ]:
            with pytest.raises(ExperimentException):
                raise exc_cls(*args)


# ---------------------------------------------------------------------------
# Factory method tests
# ---------------------------------------------------------------------------

class TestFileModifiedFactory:
    """Tests for ExperimentIntegrityError.file_modified()."""

    def test_returns_correct_type(self):
        exc = ExperimentIntegrityError.file_modified(
            LOG, "Playbook", "main.yml", "adare experiment load"
        )
        assert isinstance(exc, ExperimentIntegrityError)

    def test_message_contains_file_type(self):
        exc = ExperimentIntegrityError.file_modified(
            LOG, "Playbook", "main.yml", "adare experiment load"
        )
        assert "Playbook" in str(exc)

    def test_message_contains_file_name(self):
        exc = ExperimentIntegrityError.file_modified(
            LOG, "Playbook", "main.yml", "adare experiment load"
        )
        assert "main.yml" in str(exc)

    def test_message_mentions_modified_after_loading(self):
        exc = ExperimentIntegrityError.file_modified(
            LOG, "Playbook", "main.yml", "adare experiment load"
        )
        assert "modified after loading" in str(exc)

    def test_solutions_contain_reload_command(self):
        exc = ExperimentIntegrityError.file_modified(
            LOG, "Playbook", "main.yml", "adare experiment load"
        )
        assert any("adare experiment load" in s for s in exc.possible_solutions)

    def test_solutions_contain_unauthorized_check(self):
        exc = ExperimentIntegrityError.file_modified(
            LOG, "Playbook", "main.yml", "adare experiment load"
        )
        assert any("unauthorized" in s for s in exc.possible_solutions)


class TestFileNotFoundFactory:
    """Tests for ExperimentIntegrityError.file_not_found()."""

    def test_returns_correct_type(self):
        exc = ExperimentIntegrityError.file_not_found(
            LOG, "Environment", "/path/to/env.yml"
        )
        assert isinstance(exc, ExperimentIntegrityError)

    def test_message_contains_file_type_and_path(self):
        exc = ExperimentIntegrityError.file_not_found(
            LOG, "Environment", "/path/to/env.yml"
        )
        assert "Environment" in str(exc)
        assert "/path/to/env.yml" in str(exc)

    def test_internal_path_solutions(self):
        exc = ExperimentIntegrityError.file_not_found(
            LOG, "Environment", "/path/to/env.yml", is_external=False
        )
        assert any("properly loaded" in s for s in exc.possible_solutions)
        assert not any("external path" in s for s in exc.possible_solutions)

    def test_external_path_solutions(self):
        exc = ExperimentIntegrityError.file_not_found(
            LOG, "Environment", "/mnt/share/env.yml", is_external=True
        )
        assert any("external path" in s for s in exc.possible_solutions)

    def test_solutions_always_include_exists_check(self):
        for external in (True, False):
            exc = ExperimentIntegrityError.file_not_found(
                LOG, "Playbook", "/p", is_external=external
            )
            assert any("exists at" in s for s in exc.possible_solutions)


class TestFilesChangedAfterLoadFactory:
    """Tests for ExperimentIntegrityError.files_changed_after_load()."""

    def test_returns_correct_type(self):
        exc = ExperimentIntegrityError.files_changed_after_load(
            LOG, "Testfunction", ["tf1.py"], "adare tf remove", "adare tf load"
        )
        assert isinstance(exc, ExperimentIntegrityError)

    def test_message_lists_changed_files(self):
        exc = ExperimentIntegrityError.files_changed_after_load(
            LOG, "Testfunction", ["alpha.py", "beta.py"],
            "adare tf remove", "adare tf load"
        )
        assert "alpha.py" in str(exc)
        assert "beta.py" in str(exc)

    def test_message_truncates_after_five_files(self):
        files = [f"file{i}.py" for i in range(8)]
        exc = ExperimentIntegrityError.files_changed_after_load(
            LOG, "Testfunction", files, "rm", "load"
        )
        msg = str(exc)
        # First five should be present
        for f in files[:5]:
            assert f in msg
        # 6th should NOT be listed individually
        assert "file5.py" not in msg
        # Truncation notice
        assert "and 3 more" in msg

    def test_exactly_five_files_no_truncation(self):
        files = [f"f{i}.py" for i in range(5)]
        exc = ExperimentIntegrityError.files_changed_after_load(
            LOG, "Testfunction", files, "rm", "load"
        )
        assert "more" not in str(exc)

    def test_solutions_contain_remove_and_load_commands(self):
        exc = ExperimentIntegrityError.files_changed_after_load(
            LOG, "Testfunction", ["a.py"],
            "adare tf remove --all", "adare tf load"
        )
        assert any("adare tf remove --all" in s for s in exc.possible_solutions)
        assert any("adare tf load" in s for s in exc.possible_solutions)


class TestHashMismatchFactory:
    """Tests for ExperimentIntegrityError.hash_mismatch()."""

    def test_returns_correct_type(self):
        exc = ExperimentIntegrityError.hash_mismatch(LOG, "Playbook", "main.yml")
        assert isinstance(exc, ExperimentIntegrityError)

    def test_message_contains_file_type_and_name(self):
        exc = ExperimentIntegrityError.hash_mismatch(LOG, "Playbook", "main.yml")
        assert "Playbook" in str(exc)
        assert "main.yml" in str(exc)

    def test_message_mentions_hash(self):
        exc = ExperimentIntegrityError.hash_mismatch(LOG, "Playbook", "main.yml")
        assert "hash" in str(exc).lower()

    def test_solutions_mention_reload(self):
        exc = ExperimentIntegrityError.hash_mismatch(LOG, "Playbook", "main.yml")
        assert any("Reload" in s for s in exc.possible_solutions)

    def test_solutions_mention_unauthorized(self):
        exc = ExperimentIntegrityError.hash_mismatch(LOG, "Playbook", "main.yml")
        assert any("unauthorized" in s for s in exc.possible_solutions)


class TestVMIntegrityFailedFactory:
    """Tests for ExperimentIntegrityError.vm_integrity_failed()."""

    def test_returns_correct_type(self):
        exc = ExperimentIntegrityError.vm_integrity_failed(
            LOG, "ubuntu22", "disk image missing"
        )
        assert isinstance(exc, ExperimentIntegrityError)

    def test_message_contains_vm_name_and_detail(self):
        exc = ExperimentIntegrityError.vm_integrity_failed(
            LOG, "ubuntu22", "disk image missing"
        )
        assert "ubuntu22" in str(exc)
        assert "disk image missing" in str(exc)

    def test_solutions_mention_verify_and_reimport(self):
        exc = ExperimentIntegrityError.vm_integrity_failed(
            LOG, "ubuntu22", "disk image missing"
        )
        assert any("Verify" in s for s in exc.possible_solutions)
        assert any("Re-import" in s for s in exc.possible_solutions)


# ---------------------------------------------------------------------------
# Factory methods produce raiseable exceptions
# ---------------------------------------------------------------------------

class TestFactoryMethodsAreRaiseable:
    """Ensure factory-produced exceptions can be raised and caught properly."""

    def test_file_modified_is_raiseable(self):
        exc = ExperimentIntegrityError.file_modified(
            LOG, "Playbook", "main.yml", "adare experiment load"
        )
        with pytest.raises(ExperimentIntegrityError):
            raise exc

    def test_file_not_found_is_raiseable(self):
        exc = ExperimentIntegrityError.file_not_found(
            LOG, "Env", "/p"
        )
        with pytest.raises(ExperimentIntegrityError):
            raise exc

    def test_files_changed_after_load_is_raiseable(self):
        exc = ExperimentIntegrityError.files_changed_after_load(
            LOG, "TF", ["a.py"], "rm", "load"
        )
        with pytest.raises(ExperimentIntegrityError):
            raise exc

    def test_hash_mismatch_is_raiseable(self):
        exc = ExperimentIntegrityError.hash_mismatch(LOG, "PB", "x.yml")
        with pytest.raises(ExperimentIntegrityError):
            raise exc

    def test_vm_integrity_failed_is_raiseable(self):
        exc = ExperimentIntegrityError.vm_integrity_failed(
            LOG, "vm1", "bad disk"
        )
        with pytest.raises(ExperimentIntegrityError):
            raise exc

    def test_factory_caught_by_experiment_exception(self):
        """Factory results are also caught by the root ExperimentException."""
        exc = ExperimentIntegrityError.file_modified(
            LOG, "Playbook", "main.yml", "reload"
        )
        with pytest.raises(ExperimentException):
            raise exc

    def test_factory_caught_by_logged_error_exception(self):
        """Factory results are caught by the original LoggedErrorException base."""
        exc = ExperimentIntegrityError.hash_mismatch(LOG, "PB", "x.yml")
        with pytest.raises(LoggedErrorException):
            raise exc
