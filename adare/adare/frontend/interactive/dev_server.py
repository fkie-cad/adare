"""
Interactive Development Server for Adare Experiments.

This module provides a NiceGUI-based web interface for interactive development
and testing of experiment playbooks. It allows developers to:

1. Start a VM for the experiment
2. Send individual playbook commands via WebSocket
3. Test and validate commands interactively
4. Build up a playbook incrementally
5. Save tested commands to the final playbook
"""

import asyncio
import json
import logging
import threading
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

# Suppress websockets deprecation warnings from NiceGUI until they update
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets.legacy")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets.server") 
warnings.filterwarnings("ignore", category=DeprecationWarning, module="uvicorn.protocols.websockets")

import websockets
from nicegui import ui, app
from nicegui.events import ValueChangeEventArguments

from .ui_components import CommandParameterForm, TestResultCard, ActionHistoryPanel

from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.backend.experiment.runctx import ExperimentRunCtx, ExperimentConfig
from adare.backend.experiment.mcp_server_manager import MCPServerManager
from adare.backend.project.directory import ProjectDirectory
from adare.types.playbook import *
from adare.backend.experiment.playbook_controller import PlaybookController
from adare.backend.experiment.websocket_client import AdareVMClient

log = logging.getLogger(__name__)


@dataclass
class DevSession:
    """Development session state."""
    project_directory: ProjectDirectory
    experiment_directory: ExperimentDirectory
    experiment_name: str
    environment: str
    vm_manager: VMLifecycleManager
    mcp_manager: MCPServerManager
    context: Optional[ExperimentRunCtx] = None
    vm_started: bool = False
    playbook_controller: Optional[PlaybookController] = None
    tested_actions: List[Dict[str, Any]] = field(default_factory=list)
    current_variables: Dict[str, Any] = field(default_factory=dict)
    

