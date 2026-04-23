# external imports
import logging
from pathlib import Path

import adare.backend.experiment.database as experiment_database

# internal imports
from adare.backend.experiment.directory import ExperimentDirectory
from adare.backend.experiment.exceptions import (
    ExperimentIntegrityError,
)
from adare.exceptions import LoggedException

log = logging.getLogger(__name__)


def _get_testfunction_data_from_database():
    """
    Get testfunction data from the global database.

    Returns:
        list: List of (name, path) tuples for testfunction files
    """
    try:
        from adare.database.api.testfunction import TestfunctionDbApi

        with TestfunctionDbApi() as api:
            testfunction_files = api.get_testfunction_files()
            return [(tf_file.name, tf_file.path) for tf_file in testfunction_files]
    except Exception as e:
        log.warning(f"Failed to query testfunction files from database: {e}")
        return []


def __validate_testset_compatibility(experiment_directory: ExperimentDirectory):
    """Validate testset against available testfunctions during experiment loading."""
    playbook_path = experiment_directory.path / "playbook.yml"
    if not playbook_path.exists():
        log.info("No playbook.yml found - skipping testset validation")
        return  # No playbook to validate

    # Use global testfunctions directory only
    from adare.config.configdirectory import STATE_DIR
    testfunctions_dir = STATE_DIR / 'testfunctions'

    if not testfunctions_dir.exists():
        log.warning(f"Global testfunctions directory not found: {testfunctions_dir} - skipping validation")
        log.info("Load testfunctions using 'adare testfunction load-global <path>' to enable validation")
        return

    log.debug(f"Using global testfunctions directory: {testfunctions_dir}")

    try:
        from adarelib.testset.testfunction import get_missing_testfunctions, import_basictest_subclasses

        log.info("Validating testset compatibility with available testfunctions...")

        # Load testset from playbook
        testsetfile = experiment_directory.load_testset()

        # Try database-driven approach first, fallback to directory scanning
        supported_tests = None
        try:
            # Get testfunction data from database
            testfunction_source = _get_testfunction_data_from_database()
            if testfunction_source:
                log.debug("Using database-driven testfunction loading")
                supported_tests = import_basictest_subclasses(source=testfunction_source)
        except Exception as e:
            log.warning(f"Database-driven testfunction loading failed: {e}")

        # Fallback to directory scanning if database approach failed
        if not supported_tests:
            log.debug("Using directory-based testfunction loading")
            supported_tests = import_basictest_subclasses(directory=testfunctions_dir)

        # Check for missing testfunctions
        missing = get_missing_testfunctions(testsetfile, supported_tests)

        if missing:
            raise ExperimentIntegrityError(
                log,
                f"Testset contains unsupported testfunctions: {missing}",
                possible_solutions=[
                    "Load missing testfunction implementations using 'adare testfunction load-global <path>'",
                    "Remove invalid tests from testset.yml",
                    "Check testfunction naming matches class names",
                    "Ensure testfunction files are properly structured"
                ]
            )

        log.info(f"Testset validation passed - all {len(testsetfile.tests)} tests have valid testfunctions")

    except ImportError as e:
        log.warning(f"Could not import testset validation modules: {e}")
        log.warning("Skipping testset validation - validation will occur at runtime")
    except Exception as e:
        log.error(f"Testset validation error: {e}", exc_info=True)
        raise ExperimentIntegrityError(
            log,
            f"Testset validation failed: {str(e)}",
            possible_solutions=[
                "Check testset.yml syntax and structure",
                "Verify testfunctions directory structure",
                "Ensure all required testfunction dependencies are available"
            ]
        )


