"""
Unified Experiment Orchestrator

This module consolidates ALL experiment lifecycle logic on the client side,
eliminating the need for complex experiment orchestration in the VM.

The orchestrator handles:
1. Complete experiment lifecycle (prepare → run → cleanup)
2. VM management and setup
3. Playbook parsing and execution
4. Test orchestration and result aggregation
5. Event handling and status reporting

The VM becomes a pure tool executor that responds to individual tool calls.
"""

import asyncio
import logging
import signal
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
import json

# Internal imports - experiment management
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
import adare.backend.experiment.database as experiment_database
import adare.backend.project.database as project_database
import adare.backend.environment.database as environment_database
from adare.backend.experiment.runctx import ExperimentRunCtx, ExperimentConfig
from adare.backend.experiment.unified_action_controller import UnifiedActionController, ActionResult

# Internal imports - VM management
from adare.virtualbox.api import VirtualBoxVM, VirtualBoxManager

# Internal imports - types and config
from adare.types.playbook import parse_config, Config
from adarelib.constants import StatusEnum
from adare.config.configdirectory import ADAREVM_DIR
from adare.exceptions import LoggedException, LoggedErrorException

# Internal imports - UI and events
from adare.backend.experiment.print import flowconsolemanager, ExperimentFlowConsole

log = logging.getLogger(__name__)


@dataclass
class ExperimentResult:
    """Result of a complete experiment execution."""
    success: bool
    message: str
    experiment_run_ulid: str
    action_results: List[ActionResult]
    test_results: List[Dict[str, Any]]
    execution_time: float
    vm_info: Optional[Dict[str, Any]] = None


