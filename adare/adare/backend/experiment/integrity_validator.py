"""
Integrity validation for experiments, projects, and playbook testfunctions.

Extracted from run.py to keep the orchestrator focused on execution flow.
"""

from pathlib import Path

# configure logging
import logging
log = logging.getLogger(__name__)


class IntegrityValidator:
    """Validates integrity of project files, experiments, and playbook testfunctions.

    Accepts dependencies via constructor so callers can inject the required
    paths and directory helpers without coupling to global state.
    """

    def __init__(
        self,
        project_path: Path,
        project_directory=None,  # ProjectDirectory (optional, needed for project checks)
    ):
        self.project_path = project_path
        self.project_directory = project_directory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify_playbook_testfunctions(self, playbook) -> None:
        """Verify integrity of all testfunctions referenced by *playbook*.

        Raises:
            ExperimentIntegrityError: if a testfunction is missing from the
                database or its hash no longer matches the stored value.
            LoggedException: if the testfunction database cannot be read.
        """
        from adare.helperfunctions.integrity import verify_testfunction_integrity
        from adare.backend.testfunction.database import get_testfunction_files_data
        from adare.backend.experiment.exceptions import ExperimentIntegrityError
        from adare.exceptions import LoggedException

        # Extract testfunction names from playbook tests
        testfunction_names: set[str] = set()
        if hasattr(playbook, 'tests') and playbook.tests:
            for test in playbook.tests:
                if hasattr(test, 'testfunction'):
                    testfunction_names.add(test.testfunction)

        if not testfunction_names:
            log.info("No testfunctions found in playbook - skipping integrity verification")
            return

        log.info(f"Verifying integrity of {len(testfunction_names)} testfunctions used in playbook")

        try:
            # Get all testfunction data from database
            tf_data = get_testfunction_files_data(
                self.project_path,
                fields=['path', 'requirements_path', 'sha256hash', 'name']
            )

            # Create lookup by testfunction directory name
            tf_lookup: dict = {}
            for tf in tf_data:
                tf_path = Path(tf['path'])
                tf_dir_name = tf_path.parent.name
                tf_lookup[tf_dir_name] = tf

            # Verify integrity of each required testfunction
            verified_count = 0
            for tf_name in testfunction_names:
                if tf_name not in tf_lookup:
                    raise ExperimentIntegrityError(
                        log,
                        f"Testfunction '{tf_name}' used in playbook is not loaded in database",
                        possible_solutions=[
                            f"Load testfunction with 'adare testfunction load {tf_name}'",
                            "Check if testfunction directory exists",
                            "Verify testfunction name spelling in playbook"
                        ]
                    )

                tf_info = tf_lookup[tf_name]
                tf_path = Path(tf_info['path'])
                req_path = Path(tf_info['requirements_path'])
                expected_hash = tf_info['sha256hash']

                verify_testfunction_integrity(tf_path, req_path, expected_hash)
                verified_count += 1
                log.debug(f"Testfunction integrity verified: {tf_name}")

            log.info(
                f"Testfunction integrity verification completed: "
                f"{verified_count}/{len(testfunction_names)} verified"
            )

        except ExperimentIntegrityError:
            raise
        except ImportError as e:
            log.warning(f"Integrity verification modules not available: {e}")
        except (FileNotFoundError, KeyError) as e:
            log.error(f"Testfunction database access failed: {e}")
            raise LoggedException(log, f"Failed to access testfunction database for integrity verification: {e}")

    def check_project(
        self,
        environments: list[Path] | None = None,
        testfunctions: list[Path] | None = None,
    ) -> None:
        """Check project integrity (testfunctions + environments).

        Raises:
            ExperimentIntegrityError: if any testfunction or environment
                file has been modified after loading.
        """
        from adare.helperfunctions.integrity import (
            verify_testfunction_integrity,
            verify_environment_integrity,
        )
        import adare.backend.project.database as project_database
        from adare.backend.experiment.exceptions import ExperimentIntegrityError

        # --- Testfunctions ---------------------------------------------------
        testfunctions_changed: list = []
        hashes: list = project_database.get_global_testfunction_hashes()
        for hash_dict in hashes:
            file = hash_dict['file']
            requirements_file = hash_dict['requirements']
            hash_value = hash_dict['hash']
            path = Path(file)
            requirements_path = Path(requirements_file)

            if testfunctions and path not in testfunctions:
                continue

            try:
                verify_testfunction_integrity(path, requirements_path, hash_value)
                log.info(f'integrity check for testfunction file {path} passed')
            except ExperimentIntegrityError:
                testfunctions_changed.append(path)
                log.info(f'integrity check for testfunction file {path} failed')

        if testfunctions_changed:
            raise ExperimentIntegrityError.files_changed_after_load(
                log,
                file_type='testfunction',
                changed_files=testfunctions_changed,
                remove_command='adare testfunction remove <name>',
                load_command='adare testfunction load <name>',
            )

        # --- Environments ----------------------------------------------------
        environments_changed: list = []
        env_hashes: dict = project_database.get_global_environment_hashes()
        for file, hash_value in env_hashes.items():
            path = Path(file)
            if environments and path not in environments:
                continue

            try:
                verify_environment_integrity(path, hash_value)
                log.info(f'integrity check for environment {path} passed')
            except ExperimentIntegrityError:
                environments_changed.append(path)
                log.info(f'integrity check for environment {path} failed')

        if environments_changed:
            raise ExperimentIntegrityError.files_changed_after_load(
                log,
                file_type='environment',
                changed_files=environments_changed,
                remove_command='adare environment remove <name>',
                load_command='adare environment load <name>',
            )

    def check_experiment(
        self,
        experiment_name: str,
        environment_name: str,
        experiment_directory,  # ExperimentDirectory
    ) -> None:
        """Check experiment file integrity (playbook hash).

        Raises:
            ExperimentIntegrityError: if the playbook has been modified
                after it was loaded.
        """
        import adare.backend.experiment.database as experiment_database
        from adare.backend.experiment.exceptions import ExperimentIntegrityError

        experiment_hashes = experiment_database.get_experiment_hashes(
            self.project_path, environment_name, experiment_name
        )
        experiment_ulid = experiment_database.get_experiment_by_project_and_name(
            self.project_path, experiment_name
        )
        experiment_run_count = experiment_database.get_experiment_run_count(
            self.project_path, experiment_ulid
        )

        file_changed: list[str] = []
        if experiment_directory.sha256_playbook != experiment_hashes['playbook']:
            file_changed.append('playbook')
        else:
            log.info(f'integrity check for playbook file {experiment_directory.playbookfile} passed')

        if not file_changed:
            return

        message = (
            'to ensure the integrity of an experiment, experiment related files '
            'are not allowed to be changed after the experiment has been loaded\n'
            f'However, the following files have been changed: {", ".join(file_changed)}'
        )
        solutions: list[str] = []
        if experiment_run_count == 0:
            solutions.append(
                f'since no experiment runs have been executed yet, you can simply '
                f'load the experiment again with `adare experiment load {experiment_name}` '
                f'to overwrite the existing experiment'
            )
        else:
            solutions.extend(
                (
                    'if you want to change the experiment, you have to delete all related '
                    'experiment runs with `adare experiment remove` and then load the '
                    'experiment again with `adare experiment load`',
                    'if you want to keep the experiment runs, you have to create a new '
                    'experiment with a different name and load the new experiment with '
                    '`adare experiment load`',
                )
            )

        raise ExperimentIntegrityError(
            log,
            message,
            possible_solutions=solutions
        )