class InteractiveDevelopmentServer:
    """Interactive development server using NiceGUI."""
    
    def __init__(self, project_path: Path, experiment_name: str, environment: str, port: int = 8080):
        """Initialize the interactive development server."""
        self.port = port
        self.session = DevSession(
            project_directory=ProjectDirectory(project_path),
            experiment_directory=ExperimentDirectory(project_path, experiment_name),
            experiment_name=experiment_name,
            environment=environment,
            vm_manager=VMLifecycleManager(),
            mcp_manager=MCPServerManager()
        )
        
        self.ws_server = None
        self.ws_clients = set()
        
    async def start_vm_session(self) -> bool:
        """Start VM and prepare for interactive development."""
        try:
            # Create experiment directory for dev mode if it doesn't exist
            # Skip full experiment_load validation - dev mode only needs basic structure
            if not self.session.experiment_directory.exists():
                self.session.experiment_directory.create(empty=False)
                log.info(f"Created experiment directory for dev mode: {self.session.experiment_directory.path}")
            else:
                log.debug(f"Using existing experiment directory: {self.session.experiment_directory.path}")
            
            # Create experiment run context for development
            config = ExperimentConfig(
                project_path=self.session.project_directory.path,
                experiment_name=self.session.experiment_name,
                environment_name=self.session.environment,
                test_mode=True,  # Interactive development is like test mode
                preserve_snapshot=False,  # Don't preserve snapshots in dev mode
                disable_printing=False
            )
            
            # Create experiment run directory for this development session
            # Ensure experiment_name is never None (defensive check)
            experiment_name = self.session.experiment_name or "_dev_session"
            experiment_run_directory = ExperimentRunDirectory(
                self.session.project_directory,
                experiment_name
            )
            experiment_run_directory.create()
            
            # Create context
            self.session.context = ExperimentRunCtx(
                config=config,
                project_directory=self.session.project_directory,
                experiment_directory=self.session.experiment_directory,
                experiment_run_directory=experiment_run_directory,
                debug_screenshots=True
            )
            
            # Start MCP server for target detection
            if not await self.session.mcp_manager.start():
                log.error("Failed to start MCP server")
                return False
                
            # Create and prepare VM
            await self.session.vm_manager.create_and_prepare_vm(self.session.context)
            await self.session.vm_manager.start_vm(self.session.context)
            await self.session.vm_manager.wait_until_ready(self.session.context)
            await self.session.vm_manager.mount_shared_directories(self.session.context)
            
            # Create WebSocket client for VM communication
            self.session.context.client = AdareVMClient(
                host="localhost",
                port=self.session.context.config.websocket_port
            )
            await self.session.context.client.connect()
            
            # Initialize playbook controller for command execution
            self.session.playbook_controller = PlaybookController(
                websocket_client=self.session.context.client,
                experiment_dir=self.session.experiment_directory.path,
                project_dir=self.session.project_directory.path,
                mcp_gui_url=self.session.mcp_manager.server_url,
                debug_screenshots=True,
                screenshots_dir=self.session.context.experiment_run_directory.screenshots_directory
            )
            
            self.session.vm_started = True
            log.info("VM session started successfully")
            return True
            
        except Exception as e:
            log.error(f"Failed to start VM session: {e}")
            return False
    
    async def stop_vm_session(self):
        """Stop VM session and cleanup resources."""
        try:
            # Disconnect WebSocket client
            if self.session.context and self.session.context.client:
                await self.session.context.client.disconnect()
            
            if self.session.context:
                await self.session.vm_manager.stop_vm(self.session.context)
                await self.session.vm_manager.cleanup_vm(self.session.context)
                
            await self.session.mcp_manager.stop()
            self.session.vm_started = False
            self.session.playbook_controller = None
            log.info("VM session stopped")
            
        except Exception as e:
            log.error(f"Error stopping VM session: {e}")
    
    async def execute_action(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single action and return the result."""
        if not self.session.playbook_controller:
            return {"success": False, "error": "No active playbook controller"}
            
        try:
            # Parse the action using the existing parser
            import cattrs
            converter = cattrs.Converter()
            from adare.types.playbook import _structure_action
            
            action = _structure_action(action_data, converter)
            
            # Execute the action (assuming execute_action method exists on PlaybookController)
            # For now, we'll use a simple approach - check if the method exists
            if hasattr(self.session.playbook_controller, 'execute_single_action'):
                result = await self.session.playbook_controller.execute_single_action(action)
            else:
                # If no single action executor, create a mini-playbook
                from adare.types.playbook import Playbook, Settings
                mini_playbook = Playbook(actions=[action], settings=Settings())
                result = await self.session.playbook_controller.execute_playbook(mini_playbook)
                if result.action_results:
                    action_result = result.action_results[0]
                    return {
                        "success": action_result.success,
                        "message": action_result.message,
                        "data": action_result.data
                    }
                else:
                    return {"success": False, "error": "No action results returned"}
            
            return {
                "success": result.success,
                "message": result.message,
                "data": getattr(result, 'data', None)
            }
            
        except Exception as e:
            log.error(f"Failed to execute action: {e}")
            return {"success": False, "error": str(e)}
    
    def save_action_to_tested(self, action_data: Dict[str, Any], result: Dict[str, Any]):
        """Save a successfully tested action to the tested actions list."""
        if result.get("success", False):
            action_with_result = {
                "action": action_data,
                "result": result,
                "timestamp": datetime.now().isoformat()
            }
            self.session.tested_actions.append(action_with_result)
    
    def create_ui(self):
        """Create the NiceGUI user interface."""
        
        @ui.page('/')
        async def main_page():
            ui.page_title("Adare Interactive Experiment Development")
            
            with ui.header():
                ui.label("Interactive Experiment Development").classes("text-h4")
                ui.space()
                ui.label(f"Experiment: {self.session.experiment_name}")
                ui.label(f"Environment: {self.session.environment}")
            
            # VM Control Section
            with ui.card().classes("w-full"):
                ui.label("VM Control").classes("text-h5")
                
                vm_status = ui.label("VM Status: Stopped").classes("text-red")
                
                async def start_vm():
                    ui.notify("Starting VM session...")
                    vm_status.set_text("VM Status: Starting...")
                    vm_status.classes("text-yellow")
                    
                    success = await self.start_vm_session()
                    if success:
                        vm_status.set_text("VM Status: Running")
                        vm_status.classes("text-green")
                        ui.notify("VM session started successfully!", type="positive")
                        start_btn.set_enabled(False)
                        stop_btn.set_enabled(True)
                    else:
                        vm_status.set_text("VM Status: Failed to Start")
                        vm_status.classes("text-red")
                        ui.notify("Failed to start VM session", type="negative")
                
                async def stop_vm():
                    ui.notify("Stopping VM session...")
                    vm_status.set_text("VM Status: Stopping...")
                    vm_status.classes("text-yellow")
                    
                    await self.stop_vm_session()
                    vm_status.set_text("VM Status: Stopped")
                    vm_status.classes("text-red")
                    ui.notify("VM session stopped", type="info")
                    start_btn.set_enabled(True)
                    stop_btn.set_enabled(False)
                
                with ui.row():
                    start_btn = ui.button("Start VM", on_click=start_vm).props("color=primary")
                    stop_btn = ui.button("Stop VM", on_click=stop_vm).props("color=secondary").set_enabled(False)
            
            # Command Testing Section
            with ui.card().classes("w-full"):
                ui.label("Test Commands").classes("text-h5")
                
                # Command type selector
                command_type = ui.select(
                    ["click", "keyboard", "idle", "screenshot", "command", "test", "pause"],
                    label="Command Type",
                    value="click"
                ).classes("w-48")
                
                # Dynamic command parameters based on type
                params_container = ui.column()
                param_form = CommandParameterForm(params_container)
                
                def update_params():
                    if command_type.value == "click":
                        param_form.create_click_form()
                    elif command_type.value == "keyboard":
                        param_form.create_keyboard_form()
                    elif command_type.value == "idle":
                        param_form.create_idle_form()
                    elif command_type.value == "screenshot":
                        param_form.create_screenshot_form()
                    elif command_type.value == "command":
                        param_form.create_command_form()
                    elif command_type.value == "test":
                        param_form.create_test_form()
                    elif command_type.value == "pause":
                        param_form.create_pause_form()
                
                command_type.on('update:model-value', lambda: update_params())
                
                # Command execution result
                result_output = ui.textarea(label="Last Execution Result").classes("w-full").props("readonly")
                
                async def execute_command():
                    if not self.session.vm_started:
                        ui.notify("Please start VM first", type="warning")
                        return
                    
                    # Get parameters from form
                    action_data = param_form.get_action_data(command_type.value)
                    if not action_data:
                        ui.notify("Invalid command parameters", type="negative")
                        return
                    
                    ui.notify("Executing command...")
                    result = await self.execute_action(action_data)
                    
                    result_text = json.dumps(result, indent=2)
                    result_output.set_value(result_text)
                    
                    if result.get("success", False):
                        ui.notify("Command executed successfully!", type="positive")
                        # Add to history
                        action_history.add_action(action_data, result, datetime.now().strftime("%H:%M:%S"))
                    else:
                        ui.notify(f"Command failed: {result.get('error', 'Unknown error')}", type="negative")
                        # Still add to history for debugging
                        action_history.add_action(action_data, result, datetime.now().strftime("%H:%M:%S"))
                
                update_params()  # Initialize with default
                
                ui.button("Execute Command", on_click=execute_command).props("color=primary")
            
            # Action History Section
            with ui.card().classes("w-full"):
                ui.label("Action History").classes("text-h5")
                
                # Create action history panel
                history_container = ui.column().classes("w-full")
                action_history = ActionHistoryPanel(history_container)
                
                async def save_to_playbook():
                    """Save successful actions to the experiment playbook."""
                    successful_actions = action_history.get_successful_actions()
                    if not successful_actions:
                        ui.notify("No successful actions to save", type="warning")
                        return
                    
                    try:
                        playbook_data = {
                            "actions": successful_actions,
                            "settings": {"idle": 0.1},
                            "variables": self.session.current_variables
                        }
                        
                        # Write to playbook file
                        with open(self.session.experiment_directory.playbookfile, 'w') as f:
                            import yaml
                            yaml.safe_dump(playbook_data, f, default_flow_style=False, indent=2)
                        
                        ui.notify(f"Playbook saved with {len(successful_actions)} actions!", type="positive")
                        
                    except Exception as e:
                        log.error(f"Failed to save playbook: {e}")
                        ui.notify(f"Failed to save playbook: {e}", type="negative")
                
                def clear_history():
                    action_history.clear_history()
                    ui.notify("History cleared", type="info")
                
                with ui.row():
                    ui.button("Clear History", on_click=clear_history).props("color=secondary")
                    ui.button("Save Successful to Playbook", on_click=save_to_playbook).props("color=primary")
        
        # WebSocket endpoint for real-time communication
        @ui.page('/ws')
        async def websocket_endpoint():
            # This would handle WebSocket connections for real-time updates
            pass
    
    def run_server(self):
        """Run the interactive development server."""
        self.create_ui()
        
        @app.on_startup
        async def startup():
            log.info(f"Interactive development server starting on port {self.port}")
        
        @app.on_shutdown
        async def shutdown():
            log.info("Shutting down interactive development server")
            if self.session.vm_started:
                await self.stop_vm_session()
        
        # NiceGUI needs reload=False when called from imported module
        ui.run(
            host="127.0.0.1",
            port=self.port,
            title="Adare Interactive Development",
            dark=True,
            reload=False
        )


def _structure_action(obj, converter):
    """Helper function to structure action objects from dictionaries."""
    # This is imported from the main playbook module
    from adare.types.playbook import _structure_action as parse_action
    return parse_action(obj, converter)