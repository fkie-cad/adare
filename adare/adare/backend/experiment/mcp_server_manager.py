"""
MCP GUI Server Management Module.

This module provides functionality to start, stop, and manage the MCP GUI server
subprocess for target detection in experiments.
"""

import asyncio
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class MCPServerManager:
    """
    Manager for the MCP GUI server subprocess.
    
    Handles starting, stopping, and health checking the MCP GUI server
    that provides image and text detection services for playbook execution.
    """
    
    def __init__(self, server_port: int = 13109, log_file: Optional[Path] = None):
        """
        Initialize MCP server manager.
        
        Args:
            server_port: Port for MCP server (default: 13109)
            log_file: Path to log file for MCP server output
        """
        self.server_port = server_port
        self.process: Optional[subprocess.Popen] = None
        self.server_url = f"http://localhost:{server_port}/mcp"
        self.log_file = log_file
    
    async def start(self, allow_existing: bool = True) -> bool:
        """
        Start the MCP GUI server as a non-blocking subprocess.
        
        Args:
            allow_existing: If True, attach to existing server on port.
                           If False, fail if port is already in use.

        Returns:
            True if server started successfully, False otherwise
        """
        # Check if port is already in use (server running from another session)
        if self._is_port_in_use(self.server_port):
            if allow_existing:
                log.info(f"MCP server already running on port {self.server_port}")
                return True
            else:
                log.error(f"Port {self.server_port} is already in use and allow_existing=False")
                return False

        if self.process and self.process.poll() is None:
            log.info("MCP server already running")
            return True
        
        try:
            log.info(f"Starting MCP GUI server on port {self.server_port}...")
            
            # Open log file if specified
            log_file_handle = None
            if self.log_file:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                log_file_handle = open(self.log_file, 'w')
                log_file_handle.write(f"=== MCP GUI Server Log Started at {datetime.now()} ===\n")
                log_file_handle.flush()
            
            # Start process with start_new_session=True to detach from parent
            # This ensures it survives when the CLI tool exits
            self.process = subprocess.Popen(
                ["adare-cv-server", "--port", str(self.server_port)],
                stdout=log_file_handle or subprocess.PIPE,
                stderr=subprocess.STDOUT if log_file_handle else subprocess.PIPE,
                text=True,
                start_new_session=True
            )
            
            # Wait briefly and check if process started successfully
            await asyncio.sleep(1)
            if self.process.poll() is not None:
                # Process already exited
                stdout, stderr = self.process.communicate() if self.process.stdout else ("", "")
                log.error(f"MCP server failed to start: {stderr}")
                self.process = None
                return False
            
            # Wait for server to be ready (brief delay)
            await asyncio.sleep(2)  # Give server time to start up
            log.info("MCP GUI server started successfully")
            return True
                
        except Exception as e:
            log.error(f"Failed to start MCP server: {e}")
            self.process = None
            return False
    
    async def stop(self, force_external: bool = False):
        """
        Stop the MCP GUI server subprocess gracefully.
        
        Args:
            force_external: If True, check for and kill process on port even if not child.
                           If False, only stop local child process.
        """
        try:
            # 1. Try to stop local child process
            if self.process and self.process.poll() is None:
                log.info("Stopping local MCP GUI server process...")
                try:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                    log.info("MCP GUI server stopped gracefully")
                except subprocess.TimeoutExpired:
                    log.warning("MCP server didn't respond to SIGTERM, forcing kill...")
                    self.process.kill()
                    self.process.wait()
                self.process = None
                return

            # 2. If no local process, check if server is running on port and kill it
            # Only done if force_external is True (e.g. during final cleanup)
            if force_external and self._is_port_in_use(self.server_port):
                log.info(f"Stopping external MCP GUI server on port {self.server_port}...")
                if self._kill_process_on_port(self.server_port):
                    log.info("External MCP GUI server stopped")
                else:
                    log.warning("Failed to stop external MCP GUI server")
            
        except Exception as e:
            log.error(f"Error stopping MCP server: {e}")
    
    def is_running(self) -> bool:
        """
        Check if MCP server process is running (local or external).
        
        Returns:
            True if process is running, False otherwise
        """
        # Check local process
        if self.process and self.process.poll() is None:
            return True
            
        # Check port usage
        return self._is_port_in_use(self.server_port)

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is in use."""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                # Set timeout to avoid hanging
                s.settimeout(1.0)
                return s.connect_ex(('localhost', port)) == 0
        except:
            return False
    