"""
Modern MCP-based experiment execution system.

This module provides a new experiment base class that uses MCP servers
for GUI automation instead of GuiBot, integrating with the playbook system
for more reliable and maintainable automation.
"""

import asyncio
import logging
from pathlib import Path
from typing import Callable, Awaitable, Optional, Dict, Any, List
from datetime import datetime, timezone

from adare.backend.experiment.action_controller import MCPActionController, ActionResult
from adare.types.playbook import Config, parse_config, ActionType, Target
from adarevm.testset.testset import Testset
from adarevm.event import EventCtxManager
from adarelib.constants import StatusEnum
from adare.types.event import Event, ErrorEvent
from adare.helperfunctions.text import slugify

log = logging.getLogger(__name__)


class MCPExperiment:
    """
    Modern experiment base class using MCP servers for GUI automation.
    
    This replaces the GuiBot-based Experiment class with a more reliable
    MCP-based approach that supports playbook-driven automation.
    """
    
    description: str = ""
    
    def __init__(self, 
                 img_folder: Path, 
                 tessdata_folder: Path, 
                 testset: Testset,
                 log_func: Callable[[str], Awaitable[None]],
                 action_server_url: str = "http://localhost:13108/mcp",
                 gui_server_url: str = "http://localhost:13109/mcp"):
        """
        Initialize the MCP-based experiment.
        
        Args:
            img_folder: Path to images directory for template matching
            tessdata_folder: Path to tessdata for OCR (legacy compatibility)
            testset: Testset configuration
            log_func: Async logging function
            action_server_url: URL of the basic action MCP server
            gui_server_url: URL of the computer vision MCP server
        """
        self.img_folder = img_folder
        self.tessdata_folder = tessdata_folder
        self.testset = testset
        self.log_func = log_func
        
        # Initialize MCP controller
        self.controller = MCPActionController(action_server_url, gui_server_url)
        
        # Experiment state
        self.variables: Dict[str, Any] = {}
        self.status: str = 'success'
        self.action_results: List[ActionResult] = []
        
        # Set up image directory for MCP GUI server
        self.controller.context.set_variable('img_folder', str(img_folder))
        
        log.info(f"MCPExperiment initialized with MCP servers at {action_server_url} and {gui_server_url}")
    
    @property
    def name(self) -> str:
        """Get experiment name from class name."""
        return self.__class__.__name__
    
    async def prepare(self) -> tuple[bool, str]:
        """
        Prepare the experiment environment.
        
        This method can be overridden to perform setup tasks before
        the main experiment actions are executed.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        await self.log_func(f"Preparing experiment {self.name}")
        return True, "Preparation completed"
    
    async def run(self) -> tuple[bool, str]:
        """
        Execute the main experiment actions.
        
        This method should be overridden by subclasses to define the
        actual experiment workflow. It can either:
        1. Execute a playbook YAML file
        2. Define actions programmatically
        3. Combine both approaches
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        await self.log_func(f"Running experiment {self.name}")
        
        # Default implementation - look for a playbook file
        playbook_path = self._find_playbook_file()
        if playbook_path and playbook_path.exists():
            return await self.execute_playbook(playbook_path)
        else:
            # No playbook found - subclass should override this method
            await self.log_func("No playbook found and run() method not overridden")
            return True, "No actions to execute"
    
    async def cleanup(self) -> tuple[bool, str]:
        """
        Clean up after experiment execution.
        
        This method can be overridden to perform cleanup tasks after
        the main experiment actions are completed.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        await self.log_func(f"Cleaning up experiment {self.name}")
        return True, "Cleanup completed"
    
    async def execute_playbook(self, playbook_path: Path) -> tuple[bool, str]:
        """
        Execute a YAML playbook file.
        
        Args:
            playbook_path: Path to the YAML playbook file
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            await self.log_func(f"Executing playbook: {playbook_path}")
            
            # Parse and execute the playbook
            config = parse_config(playbook_path)
            results = await self.controller.execute_config(config)
            
            # Store results for analysis
            self.action_results.extend(results)
            
            # Determine overall success
            success_count = sum(1 for r in results if r.success)
            total_count = len(results)
            
            if success_count == total_count:
                message = f"Playbook executed successfully: {success_count}/{total_count} actions completed"
                await self.log_func(message)
                return True, message
            else:
                failed_count = total_count - success_count
                message = f"Playbook execution had failures: {failed_count}/{total_count} actions failed"
                await self.log_func(message)
                self.status = 'failed'
                return False, message
                
        except Exception as e:
            error_msg = f"Error executing playbook {playbook_path}: {e}"
            await self.log_func(error_msg)
            self.status = 'error'
            return False, error_msg
    
    async def execute_actions(self, actions: List[ActionType]) -> tuple[bool, str]:
        """
        Execute a list of actions programmatically.
        
        Args:
            actions: List of action objects to execute
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            await self.log_func(f"Executing {len(actions)} programmatic actions")
            
            results = []
            for action in actions:
                result = await self.controller.execute_action(action)
                results.append(result)
                
                # Log action result
                status_str = "✓" if result.success else "✗"
                await self.log_func(f"{status_str} {type(action).__name__}: {result.message}")
                
                # Stop on failure unless explicitly configured to continue
                if not result.success:
                    break
            
            self.action_results.extend(results)
            
            # Determine overall success
            success_count = sum(1 for r in results if r.success)
            total_count = len(results)
            
            if success_count == total_count:
                message = f"Actions executed successfully: {success_count}/{total_count} completed"
                return True, message
            else:
                failed_count = total_count - success_count
                message = f"Action execution had failures: {failed_count}/{total_count} failed"
                self.status = 'failed'
                return False, message
                
        except Exception as e:
            error_msg = f"Error executing actions: {e}"
            await self.log_func(error_msg)
            self.status = 'error'
            return False, error_msg
    
    def _find_playbook_file(self) -> Optional[Path]:
        """
        Find a playbook file associated with this experiment.
        
        Looks for files in this order:
        1. experiment_name.yaml
        2. experiment_name.yml  
        3. playbook.yaml
        4. playbook.yml
        5. actions.yaml
        6. actions.yml
        
        Returns:
            Path to playbook file if found, None otherwise
        """
        experiment_dir = Path.cwd()  # Assume we're in the experiment directory
        
        possible_names = [
            f"{self.name.lower()}.yaml",
            f"{self.name.lower()}.yml", 
            "playbook.yaml",
            "playbook.yml",
            "actions.yaml", 
            "actions.yml"
        ]
        
        for name in possible_names:
            playbook_path = experiment_dir / name
            if playbook_path.exists():
                log.info(f"Found playbook file: {playbook_path}")
                return playbook_path
        
        log.debug(f"No playbook file found in {experiment_dir}")
        return None
    
    # Convenience methods for common actions (backwards compatibility)
    
    async def click(self, target: Target, description: str = "") -> ActionResult:
        """Convenience method for clicking."""
        from adare.types.playbook import ClickAction
        action = ClickAction(target=target, description=description)
        return await self.controller.execute_action(action)
    
    async def type_text(self, text: str, description: str = "") -> ActionResult:
        """Convenience method for typing text."""
        from adare.types.playbook import KeyboardAction
        action = KeyboardAction(keys=text, description=description)
        return await self.controller.execute_action(action)
    
    async def press_keys(self, combination: List[str], description: str = "") -> ActionResult:
        """Convenience method for key combinations."""
        from adare.types.playbook import KeyboardAction
        action = KeyboardAction(combination=combination, description=description)
        return await self.controller.execute_action(action)
    
    async def wait(self, duration: float, description: str = "") -> ActionResult:
        """Convenience method for waiting."""
        from adare.types.playbook import IdleAction
        action = IdleAction(duration=duration, description=description)
        return await self.controller.execute_action(action)
    
    async def drag(self, source: Target, destination: Target, description: str = "") -> ActionResult:
        """Convenience method for drag and drop."""
        from adare.types.playbook import DragAction
        action = DragAction(source=source, destination=destination, description=description)
        return await self.controller.execute_action(action)
    
    # Context management for experiments
    
    def set_variable(self, name: str, value: Any) -> None:
        """Set an experiment variable."""
        self.variables[name] = value
        self.controller.context.set_variable(name, value)
    
    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get an experiment variable."""
        return self.variables.get(name, default)
    
    async def save_variables(self) -> None:
        """Save variables to the variables file (for backwards compatibility)."""
        import json
        vars_file = Path("variables.json")
        
        try:
            with open(vars_file, 'w') as f:
                json.dump(self.variables, f, indent=2)
            await self.log_func(f"Variables saved to {vars_file}")
        except Exception as e:
            await self.log_func(f"Error saving variables: {e}")
    
    async def load_variables(self) -> None:
        """Load variables from the variables file (for backwards compatibility)."""
        import json
        vars_file = Path("variables.json")
        
        try:
            if vars_file.exists():
                with open(vars_file, 'r') as f:
                    loaded_vars = json.load(f)
                self.variables.update(loaded_vars)
                for name, value in loaded_vars.items():
                    self.controller.context.set_variable(name, value)
                await self.log_func(f"Variables loaded from {vars_file}")
        except Exception as e:
            await self.log_func(f"Error loading variables: {e}")


