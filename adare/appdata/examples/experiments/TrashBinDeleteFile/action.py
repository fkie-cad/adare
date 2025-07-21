from adarevm.action.mcp_experiment import MCPExperiment
from pathlib import Path
from typing import Callable, Awaitable
from adarevm.testset.testset import Testset

import logging

log = logging.getLogger(__name__)


class TrashBinDeleteFile(MCPExperiment):
    description = 'Delete file and verify it appears in recycle bin using pure YAML automation'

    def __init__(self, img_folder: Path, tessdata_folder: Path, testset: Testset,
                 log_func: Callable[[str], Awaitable[None]]):
        """
        Simplified TrashBinDeleteFile experiment using pure YAML playbook.
        
        This experiment demonstrates:
        - Pure YAML-based GUI automation (no Python GUI code)
        - File creation and deletion operations
        - Forensic validation of recycle bin contents
        - Timestamp management for validation
        """
        super().__init__(img_folder, tessdata_folder, testset, log_func)

    async def prepare(self) -> tuple[bool, str]:
        """
        Prepare the experiment by creating the test file.
        
        Creates a test file at C:/Users/vagrant/Documents/testfile
        that will be deleted during the YAML automation.
        """
        await self.log_func("Preparing experiment: creating test file")
        
        try:
            # Create test file
            test_file_path = Path('C:/Users/vagrant/Documents/testfile')
            test_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(test_file_path, 'w', encoding='utf-8') as f:
                from datetime import datetime
                timestamp = datetime.now().isoformat()
                f.write('This is a test file for ADARE TrashBinDeleteFile experiment.\n')
                f.write('Created for testing file deletion and recycle bin validation.\n')
                f.write(f'Timestamp: {timestamp}\n')
            
            await self.log_func(f"Test file created successfully: {test_file_path}")
            return True, "Test file created successfully"
            
        except Exception as e:
            error_msg = f"Failed to create test file: {e}"
            await self.log_func(error_msg)
            return False, error_msg

    # No run() method needed - the base class will automatically find and execute playbook.yaml
    
    async def cleanup(self) -> tuple[bool, str]:
        """
        Clean up after experiment execution.
        
        This experiment doesn't require explicit cleanup as:
        - The test file has been deleted (which was the goal)
        - File Explorer will be closed by the VM reset
        - Forensic tools output is preserved for analysis
        """
        await self.log_func("Cleanup completed")
        return True, "Cleanup completed successfully"