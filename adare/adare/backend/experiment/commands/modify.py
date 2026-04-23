# external imports
import logging
from pathlib import Path

# internal imports
from adare.backend.experiment.commands.load import experiment_load
from adare.backend.experiment.directory import ExperimentDirectory
from adare.backend.project.directory import ProjectDirectory

log = logging.getLogger(__name__)


def experiment_remove_environments(project_path: Path, experiment_pattern: str, environment_names: list[str], force: bool = False):
    """Remove environments from experiments matching the pattern."""
    import glob

    from adare.console import print_success_message

    # Find matching experiments using glob
    project_directory = ProjectDirectory(project_path)
    experiments_dir = project_directory.experiments

    # Use glob to find matching experiment directories
    pattern_path = experiments_dir / experiment_pattern
    matching_paths = glob.glob(str(pattern_path))

    if not matching_paths:
        from adare.exceptions import LoggedErrorException
        raise LoggedErrorException(
            log,
            f'No experiments found matching pattern: {experiment_pattern}',
            possible_solutions=[
                f'Check if pattern "{experiment_pattern}" is correct',
                'List experiments with: adare experiment list',
                'Use exact experiment name if no pattern matching needed'
            ]
        )

    # Extract experiment names from paths
    experiment_names = [Path(p).name for p in matching_paths]

    log.info(f"Found {len(experiment_names)} experiment(s) matching pattern '{experiment_pattern}':")
    for exp_name in experiment_names:
        log.info(f"  - {exp_name}")
    log.info(f"Removing environment(s): {', '.join(environment_names)}")
    log.info("")

    # Process each experiment
    updated_experiments = []
    failed_experiments = []

    for exp_name in experiment_names:
        try:
            exp_dir = ExperimentDirectory(project_path, exp_name)
            if not exp_dir.exists():
                log.warning(f"Experiment directory not found: {exp_name}, skipping")
                failed_experiments.append(exp_name)
                continue

            # Load current metadata
            metadata = exp_dir.load_metadata()
            original_envs = set(metadata.environments)

            # Remove specified environments
            envs_to_remove = set(environment_names)
            updated_envs = original_envs - envs_to_remove

            # Check if anything actually changed
            if updated_envs == original_envs:
                log.info(f"Experiment '{exp_name}' doesn't have any of the specified environments, skipping")
                continue

            # Validate that we're not removing all environments
            if not updated_envs:
                if not force:
                    log.warning(f"Cannot remove all environments from experiment '{exp_name}' without --force flag")
                    failed_experiments.append(exp_name)
                    continue
                log.warning(f"Removing ALL environments from experiment '{exp_name}' due to --force flag")

            # Update metadata
            metadata.environments = sorted(list(updated_envs))

            # Save updated metadata
            exp_dir.save_metadata(metadata)
            log.info(f"Updated metadata for experiment: {exp_name}")

            # Reload experiment to update database (if it still has environments)
            if updated_envs:
                experiment_load(project_path, exp_name, force=True, silent=True)
                log.info(f"Reloaded experiment: {exp_name}")
            else:
                log.warning(f"Experiment '{exp_name}' now has no environments and may become inaccessible")

            updated_experiments.append(exp_name)

        except Exception as e:
            log.error(f"Failed to update experiment '{exp_name}': {e}")
            failed_experiments.append(exp_name)

    # Print summary
    if updated_experiments:
        print_success_message(
            title=f"Successfully removed environments from {len(updated_experiments)} experiment(s)",
            location=f"Experiments: {', '.join(updated_experiments)}",
            next_steps=[
                f"Removed environments: {', '.join(environment_names)}",
                "Experiments have been reloaded automatically",
                "Check remaining environments with: adare experiment info <name>"
            ]
        )

    if failed_experiments:
        log.warning(f"Failed to update {len(failed_experiments)} experiment(s): {', '.join(failed_experiments)}")


