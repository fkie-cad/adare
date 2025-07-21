from adarevm.action.mcp_experiment import MCPExperiment
from pathlib import Path
from typing import Callable, Awaitable
from adarevm.testset.testset import Testset

import logging

log = logging.getLogger(__name__)


class {{ name }}(MCPExperiment):
    """
    Pure YAML experiment - all automation logic is in playbook.yaml
    
    This file serves as a minimal Python entry point. The actual GUI automation,
    test execution, and workflow logic is defined in playbook.yaml.
    
    For most experiments, you only need to edit playbook.yaml!
    """
    
    description = 'YAML-first experiment with automatic playbook execution'

    def __init__(self, img_folder: Path, tessdata_folder: Path, testset: Testset,
                 log_func: Callable[[str], Awaitable[None]]):
        super().__init__(img_folder, tessdata_folder, testset, log_func)

    async def prepare(self) -> tuple[bool, str]:
        """
        Optional: Add any Python setup logic here.
        Most experiments won't need this - use playbook.yaml instead.
        """
        await self.log_func("Starting YAML-based experiment")
        return True, "Ready to execute playbook.yaml"

    # No run() method - playbook.yaml handles all automation!
    # The framework automatically executes: playbook.yaml
    
    async def cleanup(self) -> tuple[bool, str]:
        """
        Optional: Add any Python cleanup logic here.
        Most experiments won't need this - use post_actions in playbook.yaml instead.
        """
        await self.log_func("YAML experiment completed")
        return True, "Experiment finished"


# Create your GUI automation in playbook.yaml:
"""
Example playbook.yaml content:

settings:
  idle: 1.0

actions:
  # Take initial screenshot
  - screenshot:
      description: "Take initial screenshot"
  
  # Click using image recognition
  - click:
      target:
        image: "button.png"
      description: "Click the main button"
  
  # Wait for response
  - idle:
      duration: 2.0
      description: "Wait for application response"
  
  # Type text
  - keyboard:
      keys: "Hello World"
      description: "Enter text"
  
  # Use keyboard shortcuts
  - keyboard:
      combination: ["ctrl", "s"]
      description: "Save with Ctrl+S"
  
  # Click using text recognition (OCR)
  - click:
      target:
        text: "Settings"
      description: "Click Settings menu"
  
  # Conditional actions
  - block:
      description: "Handle success dialog"
      when:
        - exists:
            text: "Success"
      actions:
        - click:
            target:
              text: "OK"
            description: "Dismiss success dialog"
  
  # Error handling
  - block:
      description: "Handle error dialog"
      when:
        - exists:
            text: "Error"
      actions:
        - screenshot:
            description: "Screenshot error for debugging"
        - click:
            target:
              text: "Cancel"
            description: "Cancel error dialog"

Variables and timestamps:
- Use {{ current_timestamp }} for current time
- Set variables with set_variable action
- Reference variables with {{ variable_name }}
"""