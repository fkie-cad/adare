"""
Project detection and suggestion utilities.

This module provides functions for detecting project directories,
suggesting alternatives, and providing context-aware project guidance.
"""

from typing import List, Optional, Tuple
from pathlib import Path
import os

# configure logging
import logging
log = logging.getLogger(__name__)


def detect_potential_project_directories(search_path: Path = None, max_depth: int = 3) -> List[Path]:
    """
    Scan for potential project directories in the given path.
    
    Args:
        search_path: Path to search (defaults to current working directory)
        max_depth: Maximum directory depth to search
        
    Returns:
        List of paths that might be project directories
    """
    if search_path is None:
        search_path = Path.cwd()
    
    potential_projects = []
    
    try:
        # Look for ADARE project indicators
        for root, dirs, files in os.walk(search_path):
            current_path = Path(root)
            depth = len(current_path.parts) - len(search_path.parts)
            
            if depth > max_depth:
                dirs.clear()  # Don't recurse deeper
                continue
            
            # Check for ADARE project structure indicators
            adare_dir = current_path / 'adare'
            environments_dir = current_path / 'environments'
            experiments_dir = current_path / 'experiments'
            
            # Check if this looks like an ADARE project
            if (adare_dir.exists() and adare_dir.is_dir()) or \
               (environments_dir.exists() and environments_dir.is_dir()) or \
               (experiments_dir.exists() and experiments_dir.is_dir()):
                potential_projects.append(current_path)
                dirs.clear()  # Don't search subdirectories of found projects
        
        log.debug(f"Found {len(potential_projects)} potential project directories")
        return potential_projects
        
    except Exception as e:
        log.debug(f"Error scanning for project directories: {e}")
        return []


def suggest_project_creation_location(current_path: Path = None) -> Path:
    """
    Suggest a good location for creating a new project.
    
    Args:
        current_path: Current working directory
        
    Returns:
        Suggested path for new project
    """
    if current_path is None:
        current_path = Path.cwd()
    
    # If we're in a home directory or common project location, suggest current
    home_dir = Path.home()
    common_project_dirs = [
        home_dir / 'projects',
        home_dir / 'Documents',
        home_dir / 'workspace',
        home_dir / 'dev'
    ]
    
    # Check if current path is suitable for project creation
    if current_path == home_dir or any(current_path.is_relative_to(pdir) for pdir in common_project_dirs if pdir.exists()):
        return current_path
    
    # Otherwise suggest a standard location
    for pdir in common_project_dirs:
        if pdir.exists():
            return pdir
    
    return current_path


def check_project_database_status() -> Tuple[bool, int]:
    """
    Check if project database is accessible and get project count.
    
    Returns:
        Tuple of (database_accessible, project_count)
    """
    try:
        from adare.database.api.project import ProjectDbApi
        
        api = ProjectDbApi()
        projects = api.get_projects()
        return True, len(projects)
        
    except Exception as e:
        log.debug(f"Cannot access project database: {e}")
        return False, 0


def generate_no_project_error_message(
    current_path: Path = None,
    specified_project: str = None
) -> Tuple[str, List[str]]:
    """
    Generate enhanced error message for NoProjectFoundError.
    
    Args:
        current_path: Current working directory
        specified_project: Project name that was specified (if any)
        
    Returns:
        Tuple of (error_message, list_of_solutions)
    """
    if current_path is None:
        current_path = Path.cwd()
    
    # Check database status
    db_accessible, project_count = check_project_database_status()
    
    if specified_project:
        # User specified a project name that doesn't exist
        message = f"Project '{specified_project}' not found"
        
        if not db_accessible:
            solutions = [
                "Check database connection and try again",
                "Initialize ADARE with database setup",
                "Run 'adare manage reset' if database is corrupted"
            ]
        elif project_count == 0:
            solutions = [
                f"Create the project: 'adare project create {specified_project}'",
                "List available projects: 'adare project list'",
                "No projects exist yet - create your first project"
            ]
        else:
            solutions = [
                f"Create the project: 'adare project create {specified_project}'",
                "List available projects: 'adare project list'",
                "Check project name spelling",
                f"Use full path: 'adare -p /path/to/project <command>'"
            ]
    else:
        # No project specified and current directory is not a project
        message = f"No project directory found in current location: {current_path}"
        
        # Look for potential projects nearby
        potential_projects = detect_potential_project_directories(current_path.parent if current_path.parent != current_path else current_path)
        
        solutions = []
        
        if potential_projects:
            project_paths = [str(p) for p in potential_projects[:3]]
            solutions.extend([
                f"Navigate to a project directory: 'cd {project_paths[0]}'",
                f"Use -p flag: 'adare -p {project_paths[0]} <command>'",
                f"Found potential projects: {', '.join(project_paths)}"
            ])
        
        # Add standard solutions
        if project_count > 0:
            solutions.extend([
                "Navigate to an existing project directory",
                "List available projects: 'adare project list'",
                "Use -p flag to specify project: 'adare -p <project_path> <command>'"
            ])
        
        # Suggest creating a new project
        suggested_location = suggest_project_creation_location(current_path)
        solutions.extend([
            f"Create a new project: 'adare project create <name>'",
            f"Initialize project in current directory"
        ])
        
        if not db_accessible:
            solutions.insert(0, "Database not accessible - check ADARE installation")
    
    return message, solutions


def get_project_navigation_help(target_project: str = None) -> List[str]:
    """
    Get help for navigating to projects.
    
    Args:
        target_project: Specific project to help with
        
    Returns:
        List of helpful navigation commands
    """
    help_commands = []
    
    try:
        from adare.database.api.project import ProjectDbApi
        
        api = ProjectDbApi()
        projects = api.get_projects()
        
        if not projects:
            help_commands.extend([
                "No projects found in database",
                "Create your first project: 'adare project create <name>'",
                "Initialize project structure: 'adare project init'"
            ])
        else:
            if target_project:
                # Find specific project
                matching_projects = [p for p in projects if p.name == target_project]
                if matching_projects:
                    project = matching_projects[0]
                    help_commands.extend([
                        f"Navigate to project: 'cd {project.directory}'",
                        f"Use project flag: 'adare -p {project.directory} <command>'",
                        f"Project path: {project.directory}"
                    ])
                else:
                    help_commands.extend([
                        f"Project '{target_project}' not found",
                        "Available projects:"
                    ])
                    for project in projects[:5]:
                        help_commands.append(f"  • {project.name}: {project.directory}")
            else:
                help_commands.append("Available projects:")
                for project in projects[:5]:
                    help_commands.append(f"  • {project.name}: {project.directory}")
                
                if len(projects) > 5:
                    help_commands.append(f"  ... and {len(projects) - 5} more")
                
                help_commands.extend([
                    "",
                    "Navigate: 'cd <project_directory>'",
                    "Or use: 'adare -p <project_directory> <command>'"
                ])
        
    except Exception as e:
        log.debug(f"Error getting project navigation help: {e}")
        help_commands.extend([
            "Cannot access project database",
            "Check ADARE installation and database connection"
        ])
    
    return help_commands


def format_project_suggestions_for_cli(suggestions: List[str]) -> str:
    """
    Format project suggestions for CLI output.
    
    Args:
        suggestions: List of suggestion strings
        
    Returns:
        Formatted string for display
    """
    if not suggestions:
        return "No project suggestions available."
    
    return '\n'.join(f"  {i}. {suggestion}" for i, suggestion in enumerate(suggestions, 1))