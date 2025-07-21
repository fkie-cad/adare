from adarevm.action.mcp_experiment import MCPExperiment
from adare.types.playbook import Target, ClickAction, KeyboardAction, IdleAction
from pathlib import Path
from typing import Callable, Awaitable
from adarevm.testset.testset import Testset

import logging

log = logging.getLogger(__name__)


class {{ name }}(MCPExperiment):
    description = 'Example experiment using MCP-based GUI automation'

    def __init__(self, img_folder: Path, tessdata_folder: Path, testset: Testset,
                 log_func: Callable[[str], Awaitable[None]]):
        """
        Initialize the experiment with MCP servers for GUI automation.
        
        This uses the modern MCP-based approach instead of GuiBot for more
        reliable and maintainable GUI automation.
        """
        super().__init__(img_folder, tessdata_folder, testset, log_func)

    async def prepare(self) -> tuple[bool, str]:
        """
        Prepare the experiment environment.
        
        Use this method to:
        - Set up test files or directories
        - Configure the application under test
        - Initialize any required state
        """
        await self.log_func("Preparing experiment environment")
        
        # Example: Create test files, set variables, etc.
        # self.set_variable("test_file", "example.txt")
        
        return True, "Preparation completed successfully"

    async def run(self) -> tuple[bool, str]:
        """
        Execute the main experiment actions.
        
        You can either:
        1. Create a playbook.yaml file and let the system auto-execute it
        2. Define actions programmatically (as shown below)
        3. Combine both approaches
        """
        await self.log_func(f"Starting experiment {self.name}")

        # Option 1: Execute a playbook file (if it exists)
        # The base class will automatically look for:
        # - {{ name.lower() }}.yaml
        # - playbook.yaml  
        # - actions.yaml
        
        # If you want to use a specific playbook file:
        # playbook_path = Path("custom_playbook.yaml")
        # if playbook_path.exists():
        #     return await self.execute_playbook(playbook_path)

        # Option 2: Define actions programmatically
        actions = [
            # Click on an image (screenshot-based)
            ClickAction(
                target=Target(image="start_button.png"),
                description="Click the start button"
            ),
            
            # Wait for UI to load
            IdleAction(
                duration=2.0,
                description="Wait for application to load"
            ),
            
            # Click on text (OCR-based)
            ClickAction(
                target=Target(text="Settings"),
                description="Click Settings menu item"
            ),
            
            # Type some text
            KeyboardAction(
                keys="Test input text",
                description="Enter test data"
            ),
            
            # Use keyboard shortcut
            KeyboardAction(
                combination=["ctrl", "s"],
                description="Save with Ctrl+S"
            ),
            
            # Click at specific coordinates (if needed)
            ClickAction(
                target=Target(position=[100, 200]),
                description="Click at specific coordinates"
            ),
        ]
        
        # Execute the actions
        return await self.execute_actions(actions)

        # Option 3: Use convenience methods for simple actions
        # try:
        #     # Click using convenience method
        #     result = await self.click(Target(image="button.png"), "Click button")
        #     if not result.success:
        #         return False, f"Failed to click button: {result.message}"
        #     
        #     # Type text
        #     result = await self.type_text("Hello World", "Type greeting")
        #     if not result.success:
        #         return False, f"Failed to type text: {result.message}"
        #     
        #     # Wait
        #     await self.wait(1.0, "Wait for response")
        #     
        #     return True, "Actions completed successfully"
        # 
        # except Exception as e:
        #     return False, f"Error executing actions: {e}"

    async def cleanup(self) -> tuple[bool, str]:
        """
        Clean up after experiment execution.
        
        Use this method to:
        - Close applications
        - Remove temporary files
        - Reset system state
        """
        await self.log_func("Cleaning up experiment")
        
        # Example cleanup actions
        # - Close applications that were opened
        # - Delete temporary files
        # - Save any important data or screenshots
        
        return True, "Cleanup completed successfully"


# Example of how to create a playbook.yaml file instead of programmatic actions:
"""
Create a file named 'playbook.yaml' in your experiment directory with content like:

settings:
  idle: 1.0

actions:
  - click:
      target:
        image: "start_button.png"
      description: "Click the start button"
  
  - idle:
      duration: 2.0
      description: "Wait for application to load"
  
  - click:
      target:
        text: "Settings"
      description: "Click Settings menu"
  
  - keyboard:
      keys: "Test input"
      description: "Type test data"
  
  - keyboard:
      combination: ["ctrl", "s"]
      description: "Save with Ctrl+S"
  
  - block:
      description: "Handle save dialog if it appears"
      when:
        - exists:
            text: "Save As"
      actions:
        - click:
            target:
              text: "OK"
            description: "Confirm save"

Then remove the programmatic actions from the run() method above,
and the system will automatically execute the playbook.
"""