def experiment_validate(project_path: Path, experiment_name: str, environment_name: str = None):
    """Validate experiment configuration and integrity without starting a VM.

    Performs the following checks in order:
    1. Experiment structure (directory exists, required files present)
    2. YAML schema validation (playbook parses correctly)
    3. Variable validation (all references resolve)
    4. Test reference validation (testfunctions available)
    5. Environment compatibility (if environment specified)
    6. Integrity validation (hashes match stored values, if loaded in DB)

    Args:
        project_path: Path to the project directory
        experiment_name: Name of the experiment to validate
        environment_name: Optional environment name to check compatibility

    Returns:
        list of ValidationCheckResult DTOs
    """
    import cattrs
    import yaml

    from adare.core.dto.experiment import ValidationCheckResult
    from adare.parsers import parse_metadata_file

    checks: list[ValidationCheckResult] = []

    # --- 1. Experiment structure ---
    experiment_directory = ExperimentDirectory(project_path, experiment_name)
    if not experiment_directory.exists():
        checks.append(ValidationCheckResult(
            name='Experiment structure',
            passed=False,
            message=f'Experiment directory does not exist: {experiment_directory.path}',
        ))
        return checks  # Cannot continue without directory

    missing_files = []
    if not experiment_directory.playbookfile.exists():
        missing_files.append('playbook.yml')
    if not experiment_directory.metadatafile.exists():
        missing_files.append('metadata.yml')

    if missing_files:
        checks.append(ValidationCheckResult(
            name='Experiment structure',
            passed=False,
            message=f'Missing required files: {", ".join(missing_files)}',
        ))
        return checks  # Cannot continue without required files
    checks.append(ValidationCheckResult(
        name='Experiment structure',
        passed=True,
        message='Experiment directory and required files exist',
    ))

    # --- 2. Metadata validation ---
    try:
        metadata = parse_metadata_file(experiment_directory.metadatafile)
        checks.append(ValidationCheckResult(
            name='Metadata validation',
            passed=True,
            message='metadata.yml parsed successfully',
        ))
    except (ValueError, LoggedException) as e:
        checks.append(ValidationCheckResult(
            name='Metadata validation',
            passed=False,
            message=f'metadata.yml parsing failed: {e}',
        ))

    # --- 3. YAML schema validation ---
    playbook = None
    try:
        from adare.types.playbook import parse_playbook
        playbook = parse_playbook(experiment_directory.playbookfile)
        checks.append(ValidationCheckResult(
            name='YAML schema validation',
            passed=True,
            message=f'playbook.yml parsed successfully ({len(playbook.actions)} actions, {len(playbook.tests)} tests)',
        ))
    except (ValueError, TypeError) as e:
        checks.append(ValidationCheckResult(
            name='YAML schema validation',
            passed=False,
            message=f'Playbook validation failed: {e}',
        ))
    except (yaml.YAMLError, cattrs.BaseValidationError, KeyError, AttributeError) as e:
        checks.append(ValidationCheckResult(
            name='YAML schema validation',
            passed=False,
            message=f'Playbook parsing failed: {e}',
        ))

    # --- 4. Variable validation (only if playbook parsed) ---
    if playbook is not None:
        try:
            from adare.types.playbook_validators import (
                DuplicateVariableValidator,
                FilterValidator,
                ValidationResult,
                VariableDefinitionValidator,
                VariableUsageValidator,
            )
            usage_validator = VariableUsageValidator()
            duplicate_validator = DuplicateVariableValidator()
            definition_validator = VariableDefinitionValidator(usage_validator)
            filter_validator = FilterValidator(usage_validator)

            combined = ValidationResult()
            for validator in [usage_validator, duplicate_validator, definition_validator, filter_validator]:
                combined.merge(validator.validate(playbook))

            if combined.is_valid:
                checks.append(ValidationCheckResult(
                    name='Variable validation',
                    passed=True,
                    message='All variable references resolve correctly',
                ))
            else:
                error_msgs = [str(err) for err in combined.errors]
                checks.append(ValidationCheckResult(
                    name='Variable validation',
                    passed=False,
                    message='\n'.join(error_msgs),
                ))
            for warning in combined.warnings:
                checks.append(ValidationCheckResult(
                    name='Variable validation',
                    passed=True,
                    message=warning,
                    is_warning=True,
                ))
        except ImportError as e:
            checks.append(ValidationCheckResult(
                name='Variable validation',
                passed=True,
                message=f'Variable validation modules not available: {e}',
                is_warning=True,
            ))

    # --- 5. Test reference validation ---
    if playbook is not None and playbook.tests:
        try:
            from adare.config.configdirectory import STATE_DIR
            testfunctions_dir = STATE_DIR / 'testfunctions'

            if not testfunctions_dir.exists():
                checks.append(ValidationCheckResult(
                    name='Test reference validation',
                    passed=True,
                    message='Global testfunctions directory not found — skipping (load testfunctions first)',
                    is_warning=True,
                ))
            else:
                # Try database-driven approach first
                supported_tests = None
                try:
                    testfunction_source = _get_testfunction_data_from_database()
                    if testfunction_source:
                        from adarelib.testset.testfunction import import_basictest_subclasses
                        supported_tests = import_basictest_subclasses(source=testfunction_source)
                except (ImportError, OSError, KeyError):
                    pass

                if not supported_tests:
                    from adarelib.testset.testfunction import import_basictest_subclasses
                    supported_tests = import_basictest_subclasses(directory=testfunctions_dir)

                # Check which test functions are missing
                from adarelib.testset.testfunction import get_missing_testfunctions
                testset = experiment_directory.load_testset()
                missing = get_missing_testfunctions(testset, supported_tests)

                if missing:
                    checks.append(ValidationCheckResult(
                        name='Test reference validation',
                        passed=False,
                        message=f'Missing testfunctions: {missing}',
                    ))
                else:
                    checks.append(ValidationCheckResult(
                        name='Test reference validation',
                        passed=True,
                        message=f'All {len(playbook.tests)} test references are valid',
                    ))
        except ImportError as e:
            checks.append(ValidationCheckResult(
                name='Test reference validation',
                passed=True,
                message=f'Testfunction validation modules not available: {e}',
                is_warning=True,
            ))
        except (ExperimentIntegrityError, LoggedException) as e:
            checks.append(ValidationCheckResult(
                name='Test reference validation',
                passed=False,
                message=f'Test reference validation failed: {e}',
            ))
    elif playbook is not None:
        checks.append(ValidationCheckResult(
            name='Test reference validation',
            passed=True,
            message='No tests defined in playbook — skipping',
            is_warning=True,
        ))

    # --- 6. Environment compatibility ---
    if environment_name:
        try:
            from adare.database.api.experiment import ExperimentApi
            with ExperimentApi(project_path) as api:
                environment = api.get_environment(environment_name, project_path.name)
                if environment is None:
                    checks.append(ValidationCheckResult(
                        name='Environment compatibility',
                        passed=False,
                        message=f'Environment "{environment_name}" not found in project',
                    ))
                else:
                    # Check if environment is listed in experiment metadata
                    try:
                        metadata = experiment_directory.load_metadata()
                        if environment_name in metadata.environments:
                            checks.append(ValidationCheckResult(
                                name='Environment compatibility',
                                passed=True,
                                message=f'Environment "{environment_name}" is compatible with experiment',
                            ))
                        else:
                            checks.append(ValidationCheckResult(
                                name='Environment compatibility',
                                passed=True,
                                message=f'Environment "{environment_name}" is not listed in metadata.yml '
                                        f'(listed: {", ".join(metadata.environments) or "none"})',
                                is_warning=True,
                            ))
                    except (ValueError, LoggedException, OSError) as e:
                        checks.append(ValidationCheckResult(
                            name='Environment compatibility',
                            passed=True,
                            message=f'Environment "{environment_name}" exists but metadata could not be checked: {e}',
                            is_warning=True,
                        ))
        except (ValueError, LoggedException, OSError) as e:
            checks.append(ValidationCheckResult(
                name='Environment compatibility',
                passed=False,
                message=f'Environment check failed: {e}',
            ))

    # --- 7. Integrity validation ---
    experiment_ulid = experiment_database.get_experiment_by_project_and_name(
        project_path, experiment_name, trigger_error=False
    )
    if not experiment_ulid:
        checks.append(ValidationCheckResult(
            name='Integrity validation',
            passed=True,
            message='Experiment not loaded in database — integrity check skipped (load first)',
            is_warning=True,
        ))
    else:
        try:
            # Compare playbook hash with stored value
            hashes = experiment_database.get_experiment_hashes(
                project_path, environment_name or experiment_name, experiment_name
            )
            current_hash = experiment_directory.sha256_playbook
            stored_hash = hashes.get('playbook', '')
            if current_hash == stored_hash:
                checks.append(ValidationCheckResult(
                    name='Integrity validation',
                    passed=True,
                    message='Playbook hash matches database — no modifications detected',
                ))
            else:
                checks.append(ValidationCheckResult(
                    name='Integrity validation',
                    passed=False,
                    message='Playbook has been modified since last load',
                ))
        except (ValueError, KeyError) as e:
            checks.append(ValidationCheckResult(
                name='Integrity validation',
                passed=True,
                message=f'Integrity check could not complete: {e}',
                is_warning=True,
            ))

    return checks
