"""
UI Components for Interactive Development Interface.

This module provides reusable UI components for building the
interactive development interface using NiceGUI.
"""

import json
from typing import Dict, Any, Optional, Callable
from nicegui import ui


class CommandParameterForm:
    """Form for editing command parameters based on command type."""
    
    def __init__(self, container, on_change: Optional[Callable] = None):
        self.container = container
        self.on_change = on_change
        self.current_inputs = {}
        
    def clear(self):
        """Clear all current inputs."""
        self.container.clear()
        self.current_inputs = {}
    
    def create_click_form(self):
        """Create form for click action parameters."""
        self.clear()
        with self.container:
            ui.label("Click Action Parameters").classes("text-subtitle1 q-mb-sm")
            
            # Target selection
            target_type = ui.select(
                ["position", "image", "text"],
                label="Target Type",
                value="position"
            ).classes("w-48")
            
            target_container = ui.column()
            
            def update_target_form():
                target_container.clear()
                with target_container:
                    if target_type.value == "position":
                        x_input = ui.number("X coordinate", value=100, min=0)
                        y_input = ui.number("Y coordinate", value=100, min=0)
                        self.current_inputs.update({"x": x_input, "y": y_input})
                    elif target_type.value == "image":
                        image_input = ui.input("Image filename (in img/ directory)")
                        strategy_select = ui.select(
                            ["first", "best_confidence", "largest", "smallest"],
                            label="Selection Strategy",
                            value="first"
                        )
                        self.current_inputs.update({
                            "image": image_input,
                            "strategy": strategy_select
                        })
                    elif target_type.value == "text":
                        text_input = ui.input("Text to find")
                        strategy_select = ui.select(
                            ["first", "best_confidence", "closest_to"],
                            label="Selection Strategy",
                            value="first"
                        )
                        self.current_inputs.update({
                            "text": text_input,
                            "strategy": strategy_select
                        })
            
            target_type.on('update:model-value', lambda: update_target_form())
            self.current_inputs["target_type"] = target_type
            
            # Description
            desc_input = ui.input("Description (optional)").classes("w-full")
            self.current_inputs["description"] = desc_input
            
            update_target_form()
    
    def create_keyboard_form(self):
        """Create form for keyboard action parameters."""
        self.clear()
        with self.container:
            ui.label("Keyboard Action Parameters").classes("text-subtitle1 q-mb-sm")
            
            # Input type selection
            input_type = ui.select(
                ["keys", "combination"],
                label="Input Type",
                value="keys"
            ).classes("w-48")
            
            input_container = ui.column()
            
            def update_input_form():
                input_container.clear()
                with input_container:
                    if input_type.value == "keys":
                        keys_input = ui.input("Text to type").classes("w-full")
                        self.current_inputs["keys"] = keys_input
                    elif input_type.value == "combination":
                        combo_input = ui.input(
                            "Key combination (comma-separated)",
                            placeholder="ctrl,c"
                        ).classes("w-full")
                        self.current_inputs["combination"] = combo_input
            
            input_type.on('update:model-value', lambda: update_input_form())
            self.current_inputs["input_type"] = input_type
            
            # Description
            desc_input = ui.input("Description (optional)").classes("w-full")
            self.current_inputs["description"] = desc_input
            
            update_input_form()
    
    def create_idle_form(self):
        """Create form for idle action parameters."""
        self.clear()
        with self.container:
            ui.label("Idle Action Parameters").classes("text-subtitle1 q-mb-sm")
            
            duration_input = ui.number("Duration (seconds)", value=1.0, min=0.1, step=0.1)
            desc_input = ui.input("Description (optional)").classes("w-full")
            
            self.current_inputs = {
                "duration": duration_input,
                "description": desc_input
            }
    
    def create_screenshot_form(self):
        """Create form for screenshot action parameters."""
        self.clear()
        with self.container:
            ui.label("Screenshot Action Parameters").classes("text-subtitle1 q-mb-sm")
            
            full_screen = ui.checkbox("Full screen screenshot", value=True)
            
            region_container = ui.column()
            
            def update_region_form():
                region_container.clear()
                if not full_screen.value:
                    with region_container:
                        ui.label("Screenshot Region:")
                        with ui.row():
                            x_input = ui.number("X", value=0, min=0)
                            y_input = ui.number("Y", value=0, min=0)
                        with ui.row():
                            width_input = ui.number("Width", value=800, min=1)
                            height_input = ui.number("Height", value=600, min=1)
                        self.current_inputs.update({
                            "x": x_input,
                            "y": y_input,
                            "width": width_input,
                            "height": height_input
                        })
            
            full_screen.on('update:model-value', lambda: update_region_form())
            
            desc_input = ui.input("Description (optional)").classes("w-full")
            
            self.current_inputs = {
                "full_screen": full_screen,
                "description": desc_input
            }
            
            update_region_form()
    
    def create_command_form(self):
        """Create form for command action parameters."""
        self.clear()
        with self.container:
            ui.label("Command Action Parameters").classes("text-subtitle1 q-mb-sm")
            
            cmd_input = ui.input("Command").classes("w-full")
            cwd_input = ui.input("Working directory (optional)").classes("w-full")
            timeout_input = ui.number("Timeout (seconds)", value=30, min=1)
            shell_checkbox = ui.checkbox("Use shell", value=False)
            desc_input = ui.input("Description (optional)").classes("w-full")
            
            self.current_inputs = {
                "cmd": cmd_input,
                "cwd": cwd_input,
                "timeout": timeout_input,
                "shell": shell_checkbox,
                "description": desc_input
            }
    
    def create_test_form(self):
        """Create form for test action parameters."""
        self.clear()
        with self.container:
            ui.label("Test Action Parameters").classes("text-subtitle1 q-mb-sm")

            test_name_input = ui.input("Test name").classes("w-full")
            desc_input = ui.input("Description (optional)").classes("w-full")

            self.current_inputs = {
                "name": test_name_input,
                "description": desc_input
            }

    def create_pause_form(self):
        """Create form for pause action parameters."""
        self.clear()
        with self.container:
            ui.label("Pause Action Parameters").classes("text-subtitle1 q-mb-sm")

            name_input = ui.input("Action name (optional)").classes("w-full")
            message_input = ui.input("Pause message (optional)").classes("w-full")
            desc_input = ui.input("Description (optional)").classes("w-full")

            self.current_inputs = {
                "name": name_input,
                "message": message_input,
                "description": desc_input
            }
    
    def get_action_data(self, command_type: str) -> Dict[str, Any]:
        """Get action data from current form inputs."""
        if command_type == "click":
            target = {}
            if self.current_inputs["target_type"].value == "position":
                target["position"] = [
                    int(self.current_inputs["x"].value or 0),
                    int(self.current_inputs["y"].value or 0)
                ]
            elif self.current_inputs["target_type"].value == "image":
                target["image"] = self.current_inputs["image"].value
            elif self.current_inputs["target_type"].value == "text":
                target["text"] = self.current_inputs["text"].value
            
            return {
                "click": {
                    "target": target,
                    "description": self.current_inputs["description"].value or ""
                }
            }
        
        elif command_type == "keyboard":
            keyboard_data = {"description": self.current_inputs["description"].value or ""}
            if self.current_inputs["input_type"].value == "keys":
                keyboard_data["keys"] = self.current_inputs["keys"].value or ""
            else:
                combination_str = self.current_inputs["combination"].value or ""
                keyboard_data["combination"] = [k.strip() for k in combination_str.split(",") if k.strip()]
            
            return {"keyboard": keyboard_data}
        
        elif command_type == "idle":
            return {
                "idle": {
                    "duration": self.current_inputs["duration"].value or 1.0,
                    "description": self.current_inputs["description"].value or ""
                }
            }
        
        elif command_type == "screenshot":
            screenshot_data = {
                "description": self.current_inputs["description"].value or ""
            }
            if not self.current_inputs["full_screen"].value:
                screenshot_data.update({
                    "x": int(self.current_inputs["x"].value or 0),
                    "y": int(self.current_inputs["y"].value or 0),
                    "width": int(self.current_inputs["width"].value or 800),
                    "height": int(self.current_inputs["height"].value or 600)
                })
            
            return {"screenshot": screenshot_data}
        
        elif command_type == "command":
            command_data = {
                "cmd": self.current_inputs["cmd"].value or "",
                "description": self.current_inputs["description"].value or ""
            }
            if self.current_inputs["cwd"].value:
                command_data["cwd"] = self.current_inputs["cwd"].value
            if self.current_inputs["timeout"].value:
                command_data["timeout"] = self.current_inputs["timeout"].value
            if self.current_inputs["shell"].value:
                command_data["shell"] = True
            
            return {"command": command_data}
        
        elif command_type == "test":
            return {
                "test": {
                    "name": self.current_inputs["name"].value or "",
                    "description": self.current_inputs["description"].value or ""
                }
            }

        elif command_type == "pause":
            pause_data = {
                "description": self.current_inputs["description"].value or ""
            }
            if self.current_inputs["name"].value:
                pause_data["name"] = self.current_inputs["name"].value
            if self.current_inputs["message"].value:
                pause_data["message"] = self.current_inputs["message"].value

            return {"pause": pause_data}

        return {}


