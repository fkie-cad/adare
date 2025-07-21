"""
File operation error analysis and suggestions.

This module provides utilities for analyzing file operation failures
and generating helpful suggestions for resolution.
"""

from typing import List, Tuple, Optional
from pathlib import Path
import os
import stat

# configure logging
import logging
log = logging.getLogger(__name__)


def analyze_file_error(
    operation: str,
    file_path: Path,
    error: Exception
) -> Tuple[str, List[str]]:
    """
    Analyze file operation error and generate suggestions.
    
    Args:
        operation: The operation that failed (e.g., 'read', 'write', 'create')
        file_path: Path that caused the error
        error: The exception that occurred
        
    Returns:
        Tuple of (enhanced_message, list_of_solutions)
    """
    error_str = str(error)
    solutions = []
    
    # Analyze specific error types
    if "Permission denied" in error_str or "PermissionError" in str(type(error)):
        message = f"Permission denied while trying to {operation} {file_path}"
        solutions.extend(_get_permission_solutions(file_path, operation))
        
    elif "No such file or directory" in error_str or "FileNotFoundError" in str(type(error)):
        message = f"File not found while trying to {operation} {file_path}"
        solutions.extend(_get_file_not_found_solutions(file_path, operation))
        
    elif "Is a directory" in error_str or "IsADirectoryError" in str(type(error)):
        message = f"Cannot {operation} {file_path}: it is a directory"
        solutions.extend(_get_directory_error_solutions(file_path, operation))
        
    elif "File exists" in error_str or "FileExistsError" in str(type(error)):
        message = f"File already exists: {file_path}"
        solutions.extend(_get_file_exists_solutions(file_path, operation))
        
    elif "No space left on device" in error_str:
        message = f"No space left on device while trying to {operation} {file_path}"
        solutions.extend(_get_disk_space_solutions(file_path))
        
    else:
        # Generic file operation error
        message = f"Error during {operation} of {file_path}: {error}"
        solutions.extend(_get_generic_file_solutions(file_path, operation))
    
    return message, solutions


def _get_permission_solutions(file_path: Path, operation: str) -> List[str]:
    """Get solutions for permission errors."""
    solutions = []
    
    # Check if file/directory exists
    if file_path.exists():
        # Get current permissions
        try:
            file_stat = file_path.stat()
            current_perms = oct(file_stat.st_mode)[-3:]
            
            if operation in ['read', 'validate', 'load']:
                solutions.extend([
                    f"Add read permission: 'chmod +r {file_path}'",
                    f"Current permissions: {current_perms} - need read access",
                ])
            elif operation in ['write', 'create', 'save']:
                solutions.extend([
                    f"Add write permission: 'chmod +w {file_path}'",
                    f"Current permissions: {current_perms} - need write access",
                ])
            elif operation in ['execute', 'run']:
                solutions.extend([
                    f"Add execute permission: 'chmod +x {file_path}'",
                    f"Current permissions: {current_perms} - need execute access",
                ])
            
            # Check ownership
            try:
                owner_uid = file_stat.st_uid
                current_uid = os.getuid()
                if owner_uid != current_uid:
                    import pwd
                    owner_name = pwd.getpwuid(owner_uid).pw_name
                    solutions.append(f"File owned by {owner_name} - consider using sudo or changing ownership")
            except Exception:
                pass
                
        except Exception as e:
            log.debug(f"Error analyzing file permissions: {e}")
    
    # Check parent directory permissions
    parent = file_path.parent
    if parent.exists():
        try:
            parent_stat = parent.stat()
            parent_perms = oct(parent_stat.st_mode)[-3:]
            
            if operation in ['create', 'write']:
                solutions.extend([
                    f"Check parent directory permissions: {parent_perms}",
                    f"Add write permission to parent: 'chmod +w {parent}'",
                ])
        except Exception:
            pass
    
    # Generic permission solutions
    solutions.extend([
        "Run with elevated privileges: 'sudo <command>'",
        f"Check file ownership: 'ls -la {file_path}'",
        f"Fix ownership: 'sudo chown $USER {file_path}'",
    ])
    
    return solutions


def _get_file_not_found_solutions(file_path: Path, operation: str) -> List[str]:
    """Get solutions for file not found errors."""
    solutions = []
    
    # Check if parent directory exists
    parent = file_path.parent
    if not parent.exists():
        solutions.extend([
            f"Create parent directory: 'mkdir -p {parent}'",
            f"Parent directory {parent} does not exist",
        ])
    
    # Check for similar files in the directory
    if parent.exists():
        try:
            similar_files = []
            for item in parent.iterdir():
                if item.name.lower().startswith(file_path.stem.lower()[:3]):
                    similar_files.append(item.name)
            
            if similar_files:
                solutions.append(f"Similar files found: {', '.join(similar_files[:3])}")
                if len(similar_files) > 3:
                    solutions.append(f"... and {len(similar_files) - 3} more")
        except Exception:
            pass
    
    # Check common alternative locations
    common_locations = _get_common_file_locations(file_path)
    existing_alternatives = [loc for loc in common_locations if loc.exists()]
    
    if existing_alternatives:
        solutions.extend([
            f"File found in alternative location: {existing_alternatives[0]}",
            f"Use: 'ln -s {existing_alternatives[0]} {file_path}' to create link",
        ])
    
    # Operation-specific solutions
    if operation in ['read', 'load', 'validate']:
        solutions.extend([
            f"Verify file path spelling: {file_path}",
            f"Check if file was moved or renamed",
            "Use absolute path if using relative path",
        ])
    elif operation in ['write', 'create', 'save']:
        solutions.extend([
            f"Create the file first: 'touch {file_path}'",
            f"Ensure parent directory exists: 'mkdir -p {parent}'",
        ])
    
    solutions.append(f"Check current directory: 'pwd' (are you in the right place?)")
    
    return solutions


