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
    
    async def start(self) -> bool:
        """
        Start the MCP GUI server as a non-blocking subprocess.
        
        Returns:
            True if server started successfully, False otherwise
        """
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
            
            self.process = subprocess.Popen(
                ["adare-cv-server", "--port", str(self.server_port)],
                stdout=log_file_handle or subprocess.PIPE,
                stderr=subprocess.STDOUT if log_file_handle else subprocess.PIPE,
                text=True
            )
            
            # Wait briefly and check if process started successfully
            await asyncio.sleep(1)
            if self.process.poll() is not None:
                # Process already exited
                stdout, stderr = self.process.communicate()
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
    
    async def stop(self):
        """
        Stop the MCP GUI server subprocess gracefully.
        """
        if not self.process:
            return
        
        try:
            if self.process.poll() is None:
                log.info("Stopping MCP GUI server...")
                
                # Try graceful shutdown first
                self.process.terminate()
                
                # Wait up to 5 seconds for graceful shutdown
                try:
                    self.process.wait(timeout=5)
                    log.info("MCP GUI server stopped gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill if graceful shutdown fails
                    log.warning("MCP server didn't respond to SIGTERM, forcing kill...")
                    self.process.kill()
                    self.process.wait()
                    log.info("MCP GUI server force killed")
            
            self.process = None
            
        except Exception as e:
            log.error(f"Error stopping MCP server: {e}")
    
    def is_running(self) -> bool:
        """
        Check if MCP server process is running.
        
        Returns:
            True if process is running, False otherwise
        """
        return self.process is not None and self.process.poll() is None
    
