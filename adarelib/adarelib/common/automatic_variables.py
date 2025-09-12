"""
Automatic Variables for ADARE Playbooks

This module provides automatic system variables that are available in all playbooks
without needing to be explicitly defined. These variables resolve to platform-appropriate
values at runtime.
"""

import os
import platform
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from .variables import VariableRegistry, Variable, VariableType

log = logging.getLogger(__name__)


class AutomaticVariables:
    """
    Provides automatic system variables for ADARE playbooks.
    
    These variables are available in all playbooks and resolve to appropriate
    values based on the target system/VM configuration.
    """
    
    @classmethod
    def get_automatic_variables(cls, vm_os: Optional[str] = None, vm_user: Optional[str] = None) -> VariableRegistry:
        """
        Get automatic variables appropriate for the target system.
        
        Args:
            vm_os: Target VM OS ('windows', 'linux') - if None, detects current system
            vm_user: Target VM username - if None, uses current user or default
            
        Returns:
            VariableRegistry containing automatic variables
        """
        registry = VariableRegistry()
        
        # Determine target OS
        target_os = vm_os if vm_os else cls._detect_os()
        
        # Determine target user
        target_user = vm_user if vm_user else cls._get_default_user(target_os)
        
        # Add automatic variables
        cls._add_user_variables(registry, target_os, target_user)
        cls._add_system_variables(registry, target_os)
        
        log.debug(f"Created automatic variables for OS='{target_os}', user='{target_user}': {list(registry.variables.keys())}")
        
        return registry
    
    @classmethod
    def _detect_os(cls) -> str:
        """Detect current OS."""
        system = platform.system().lower()
        if system == 'windows':
            return 'windows'
        else:
            return 'linux'
    
    @classmethod
    def _get_default_user(cls, target_os: str) -> str:
        """Get default username for target OS."""
        current_user = os.getenv('USER') or os.getenv('USERNAME')
        
        # Common VM usernames by OS
        defaults = {
            'windows': 'Admin',
            'linux': 'adare'
        }
        
        # Use current user if available, otherwise use OS default
        return current_user or defaults.get(target_os, 'user')
    
    @classmethod 
    def _add_user_variables(cls, registry: VariableRegistry, target_os: str, username: str):
        """Add user-related automatic variables."""
        
        # adare_user_home - main requested variable
        home_path = cls._get_user_home_path(target_os, username)
        registry.add('adare_user_home', Variable(
            value=home_path,
            type=VariableType.PATH,
            description=f"Home directory for user '{username}' on {target_os}"
        ))
        
        # adare_username - the resolved username
        registry.add('adare_username', Variable(
            value=username,
            type=VariableType.STRING,
            description=f"Username on target system"
        ))
        
        # Additional user-specific paths
        if target_os == 'windows':
            registry.add('adare_user_documents', Variable(
                value=f"C:/Users/{username}/Documents",
                type=VariableType.PATH,
                description="User's Documents folder on Windows"
            ))
            registry.add('adare_user_desktop', Variable(
                value=f"C:/Users/{username}/Desktop", 
                type=VariableType.PATH,
                description="User's Desktop folder on Windows"
            ))
            registry.add('adare_user_downloads', Variable(
                value=f"C:/Users/{username}/Downloads",
                type=VariableType.PATH,
                description="User's Downloads folder on Windows"
            ))
        else:  # linux
            registry.add('adare_user_documents', Variable(
                value=f"/home/{username}/Documents",
                type=VariableType.PATH,
                description="User's Documents folder on Linux"
            ))
            registry.add('adare_user_desktop', Variable(
                value=f"/home/{username}/Desktop",
                type=VariableType.PATH,
                description="User's Desktop folder on Linux"
            ))
            registry.add('adare_user_downloads', Variable(
                value=f"/home/{username}/Downloads",
                type=VariableType.PATH,
                description="User's Downloads folder on Linux"
            ))
    
    @classmethod
    def _add_system_variables(cls, registry: VariableRegistry, target_os: str):
        """Add system-related automatic variables."""
        
        # adare_os - operating system name
        registry.add('adare_os', Variable(
            value=target_os,
            type=VariableType.STRING,
            description="Target operating system (windows/linux)"
        ))
        
        # OS-specific system paths
        if target_os == 'windows':
            registry.add('adare_temp_dir', Variable(
                value="C:/Windows/Temp",
                type=VariableType.PATH,
                description="System temporary directory on Windows"
            ))
            registry.add('adare_system_drive', Variable(
                value="C:",
                type=VariableType.STRING,
                description="System drive on Windows"
            ))
        else:  # linux
            registry.add('adare_temp_dir', Variable(
                value="/tmp",
                type=VariableType.PATH,
                description="System temporary directory on Linux"
            ))
            registry.add('adare_root_dir', Variable(
                value="/",
                type=VariableType.PATH,
                description="Root directory on Linux"
            ))
    
    @classmethod
    def _get_user_home_path(cls, target_os: str, username: str) -> str:
        """Get the user home directory path for the target OS."""
        if target_os == 'windows':
            return f"C:/Users/{username}"
        else:  # linux
            return f"/home/{username}"
    
    @classmethod
    def merge_with_user_variables(cls, automatic_vars: VariableRegistry, user_vars: Optional[VariableRegistry]) -> VariableRegistry:
        """
        Merge automatic variables with user-defined variables.
        
        User variables take precedence over automatic ones.
        
        Args:
            automatic_vars: Automatic variables registry
            user_vars: User-defined variables registry (can be None)
            
        Returns:
            Merged VariableRegistry with user variables taking precedence
        """
        if not user_vars:
            return automatic_vars
        
        merged = VariableRegistry()
        
        # First add all automatic variables
        for name, var in automatic_vars.variables.items():
            merged.add(name, var)
        
        # Then add/override with user variables
        for name, var in user_vars.variables.items():
            if name in merged.variables:
                log.debug(f"User variable '{name}' overrides automatic variable")
            merged.add(name, var)
        
        return merged