"""
VM File Service for Host-Side Tests.

This service provides file access from VM to host, reusing the existing
pull infrastructure for consistency and code reuse.
"""

import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class VMFileService:
    """
    VM file access service for host-side tests.

    This service allows host-side tests to pull files from the VM
    for analysis on the host. It reuses the existing pull action
    infrastructure (execute_programmatic_pull) to maintain consistency
    with the playbook pull action.
    """

    def __init__(self, action_executor):
        """
        Initialize VM file service.

        Args:
            action_executor: ActionExecutor instance with pull capabilities
        """
        self.action_executor = action_executor

    async def pull_file(
        self,
        vm_path: str,
        description: str = "Host test file pull"
    ) -> Path:
        """
        Pull file or directory from VM to host artifacts directory.

        This method reuses the existing pull infrastructure via
        action_executor.execute_programmatic_pull(), ensuring consistent
        behavior with playbook pull actions.

        Args:
            vm_path: Path to file/directory in VM
            description: Description for logging

        Returns:
            Path to pulled file/directory on host (in artifacts dir)

        Raises:
            FileNotFoundError: If pull fails or file not found in VM
            RuntimeError: If pull operation encounters an error
        """
        try:
            log.debug(f"VM File Service: Pulling '{vm_path}' from VM")

            # Reuse existing pull infrastructure
            result = await self.action_executor.execute_programmatic_pull(
                src_path=vm_path,
                description=description
            )

            if result.success and result.data:
                dest_path = Path(result.data.get('destination'))
                log.debug(f"VM File Service: Successfully pulled '{vm_path}' to '{dest_path}'")
                return dest_path
            else:
                error_msg = f"Failed to pull {vm_path}: {result.message}"
                log.error(f"VM File Service: {error_msg}")
                raise FileNotFoundError(error_msg)

        except FileNotFoundError:
            # Re-raise FileNotFoundError as-is
            raise
        except Exception as e:
            log.error(f"VM File Service: Pull operation failed: {e}", exc_info=True)
            raise RuntimeError(f"VM file pull failed: {e}")

    async def read_file(
        self,
        vm_path: str,
        encoding: str = 'utf-8'
    ) -> str:
        """
        Pull file from VM and read its contents.

        Args:
            vm_path: Path to file in VM
            encoding: Text encoding (default: utf-8)

        Returns:
            File contents as string

        Raises:
            FileNotFoundError: If file doesn't exist in VM
            UnicodeDecodeError: If file encoding is invalid
            RuntimeError: If pull or read operation fails
        """
        try:
            log.debug(f"VM File Service: Reading file '{vm_path}' from VM")

            # Pull file to host
            local_path = await self.pull_file(
                vm_path=vm_path,
                description=f"Host test read: {vm_path}"
            )

            # Read file contents
            if not local_path.exists():
                raise FileNotFoundError(f"Pulled file not found at {local_path}")

            if not local_path.is_file():
                raise ValueError(f"Path is not a file: {local_path}")

            contents = local_path.read_text(encoding=encoding)
            log.debug(f"VM File Service: Read {len(contents)} characters from '{vm_path}'")
            return contents

        except (FileNotFoundError, ValueError, UnicodeDecodeError):
            # Re-raise these specific exceptions as-is
            raise
        except Exception as e:
            log.error(f"VM File Service: Read operation failed: {e}", exc_info=True)
            raise RuntimeError(f"VM file read failed: {e}")

    async def read_bytes(self, vm_path: str) -> bytes:
        """
        Pull file from VM and read its raw bytes.

        Args:
            vm_path: Path to file in VM

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: If file doesn't exist in VM
            RuntimeError: If pull or read operation fails
        """
        try:
            log.debug(f"VM File Service: Reading bytes from '{vm_path}' in VM")

            # Pull file to host
            local_path = await self.pull_file(
                vm_path=vm_path,
                description=f"Host test read bytes: {vm_path}"
            )

            # Read file bytes
            if not local_path.exists():
                raise FileNotFoundError(f"Pulled file not found at {local_path}")

            if not local_path.is_file():
                raise ValueError(f"Path is not a file: {local_path}")

            contents = local_path.read_bytes()
            log.debug(f"VM File Service: Read {len(contents)} bytes from '{vm_path}'")
            return contents

        except (FileNotFoundError, ValueError):
            # Re-raise these specific exceptions as-is
            raise
        except Exception as e:
            log.error(f"VM File Service: Read bytes operation failed: {e}", exc_info=True)
            raise RuntimeError(f"VM file read bytes failed: {e}")

    async def pull_directory(
        self,
        vm_path: str,
        description: str = "Host test directory pull"
    ) -> Path:
        """
        Pull directory from VM to host artifacts directory.

        This is an alias for pull_file() since the underlying pull
        infrastructure handles both files and directories recursively.

        Args:
            vm_path: Path to directory in VM
            description: Description for logging

        Returns:
            Path to pulled directory on host (in artifacts dir)

        Raises:
            FileNotFoundError: If pull fails or directory not found in VM
            RuntimeError: If pull operation encounters an error
        """
        return await self.pull_file(vm_path=vm_path, description=description)