class UnifiedExperimentOrchestrator:
    """
    Unified orchestrator that handles ALL experiment lifecycle on the client side.
    
    This class eliminates the need for experiment orchestration logic in the VM
    by centralizing all control flow, state management, and coordination here.
    """
    
    def __init__(self, 
                 project_path: Path,
                 experiment_name: str,
                 environment_name: str,
                 vm_server_url: str = "ws://localhost:13108"):
        """
        Initialize the experiment orchestrator.
        
        Args:
            project_path: Path to the project
            experiment_name: Name of the experiment
            environment_name: Name of the environment
            vm_server_url: WebSocket URL for VM communication
        """
        self.project_path = project_path
        self.experiment_name = experiment_name
        self.environment_name = environment_name
        self.vm_server_url = vm_server_url
        
        # Context and configuration
        self.config = ExperimentConfig(project_path, experiment_name, environment_name)
        self.context: Optional[ExperimentRunCtx] = None
        
        # Controllers
        self.action_controller: Optional[UnifiedActionController] = None
        self.vm_manager: Optional[VirtualBoxManager] = None
        self.flow_console: Optional[ExperimentFlowConsole] = None
        
        # State management
        self.stop_event = asyncio.Event()
        self.experiment_run_ulid: Optional[str] = None
        
        # Event handlers
        self.event_handlers: Dict[str, List[Callable]] = {}
        
        # Performance tracking
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def add_event_handler(self, event_type: str, handler: Callable):
        """Add an event handler."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
    
    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit an event to all registered handlers."""
        handlers = self.event_handlers.get(event_type, [])
        handlers.extend(self.event_handlers.get('*', []))
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event_type, data)
                else:
                    handler(event_type, data)
            except Exception as e:
                log.error(f"Error in event handler: {e}")
    
    async def execute_experiment(self, 
                                disable_printing: bool = False,
                                test_mode: bool = False) -> ExperimentResult:
        """
        Execute a complete experiment with full lifecycle management.
        
        This is the main orchestration method that coordinates all phases:
        1. Initialization and setup
        2. VM creation and configuration
        3. Experiment execution (playbook + tests)
        4. Cleanup and finalization
        
        Args:
            disable_printing: Whether to disable console output
            test_mode: Whether to run in test mode (no actual VM operations)
            
        Returns:
            ExperimentResult with complete execution summary
        """
        self.start_time = asyncio.get_event_loop().time()
        
        try:
            await self._emit_event('experiment_start', {
                'experiment_name': self.experiment_name,
                'environment_name': self.environment_name,
                'test_mode': test_mode
            })
            
            # Phase 1: Initialize experiment context
            log.info(f"Phase 1: Initializing experiment {self.experiment_name}")
            await self._initialize_experiment(test_mode)
            
            # Phase 2: Set up VM and environment
            if not test_mode:
                log.info("Phase 2: Setting up VM and environment")
                await self._setup_vm_environment()
            
            # Phase 3: Execute experiment actions
            log.info("Phase 3: Executing experiment actions")
            action_results = await self._execute_experiment_actions()
            
            # Phase 4: Execute tests
            log.info("Phase 4: Executing tests")
            test_results = await self._execute_tests()
            
            # Phase 5: Finalize and cleanup
            log.info("Phase 5: Finalizing experiment")
            await self._finalize_experiment()
            
            self.end_time = asyncio.get_event_loop().time()
            execution_time = self.end_time - self.start_time
            
            # Determine overall success
            actions_successful = all(r.success for r in action_results)
            tests_successful = all(t.get('success', False) for t in test_results)
            overall_success = actions_successful and tests_successful
            
            result = ExperimentResult(
                success=overall_success,
                message=f"Experiment completed: {len(action_results)} actions, {len(test_results)} tests",
                experiment_run_ulid=self.experiment_run_ulid,
                action_results=action_results,
                test_results=test_results,
                execution_time=execution_time,
                vm_info=self._get_vm_info() if not test_mode else None
            )
            
            await self._emit_event('experiment_complete', {
                'success': overall_success,
                'execution_time': execution_time,
                'action_count': len(action_results),
                'test_count': len(test_results)
            })
            
            return result
            
        except Exception as e:
            self.end_time = asyncio.get_event_loop().time()
            execution_time = (self.end_time - self.start_time) if self.start_time else 0.0
            
            await self._emit_event('experiment_error', {
                'error': str(e),
                'execution_time': execution_time
            })
            
            log.error(f"Experiment execution failed: {e}", exc_info=True)
            
            return ExperimentResult(
                success=False,
                message=f"Experiment failed: {str(e)}",
                experiment_run_ulid=self.experiment_run_ulid or "unknown",
                action_results=[],
                test_results=[],
                execution_time=execution_time
            )
        
        finally:
            # Always attempt cleanup
            await self._cleanup()
    
    async def _initialize_experiment(self, test_mode: bool = False):
        """Initialize experiment context and database entries."""
        # Create experiment run context
        self.context = ExperimentRunCtx(self.config)
        
        if test_mode:
            # For test mode, create a fake experiment run
            from adare.backend.experiment.commands import step_initialize
            step_initialize(self.context, fake=True)
        else:
            # Normal initialization
            from adare.backend.experiment.commands import step_initialize
            step_initialize(self.context)
        
        self.experiment_run_ulid = self.context.experiment_run_ulid
        
        # Set up directories and check integrity
        await self._run_blocking_step(self._setup_directories)
        await self._run_blocking_step(self._check_integrity)
        
        log.info(f"Experiment initialized with run ULID: {self.experiment_run_ulid}")
    
    async def _setup_vm_environment(self):
        """Set up VirtualBox VM and environment."""
        # Create and configure VM
        await self._run_async_step(self._create_vm)
        await self._run_async_step(self._start_vm)
        await self._run_async_step(self._wait_for_vm_ready)
        await self._run_async_step(self._mount_shared_directories)
        
        # Install and start VM services
        await self._run_async_step(self._install_adarevm)
        await self._run_async_step(self._start_websocket_server)
        
        # Connect to VM
        await self._run_async_step(self._connect_to_vm)
        
        log.info("VM environment setup complete")
    
    async def _execute_experiment_actions(self) -> List[ActionResult]:
        """Execute the main experiment actions using playbook or action.py."""
        if not self.action_controller:
            raise RuntimeError("Action controller not initialized")
        
        # Look for playbook file first
        playbook_path = self._find_playbook_file()
        
        if playbook_path and playbook_path.exists():
            log.info(f"Executing playbook: {playbook_path}")
            return await self._execute_playbook(playbook_path)
        else:
            # Fall back to action.py execution
            log.info("No playbook found, executing action.py")
            return await self._execute_action_py()
    
    async def _execute_playbook(self, playbook_path: Path) -> List[ActionResult]:
        """Execute a YAML playbook file."""
        try:
            # Parse playbook configuration
            config = parse_config(playbook_path)
            
            await self._emit_event('playbook_start', {
                'playbook_path': str(playbook_path),
                'action_count': len(config.actions)
            })
            
            # Execute the playbook using unified controller
            results = await self.action_controller.execute_config(config)
            
            await self._emit_event('playbook_complete', {
                'playbook_path': str(playbook_path),
                'results_count': len(results),
                'success_count': sum(1 for r in results if r.success)
            })
            
            return results
            
        except Exception as e:
            log.error(f"Error executing playbook {playbook_path}: {e}")
            await self._emit_event('playbook_error', {
                'playbook_path': str(playbook_path),
                'error': str(e)
            })
            return [ActionResult(success=False, message=f"Playbook execution failed: {e}")]
    
    async def _execute_action_py(self) -> List[ActionResult]:
        """Execute legacy action.py file via VM."""
        try:
            # Send experiment execution command to VM
            if not self.action_controller:
                raise RuntimeError("Action controller not initialized")
            
            await self._emit_event('action_py_start', {
                'experiment_name': self.experiment_name
            })
            
            # Use the VM's experiment execution capability
            result = await self.action_controller._execute_tool("execute_experiment", {
                "experiment_name": self.experiment_name
            })
            
            action_result = ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', 'Action.py executed'),
                data=result
            )
            
            await self._emit_event('action_py_complete', {
                'success': action_result.success,
                'message': action_result.message
            })
            
            return [action_result]
            
        except Exception as e:
            log.error(f"Error executing action.py: {e}")
            await self._emit_event('action_py_error', {'error': str(e)})
            return [ActionResult(success=False, message=f"Action.py execution failed: {e}")]
    
    async def _execute_tests(self) -> List[Dict[str, Any]]:
        """Execute tests defined in testset.yml."""
        try:
            if not self.action_controller:
                return []
            
            # Look for testset file
            testset_path = self._find_testset_file()
            if not testset_path or not testset_path.exists():
                log.info("No testset file found, skipping tests")
                return []
            
            await self._emit_event('tests_start', {
                'testset_path': str(testset_path)
            })
            
            # Upload testset to VM
            with open(testset_path, 'r') as f:
                testset_yaml = f.read()
            
            upload_result = await self.action_controller.upload_testset(testset_yaml)
            if not upload_result.success:
                log.error(f"Failed to upload testset: {upload_result.message}")
                return []
            
            # Execute all tests
            test_result = await self.action_controller.run_all_tests()
            
            if test_result.success:
                test_results = test_result.data.get('test_results', [])
                await self._emit_event('tests_complete', {
                    'test_count': len(test_results),
                    'success_count': sum(1 for t in test_results if t.get('success', False))
                })
                return test_results
            else:
                log.error(f"Test execution failed: {test_result.message}")
                return []
                
        except Exception as e:
            log.error(f"Error executing tests: {e}")
            await self._emit_event('tests_error', {'error': str(e)})
            return []
    
    async def _finalize_experiment(self):
        """Finalize experiment and update database."""
        if self.context and self.experiment_run_ulid:
            # Update experiment status in database
            experiment_database.update_experiment_run_status(
                self.experiment_run_ulid,
                StatusEnum.SUCCESS
            )
            
            log.info(f"Experiment {self.experiment_run_ulid} finalized successfully")
    
    def _find_playbook_file(self) -> Optional[Path]:
        """Find a playbook file in the experiment directory."""
        if not self.context:
            return None
        
        experiment_dir = Path(self.context.experiment_directory.path)
        
        possible_names = [
            "playbook.yaml",
            "playbook.yml",
            "actions.yaml",
            "actions.yml",
            f"{self.experiment_name.lower()}.yaml",
            f"{self.experiment_name.lower()}.yml"
        ]
        
        for name in possible_names:
            playbook_path = experiment_dir / name
            if playbook_path.exists():
                log.info(f"Found playbook file: {playbook_path}")
                return playbook_path
        
        log.debug(f"No playbook file found in {experiment_dir}")
        return None
    
    def _find_testset_file(self) -> Optional[Path]:
        """Find a testset file in the experiment directory."""
        if not self.context:
            return None
        
        experiment_dir = Path(self.context.experiment_directory.path)
        testset_path = experiment_dir / "testset.yml"
        
        if testset_path.exists():
            return testset_path
        
        return None
    
    def _get_vm_info(self) -> Optional[Dict[str, Any]]:
        """Get VM information for result reporting."""
        if not self.context or not hasattr(self.context, 'box'):
            return None
        
        try:
            return {
                "vm_name": self.context.box.name,
                "vm_status": self.context.box.status(),
                "vm_ip": getattr(self.context.box, 'ip', None)
            }
        except Exception:
            return None
    
    # VM management methods (delegate to existing implementation)
    
    async def _create_vm(self):
        """Create VirtualBox VM."""
        from adare.backend.experiment.commands import step_create_virtualbox_machine
        await asyncio.to_thread(step_create_virtualbox_machine, self.context)
    
    async def _start_vm(self):
        """Start the VirtualBox VM."""
        from adare.backend.experiment.commands import step_run_vm
        await step_run_vm(self.context)
    
    async def _wait_for_vm_ready(self):
        """Wait for VM to be ready."""
        from adare.backend.experiment.commands import step_wait_till_vm_is_ready
        await step_wait_till_vm_is_ready(self.context)
    
    async def _mount_shared_directories(self):
        """Mount shared directories in VM."""
        from adare.backend.experiment.commands import step_mount_shared_directories
        await step_mount_shared_directories(self.context)
    
    async def _install_adarevm(self):
        """Install adarevm in the VM."""
        from adare.backend.experiment.commands import step_install_and_run_websocket_server
        await step_install_and_run_websocket_server(self.context)
    
    async def _start_websocket_server(self):
        """Start WebSocket server in VM."""
        # This is now part of _install_adarevm
        pass
    
    async def _connect_to_vm(self):
        """Connect to VM WebSocket server."""
        # Initialize action controller and connect
        self.action_controller = UnifiedActionController(vm_server_url=self.vm_server_url)
        
        connected = await self.action_controller.connect()
        if not connected:
            raise RuntimeError("Failed to connect to VM WebSocket server")
        
        # Set up event forwarding
        self.action_controller.add_event_handler('*', self._forward_vm_event)
        
        log.info("Connected to VM WebSocket server")
    
    async def _forward_vm_event(self, event_type: str, data: Dict[str, Any]):
        """Forward VM events to experiment orchestrator handlers."""
        await self._emit_event(f"vm_{event_type}", data)
    
    # Setup and utility methods
    
    async def _setup_directories(self):
        """Set up experiment directories."""
        from adare.backend.experiment.commands import step_setup_directories, step_create_run_directory
        step_setup_directories(self.context)
        step_create_run_directory(self.context)
    
    async def _check_integrity(self):
        """Check experiment and project integrity."""
        from adare.backend.experiment.commands import (
            step_resolve_environment,
            step_check_integrity_experiment, 
            step_check_integrity_project
        )
        step_resolve_environment(self.context)
        step_check_integrity_experiment(self.context)
        step_check_integrity_project(self.context)
    
    # Helper methods for async execution
    
    async def _run_blocking_step(self, step_func):
        """Run a blocking step in a separate thread."""
        if not self.stop_event.is_set():
            log.debug(f"Running blocking step: {step_func.__name__}")
            await asyncio.to_thread(step_func)
            log.debug(f"Blocking step {step_func.__name__} completed")
    
    async def _run_async_step(self, step_func):
        """Run an async step with cancellation support."""
        if not self.stop_event.is_set():
            log.debug(f"Running async step: {step_func.__name__}")
            
            step_task = asyncio.create_task(step_func())
            stop_task = asyncio.create_task(self.stop_event.wait())
            
            try:
                done, pending = await asyncio.wait(
                    [step_task, stop_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # Check for exceptions
                for task in done:
                    if task.exception():
                        raise task.exception()
                        
                log.debug(f"Async step {step_func.__name__} completed")
                
            finally:
                # Ensure cleanup
                for task in [step_task, stop_task]:
                    if not task.done():
                        task.cancel()
    
    async def _cleanup(self):
        """Clean up resources."""
        try:
            if self.action_controller:
                await self.action_controller.disconnect()
            
            if self.context:
                from adare.backend.experiment.commands import (
                    step_shutdown_ws,
                    step_shutdown_virtualbox_vm,
                    step_cleanup_virtualbox_vm
                )
                try:
                    await step_shutdown_ws(self.context)
                    await step_shutdown_virtualbox_vm(self.context)
                    await step_cleanup_virtualbox_vm(self.context)
                except Exception as e:
                    log.error(f"Error during VM cleanup: {e}")
            
            if self.flow_console:
                self.flow_console.stop()
                
        except Exception as e:
            log.error(f"Error during cleanup: {e}")


# Convenience functions for direct usage

async def execute_experiment(project_path: Path,
                           experiment_name: str,
                           environment_name: str,
                           disable_printing: bool = False,
                           test_mode: bool = False) -> ExperimentResult:
    """
    Execute an experiment with unified orchestration.
    
    This replaces the complex experiment_run function with a cleaner approach
    that centralizes all orchestration on the client side.
    
    Args:
        project_path: Path to the project
        experiment_name: Name of the experiment
        environment_name: Name of the environment  
        disable_printing: Whether to disable console output
        test_mode: Whether to run in test mode
        
    Returns:
        ExperimentResult with execution summary
    """
    orchestrator = UnifiedExperimentOrchestrator(
        project_path=project_path,
        experiment_name=experiment_name,
        environment_name=environment_name
    )
    
    return await orchestrator.execute_experiment(
        disable_printing=disable_printing,
        test_mode=test_mode
    )


async def execute_playbook_standalone(playbook_path: Path,
                                    vm_server_url: str = "ws://localhost:13108") -> List[ActionResult]:
    """
    Execute a standalone playbook without full experiment setup.
    
    This is useful for testing playbooks or running automation scripts
    without the overhead of experiment lifecycle management.
    
    Args:
        playbook_path: Path to the YAML playbook file
        vm_server_url: VM server URL
        
    Returns:
        List of action results
    """
    from adare.backend.experiment.unified_action_controller import execute_playbook_file
    return await execute_playbook_file(playbook_path, vm_server_url)


# Example usage
if __name__ == "__main__":
    async def example():
        project_path = Path("/path/to/project")
        experiment_name = "test_experiment"
        environment_name = "win11_env"
        
        result = await execute_experiment(
            project_path=project_path,
            experiment_name=experiment_name,
            environment_name=environment_name,
            test_mode=True
        )
        
        print(f"Experiment completed: {result.success}")
        print(f"Message: {result.message}")
        print(f"Execution time: {result.execution_time:.2f}s")
        print(f"Actions: {len(result.action_results)}")
        print(f"Tests: {len(result.test_results)}")
    
    asyncio.run(example())