# external imports
from pathlib import Path
from typing import Literal

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

        # Check if resolved path is within the appropriate resource directory
        try:
            # Get relative path from resource directory to target
            relative_to_resource = resolved_path.relative_to(resource_dir.resolve())
        except ValueError:
            raise InvalidPathError(
                log,
                f'Path "{relative_path}" is not within the {resource_type} directory',
                possible_solutions=[
                    f'Use a path within the {resource_type}/ directory',
                    f'Or use just the {resource_type[:-1]} name without path separators'
                ]
            )

        # Extract the resource name (first part of the relative path)
        if resource_type == 'environments':
            # For environments, handle .yml/.yaml extensions
            name_with_ext = relative_to_resource.parts[0] if relative_to_resource.parts else relative_path
            # Remove .yml/.yaml extension if present
            name = Path(name_with_ext).stem
        else:
            # For experiments and testfunctions, use directory name
            name = relative_to_resource.parts[0] if relative_to_resource.parts else relative_path

        return name

    except Exception as e:
        if isinstance(e, InvalidPathError):
            raise
        raise InvalidPathError(
            log,
            f'Failed to resolve path "{relative_path}": {str(e)}',
            possible_solutions=[
                'Check that the path is valid and exists',
                f'Ensure the path points to a {resource_type[:-1]} within the {resource_type}/ directory'
            ]
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