class TestResultCard:
    """Card component for displaying test results."""
    
    def __init__(self, container, action_data: Dict[str, Any], result: Dict[str, Any], timestamp: str):
        self.container = container
        self.action_data = action_data
        self.result = result
        self.timestamp = timestamp
        
    def render(self):
        """Render the result card."""
        with self.container:
            with ui.card().classes("w-full q-mb-sm"):
                with ui.card_section():
                    with ui.row().classes("w-full items-center"):
                        # Success/failure badge
                        if self.result.get("success", False):
                            ui.badge("SUCCESS", color="green")
                        else:
                            ui.badge("FAILED", color="red")
                        
                        ui.space()
                        ui.label(self.timestamp).classes("text-caption text-grey")
                    
                    # Action details
                    action_type = list(self.action_data.keys())[0] if self.action_data else "unknown"
                    ui.label(f"Action: {action_type}").classes("text-subtitle2 q-mt-sm")
                    
                    # Expandable details
                    with ui.expansion("Details", icon="info"):
                        # Action data
                        ui.label("Action Data:").classes("text-weight-bold")
                        ui.code(json.dumps(self.action_data, indent=2)).classes("text-xs")
                        
                        # Result data
                        ui.label("Result:").classes("text-weight-bold q-mt-md")
                        ui.code(json.dumps(self.result, indent=2)).classes("text-xs")


class ActionHistoryPanel:
    """Panel for displaying and managing action history."""
    
    def __init__(self, container):
        self.container = container
        self.action_history = []
    
    def add_action(self, action_data: Dict[str, Any], result: Dict[str, Any], timestamp: str):
        """Add an action to the history."""
        self.action_history.append({
            "action": action_data,
            "result": result,
            "timestamp": timestamp
        })
        self.refresh()
    
    def clear_history(self):
        """Clear all history."""
        self.action_history.clear()
        self.refresh()
    
    def get_successful_actions(self) -> list:
        """Get only successful actions for saving to playbook."""
        return [
            item["action"] for item in self.action_history
            if item["result"].get("success", False)
        ]
    
    def refresh(self):
        """Refresh the display."""
        self.container.clear()
        with self.container:
            if not self.action_history:
                ui.label("No actions tested yet").classes("text-grey q-pa-md")
                return
            
            for item in reversed(self.action_history):  # Show most recent first
                TestResultCard(
                    self.container,
                    item["action"],
                    item["result"],
                    item["timestamp"]
                ).render()