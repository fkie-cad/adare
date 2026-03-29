# external imports
from pathlib import Path
from typing import Literal
import shutil

# internal imports
from adare.backend.project.directory import ProjectDirectory
from adare.exceptions import LoggedException

# configure logging
import logging
log = logging.getLogger(__name__)


ResourceType = Literal['experiments', 'environments', 'testfunctions']


class InvalidPathError(LoggedException):
    """Exception raised when a relative path is invalid or outside project boundaries."""
    pass


def _copy_external_experiment(external_path: Path, experiments_dir: Path) -> tuple[str, bool]:
    """
    Copy external experiment directory to project experiments directory.

    Args:
        external_path: Path to external experiment directory
        experiments_dir: Project experiments directory

    Returns:
        Tuple of (experiment_name, was_copied) where:
        - experiment_name: Name of the experiment (directory name)
        - was_copied: True if directory was copied, False if it already existed

    Raises:
        InvalidPathError: If copy fails
    """
    experiment_name = external_path.name
    target_path = experiments_dir / experiment_name

    # Check if target already exists - return name without copying
    if target_path.exists():
        log.info(f'Experiment directory "{experiment_name}" already exists, using existing directory')
        return experiment_name, False

    try:
        # Ensure experiments directory exists
        experiments_dir.mkdir(parents=True, exist_ok=True)

        # Copy the entire external experiment directory
        shutil.copytree(external_path, target_path)
        log.info(f'Copied external experiment from {external_path} to {target_path}')

        return experiment_name, True

    except OSError as e:
        # Clean up on failure
        if target_path.exists():
            shutil.rmtree(target_path, ignore_errors=True)
        raise InvalidPathError(
            log,
            f'Failed to copy external experiment from "{external_path}" to "{target_path}": {str(e)}'
        ) from e


def resolve_path_to_name(input_path: str, project_dir: Path, resource_type: ResourceType) -> str:
    """
    Convert relative path or name to resource name.

    Args:
        input_path: User input - either a simple name or relative path
        project_dir: Project directory path
        resource_type: Type of resource (experiments, environments, testfunctions)

    Returns:
        Resource name extracted from path or the original name

    Raises:
        InvalidPathError: If relative path is invalid or outside project boundaries
    """
    # If input contains path separators, treat as relative path
    if '/' in input_path or '\\' in input_path:
        return _resolve_relative_path(input_path, project_dir, resource_type)
    else:
        # Simple name - return as-is for backward compatibility
        return input_path


def _resolve_relative_path(relative_path: str, project_dir: Path, resource_type: ResourceType) -> str:
    """
    Resolve relative path to resource name and validate it's within project boundaries.

    Args:
        relative_path: Relative path string
        project_dir: Project directory path
        resource_type: Type of resource directory

    Returns:
        Resource name extracted from the path

    Raises:
        InvalidPathError: If path is invalid or outside boundaries
    """
    project_directory = ProjectDirectory(project_dir)

    # Get the appropriate resource directory
    resource_dir_map = {
        'experiments': project_directory.experiments,
        'environments': project_directory.environments,
        'testfunctions': project_directory.testfunctions
    }
    resource_dir = resource_dir_map[resource_type]

    try:
        # Convert to Path object and resolve
        input_path = Path(relative_path)

        # Handle relative paths starting with ./
        if input_path.is_absolute():
            resolved_path = input_path
        else:
            # Resolve relative to current working directory (should be project dir)
            resolved_path = (Path.cwd() / input_path).resolve()

        # For environments, allow external files; for others, check within resource directory
        if resource_type == 'environments':
            # For environments, if the file exists externally, return the full path
            if resolved_path.exists() and resolved_path.suffix in ['.yml', '.yaml']:
                # Check if it's outside the project environments directory
                try:
                    resolved_path.relative_to(resource_dir.resolve())
                    # It's within the project directory, return just the name
                    name = resolved_path.stem
                except ValueError:
                    # It's external, return the full path
                    name = str(resolved_path)
            else:
                # Try to find within project environments directory
                try:
                    relative_to_resource = resolved_path.relative_to(resource_dir.resolve())
                    name_with_ext = relative_to_resource.parts[0] if relative_to_resource.parts else relative_path
                    name = Path(name_with_ext).stem
                except ValueError:
                    raise InvalidPathError(
                        log,
                        f'Environment file "{relative_path}" not found and not within the environments directory.'
                    )
        else:
            # For experiments and testfunctions, check if within resource directory
            try:
                relative_to_resource = resolved_path.relative_to(resource_dir.resolve())
                name = relative_to_resource.parts[0] if relative_to_resource.parts else relative_path
            except ValueError:
                # Path is outside resource directory - handle external experiments
                if resource_type == 'experiments':
                    if resolved_path.exists() and resolved_path.is_dir():
                        name, _ = _copy_external_experiment(resolved_path, resource_dir)
                    else:
                        # Provide more specific error for experiments
                        if not resolved_path.exists():
                            raise InvalidPathError(
                                log,
                                f'External experiment path "{relative_path}" does not exist. Please check the path and try again.'
                            )
                        else:
                            raise InvalidPathError(
                                log,
                                f'External experiment path "{relative_path}" exists but is not a directory.'
                            )
                else:
                    # For non-experiments, keep original behavior
                    raise InvalidPathError(
                        log,
                        f'Path "{relative_path}" is not within the {resource_type} directory. Use a path within the {resource_type}/ directory or just the {resource_type[:-1]} name without path separators.'
                    )

        return name

    except Exception as e:
        if isinstance(e, InvalidPathError):
            raise
        raise InvalidPathError(
            log,
            f'Failed to resolve path "{relative_path}": {str(e)}. Check that the path is valid and exists. Ensure the path points to a {resource_type[:-1]} within the {resource_type}/ directory.'
        )


def resolve_experiment_path(input_path: str, project_dir: Path) -> str:
    """Resolve experiment path or name to experiment name."""
    return resolve_path_to_name(input_path, project_dir, 'experiments')


def resolve_environment_path(input_path: str, project_dir: Path) -> str:
    """Resolve environment path or name to environment name."""
    return resolve_path_to_name(input_path, project_dir, 'environments')


def resolve_testfunction_path(input_path: str, project_dir: Path) -> str:
    """Resolve testfunction path or name to testfunction name."""
    return resolve_path_to_name(input_path, project_dir, 'testfunctions')