def experiment_add_environments(project_path: Path, experiment_pattern: str, environment_names: list[str], force: bool = False):
    """Add environments to experiments matching the pattern."""
    import glob

    from adare.console import print_success_message

    # Find matching experiments using glob
    project_directory = ProjectDirectory(project_path)
    experiments_dir = project_directory.experiments

    # Use glob to find matching experiment directories
    pattern_path = experiments_dir / experiment_pattern
    matching_paths = glob.glob(str(pattern_path))

    if not matching_paths:
        from adare.exceptions import LoggedErrorException
        raise LoggedErrorException(
            log,
            f'No experiments found matching pattern: {experiment_pattern}',
            possible_solutions=[
                f'Check if pattern "{experiment_pattern}" is correct',
                'List experiments with: adare experiment list',
                'Use exact experiment name if no pattern matching needed'
            ]
        )

    # Extract experiment names from paths
    experiment_names = [Path(p).name for p in matching_paths]

    # Validate all environments exist in project before proceeding
    from adare.database.api.environment import EnvironmentDbApi
    with EnvironmentDbApi() as env_db:
        project_environments = {env.name for env in env_db.get_environments(project_path)}

    missing_envs = [env for env in environment_names if env not in project_environments]
    if missing_envs:
        from adare.exceptions import LoggedErrorException
        raise LoggedErrorException(
            log,
            f'Environment(s) not found in project: {", ".join(missing_envs)}',
            possible_solutions=[
                'Create missing environments with: adare environment create <name>',
                'Load existing environments with: adare environment load <file>',
                'List available environments with: adare environment list'
            ]
        )

    log.info(f"Found {len(experiment_names)} experiment(s) matching pattern '{experiment_pattern}':")
    for exp_name in experiment_names:
        log.info(f"  - {exp_name}")
    log.info(f"Adding environment(s): {', '.join(environment_names)}")
    log.info("")

    # Process each experiment
    updated_experiments = []
    failed_experiments = []
    skipped_experiments = []  # Track experiments that already have the environments
    environment_missing_experiments = []  # Track experiments where environments aren't in global database

    for exp_name in experiment_names:
        try:
            exp_dir = ExperimentDirectory(project_path, exp_name)
            if not exp_dir.exists():
                log.warning(f"Experiment directory not found: {exp_name}, skipping")
                failed_experiments.append(exp_name)
                continue

            # Load current metadata
            metadata = exp_dir.load_metadata()
            original_envs = set(metadata.environments)

            # Add new environments (avoid duplicates)
            new_envs = set(environment_names)
            updated_envs = original_envs | new_envs

            # Check if anything actually changed
            if updated_envs == original_envs:
                log.info(f"Experiment '{exp_name}' already has all specified environments, skipping")
                skipped_experiments.append(exp_name)
                continue

            # Update metadata
            metadata.environments = sorted(list(updated_envs))

            # Save updated metadata
            exp_dir.save_metadata(metadata)
            log.info(f"Updated metadata for experiment: {exp_name}")

            # Reload experiment to update database
            experiment_load(project_path, exp_name, force=True, silent=True)
            log.info(f"Reloaded experiment: {exp_name}")

            updated_experiments.append(exp_name)

        except Exception as e:
            from adare.database.exceptions import EnvironmentMissingError
            if isinstance(e, EnvironmentMissingError):
                log.error(f"Environment(s) not found in global database for experiment '{exp_name}': {', '.join(environment_names)}")
                environment_missing_experiments.append(exp_name)
            else:
                log.error(f"Failed to update experiment '{exp_name}': {e}")
                failed_experiments.append(exp_name)

    # Print comprehensive summary
    total_processed = len(updated_experiments) + len(skipped_experiments) + len(failed_experiments) + len(environment_missing_experiments)

    if updated_experiments:
        print_success_message(
            title=f"Successfully added environments to {len(updated_experiments)} experiment(s)",
            next_steps=[
                "Run experiment in new environments with: adare experiment run <name> -e <environment>",
            ]
        )

    if skipped_experiments:
        log.info(f"\n{len(skipped_experiments)} experiment(s) already had the specified environment(s): {', '.join(skipped_experiments)}")

    if environment_missing_experiments:
        from adare.console import print_error_message
        print_error_message(
            title=f"Environment(s) not found in global database for {len(environment_missing_experiments)} experiment(s)",
            details=f"Experiments: {', '.join(environment_missing_experiments)}\nEnvironment(s): {', '.join(environment_names)}",
            possible_solutions=[
                "Check if environment names are spelled correctly",
                "Load environments to global database with: adare environment load <environment_file>",
                "Create environments with: adare environment create <name>",
                "List available environments with: adare environment list"
            ]
        )

    if failed_experiments:
        from adare.console import print_error_message
        print_error_message(
            title=f"Failed to update {len(failed_experiments)} experiment(s)",
            details=f"Experiments: {', '.join(failed_experiments)}",
            possible_solutions=[
                "Check experiment metadata.yml files for syntax errors",
                "Ensure experiment directories exist and are accessible",
                "Check log output above for specific error details"
            ]
        )

    # Final status summary
    if total_processed == 0:
        log.info("\nNo experiments were processed.")
    elif updated_experiments or skipped_experiments:
        log.info(f"\nSummary: {len(updated_experiments)} updated, {len(skipped_experiments)} already had environments, {len(environment_missing_experiments)} missing environments, {len(failed_experiments)} failed.")
    else:
        log.info("\nNo experiments were successfully updated. See error details above.")