def _get_directory_error_solutions(file_path: Path, operation: str) -> List[str]:
    """Get solutions for directory operation errors."""
    solutions = []
    
    if operation in ['read', 'write']:
        # User tried to read/write a directory as a file
        solutions.extend([
            f"'{file_path}' is a directory, not a file",
            f"List directory contents: 'ls -la {file_path}'",
            f"Specify a file within the directory",
        ])
        
        # Check for common files in the directory
        if file_path.exists():
            try:
                common_files = ['config.yml', 'settings.yml', 'environment.yml', 'metadata.yml']
                existing_files = [f for f in common_files if (file_path / f).exists()]
                
                if existing_files:
                    solutions.append(f"Found files in directory: {', '.join(existing_files)}")
                    solutions.append(f"Try: 'cat {file_path / existing_files[0]}'")
            except Exception:
                pass
    
    return solutions


def _get_file_exists_solutions(file_path: Path, operation: str) -> List[str]:
    """Get solutions for file already exists errors."""
    solutions = []
    
    if operation in ['create', 'write']:
        solutions.extend([
            f"File already exists: {file_path}",
            f"Remove existing file: 'rm {file_path}'",
            f"Backup existing file: 'mv {file_path} {file_path}.backup'",
            f"Use different filename or add timestamp",
        ])
        
        # Check if it's a directory
        if file_path.is_dir():
            solutions.extend([
                f"'{file_path}' is a directory - use a different name",
                f"Or remove directory: 'rm -rf {file_path}'",
            ])
    
    return solutions


def _get_disk_space_solutions(file_path: Path) -> List[str]:
    """Get solutions for disk space errors."""
    solutions = []
    
    try:
        # Get disk usage info
        stat_result = os.statvfs(file_path.parent)
        free_space = stat_result.f_frsize * stat_result.f_bavail
        total_space = stat_result.f_frsize * stat_result.f_blocks
        
        free_gb = free_space / (1024**3)
        total_gb = total_space / (1024**3)
        
        solutions.extend([
            f"Free space: {free_gb:.1f} GB of {total_gb:.1f} GB",
            f"Clean up disk space: 'du -h {file_path.parent} | sort -hr | head -10'",
            "Remove temporary files or move files to another location",
            "Check for large log files or old backups",
        ])
    except Exception:
        solutions.extend([
            "Check disk space: 'df -h'",
            "Clean up temporary files",
            "Move files to another location with more space",
        ])
    
    return solutions


def _get_generic_file_solutions(file_path: Path, operation: str) -> List[str]:
    """Get generic solutions for file operation errors."""
    solutions = []
    
    # Basic troubleshooting
    solutions.extend([
        f"Check if file exists: 'ls -la {file_path}'",
        f"Check permissions: 'ls -la {file_path.parent}'",
        f"Verify you're in the correct directory: 'pwd'",
    ])
    
    # Operation-specific advice
    if operation in ['read', 'load']:
        solutions.extend([
            "Ensure file is not corrupted",
            "Try copying file from backup if available",
        ])
    elif operation in ['write', 'save']:
        solutions.extend([
            "Check if file is locked by another process",
            "Ensure sufficient disk space",
        ])
    
    return solutions


def _get_common_file_locations(file_path: Path) -> List[Path]:
    """Get list of common alternative locations for a file."""
    alternatives = []
    
    # Current directory
    alternatives.append(Path.cwd() / file_path.name)
    
    # Home directory
    alternatives.append(Path.home() / file_path.name)
    
    # Common config directories
    config_dirs = [
        Path.home() / '.config',
        Path.home() / '.adare',
        Path('/etc'),
        Path('/usr/local/etc'),
    ]
    
    for config_dir in config_dirs:
        if config_dir.exists():
            alternatives.append(config_dir / file_path.name)
    
    # Same directory with different extensions
    if file_path.suffix:
        stem = file_path.stem
        parent = file_path.parent
        common_extensions = ['.yml', '.yaml', '.json', '.txt', '.cfg', '.conf']
        
        for ext in common_extensions:
            if ext != file_path.suffix:
                alternatives.append(parent / f"{stem}{ext}")
    
    return alternatives


def format_file_error_message(
    operation: str,
    file_path: Path,
    error: Exception,
    include_debug_info: bool = False
) -> Tuple[str, List[str]]:
    """
    Format a comprehensive file error message.
    
    Args:
        operation: The operation that failed
        file_path: Path that caused the error
        error: The exception that occurred
        include_debug_info: Whether to include debug information
        
    Returns:
        Tuple of (formatted_message, solutions_list)
    """
    message, solutions = analyze_file_error(operation, file_path, error)
    
    if include_debug_info:
        solutions.extend([
            f"Original error: {type(error).__name__}: {error}",
            f"Operation: {operation}",
            f"Path: {file_path}",
        ])
    
    return message, solutions