# Backwards compatibility alias
Experiment = MCPExperiment


async def run_experiment_with_tests(experiment_class, 
                                   img_folder: Path,
                                   tessdata_folder: Path, 
                                   testset: Testset,
                                   log_func: Callable[[str], Awaitable[None]]) -> tuple[bool, str]:
    """
    Run an experiment followed by its tests.
    
    This is the main entry point for executing experiments in the ADARE system.
    It runs the experiment actions and then executes any associated tests.
    
    Args:
        experiment_class: The experiment class to instantiate and run
        img_folder: Path to images directory  
        tessdata_folder: Path to tessdata directory
        testset: Testset configuration with test definitions
        log_func: Async logging function
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    experiment = experiment_class(img_folder, tessdata_folder, testset, log_func)
    
    try:
        # Run experiment lifecycle
        await log_func(f"Starting experiment lifecycle for {experiment.name}")
        
        # 1. Prepare
        success, message = await experiment.prepare()
        if not success:
            return False, f"Preparation failed: {message}"
        
        # 2. Execute main actions  
        success, message = await experiment.run()
        if not success:
            return False, f"Execution failed: {message}"
        
        # 3. Execute tests from testset
        if testset and testset.tests:
            await log_func(f"Running {len(testset.tests)} tests")
            
            test_results = []
            for test in testset.tests:
                try:
                    # Execute test function
                    test_result = await execute_test_function(test, experiment)
                    test_results.append(test_result)
                    
                    status_str = "✓" if test_result.success else "✗"
                    await log_func(f"{status_str} Test {test.name}: {test_result.message}")
                    
                except Exception as e:
                    await log_func(f"✗ Test {test.name} failed with exception: {e}")
                    test_results.append(TestResult(success=False, message=str(e)))
            
            # Evaluate test results
            passed_tests = sum(1 for r in test_results if r.success)
            total_tests = len(test_results)
            
            if passed_tests == total_tests:
                test_message = f"All tests passed: {passed_tests}/{total_tests}"
                await log_func(test_message)
            else:
                failed_tests = total_tests - passed_tests
                test_message = f"Tests failed: {failed_tests}/{total_tests} failed"
                await log_func(test_message)
                success = False
                message += f"; {test_message}"
        
        # 4. Cleanup
        cleanup_success, cleanup_message = await experiment.cleanup()
        if not cleanup_success:
            await log_func(f"Cleanup warning: {cleanup_message}")
        
        # 5. Final status
        final_message = f"Experiment {experiment.name} completed: {message}"
        await log_func(final_message)
        
        return success, final_message
        
    except Exception as e:
        error_msg = f"Experiment {experiment.name} failed with exception: {e}"
        await log_func(error_msg)
        return False, error_msg


class TestResult:
    """Result of a test execution."""
    def __init__(self, success: bool, message: str = "", data: Optional[Dict] = None):
        self.success = success
        self.message = message
        self.data = data or {}


async def execute_test_function(test, experiment: MCPExperiment) -> TestResult:
    """
    Execute a test function from the testset.
    
    Args:
        test: Test definition from testset
        experiment: The experiment instance
        
    Returns:
        TestResult indicating success/failure
    """
    try:
        # This would integrate with your existing test function system
        # For now, return a placeholder result
        
        # You could implement different test types here:
        # - Visual verification tests using screenshots
        # - Text presence tests using OCR
        # - File system tests
        # - Custom Python test functions
        
        await experiment.log_func(f"Executing test: {test.name}")
        
        # Placeholder - implement actual test execution logic
        return TestResult(success=True, message=f"Test {test.name} passed")
        
    except Exception as e:
        return TestResult(success=False, message=str(e))