"""
WebSocket Bridge for Interactive Development.

This module provides a WebSocket abstraction layer that translates
WebSocket commands into playbook syntax for interactive testing.
"""

import json
import logging
from datetime import datetime
from typing import Any

import websockets

from adare.backend.experiment.playbook_controller import PlaybookController

log = logging.getLogger(__name__)


class WebSocketCommand:
    """Represents a WebSocket command that maps to playbook actions."""

    def __init__(self, command_type: str, parameters: dict[str, Any], description: str = ""):
        self.command_type = command_type
        self.parameters = parameters
        self.description = description
        self.timestamp = datetime.now()

    def to_playbook_action(self) -> dict[str, Any]:
        """Convert WebSocket command to playbook action format."""
        if self.command_type == "click":
            return {
                "click": {
                    "target": self.parameters.get("target", {}),
                    "description": self.description or f"Click at {self.parameters.get('target', {})}"
                }
            }
        if self.command_type == "type":
            return {
                "keyboard": {
                    "keys": self.parameters.get("text", ""),
                    "description": self.description or f"Type: {self.parameters.get('text', '')}"
                }
            }
        if self.command_type == "key_combination":
            return {
                "keyboard": {
                    "combination": self.parameters.get("keys", []),
                    "description": self.description or f"Key combo: {'+'.join(self.parameters.get('keys', []))}"
                }
            }
        if self.command_type == "wait":
            return {
                "idle": {
                    "duration": self.parameters.get("duration", 1.0),
                    "description": self.description or f"Wait {self.parameters.get('duration', 1.0)}s"
                }
            }
        if self.command_type == "screenshot":
            return {
                "screenshot": {
                    "description": self.description or "Take screenshot",
                    **{k: v for k, v in self.parameters.items() if k in ["x", "y", "width", "height"]}
                }
            }
        if self.command_type == "command":
            return {
                "command": {
                    "cmd": self.parameters.get("cmd", ""),
                    "description": self.description or f"Execute: {self.parameters.get('cmd', '')}",
                    **{k: v for k, v in self.parameters.items() if k in ["cwd", "env", "timeout", "shell"]}
                }
            }
        if self.command_type == "test":
            return {
                "test": {
                    "name": self.parameters.get("name", ""),
                    "description": self.description or f"Run test: {self.parameters.get('name', '')}"
                }
            }
        raise ValueError(f"Unknown command type: {self.command_type}")


class WebSocketBridge:
    """Bridge between WebSocket interface and playbook execution."""

    def __init__(self, playbook_controller: PlaybookController):
        self.playbook_controller = playbook_controller
        self.connected_clients: set[websockets.WebSocketServerProtocol] = set()
        self.command_history: List[WebSocketCommand] = []

    async def handle_client(self, websocket, path):
        """Handle new WebSocket client connection."""
        self.connected_clients.add(websocket)
        log.info(f"WebSocket client connected from {websocket.remote_address}")

        try:
            await websocket.send(json.dumps({
                "type": "connection_established",
                "message": "Connected to Adare Interactive Development",
                "timestamp": datetime.now().isoformat()
            }))

            async for message in websocket:
                await self.handle_message(websocket, message)

        except websockets.exceptions.ConnectionClosed:
            log.info(f"WebSocket client {websocket.remote_address} disconnected")
        except Exception as e:
            log.error(f"Error handling WebSocket client: {e}")
        finally:
            self.connected_clients.discard(websocket)

    async def handle_message(self, websocket, message: str):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            command_type = data.get("type")

            if command_type == "execute_command":
                await self.handle_execute_command(websocket, data)
            elif command_type == "get_history":
                await self.handle_get_history(websocket)
            elif command_type == "clear_history":
                await self.handle_clear_history(websocket)
            elif command_type == "save_to_playbook":
                await self.handle_save_to_playbook(websocket, data)
            else:
                await self.send_error(websocket, f"Unknown command type: {command_type}")

        except json.JSONDecodeError as e:
            await self.send_error(websocket, f"Invalid JSON: {e}")
        except Exception as e:
            log.error(f"Error handling WebSocket message: {e}")
            await self.send_error(websocket, f"Internal error: {e}")

    async def handle_execute_command(self, websocket, data: dict[str, Any]):
        """Execute a command and send result back to client."""
        try:
            command = WebSocketCommand(
                command_type=data.get("command_type", ""),
                parameters=data.get("parameters", {}),
                description=data.get("description", "")
            )

            # Convert to playbook action and execute
            action_data = command.to_playbook_action()

            # Parse and execute the action
            import cattrs

            from adare.types.playbook import _structure_action

            converter = cattrs.Converter()
            action = _structure_action(action_data, converter)

            # Execute through playbook controller
            result = await self.playbook_controller.execute_action(action)

            # Store in history if successful
            if result.success:
                self.command_history.append(command)

            # Send result back to client
            await websocket.send(json.dumps({
                "type": "command_result",
                "success": result.success,
                "message": result.message,
                "data": result.data,
                "timestamp": datetime.now().isoformat()
            }))

        except Exception as e:
            log.error(f"Error executing command: {e}")
            await self.send_error(websocket, f"Command execution failed: {e}")

    async def handle_get_history(self, websocket):
        """Send command history to client."""
        history_data = []
        for cmd in self.command_history:
            history_data.append({
                "command_type": cmd.command_type,
                "parameters": cmd.parameters,
                "description": cmd.description,
                "timestamp": cmd.timestamp.isoformat()
            })

        await websocket.send(json.dumps({
            "type": "history",
            "commands": history_data
        }))

    async def handle_clear_history(self, websocket):
        """Clear command history."""
        self.command_history.clear()
        await websocket.send(json.dumps({
            "type": "history_cleared",
            "message": "Command history cleared"
        }))

    async def handle_save_to_playbook(self, websocket, data: dict[str, Any]):
        """Save command history to playbook file."""
        try:
            if not self.command_history:
                await self.send_error(websocket, "No commands in history to save")
                return

            # Convert commands to playbook actions
            actions = [cmd.to_playbook_action() for cmd in self.command_history]

            playbook_data = {
                "actions": actions,
                "settings": {"idle": 0.1},
                "variables": data.get("variables", {})
            }

            # Get playbook file path from data or use default
            playbook_path = data.get("playbook_path")
            if not playbook_path:
                await self.send_error(websocket, "No playbook path provided")
                return

            # Write to playbook file
            from pathlib import Path

            import yaml

            with open(Path(playbook_path), 'w') as f:
                yaml.safe_dump(playbook_data, f, default_flow_style=False, indent=2)

            await websocket.send(json.dumps({
                "type": "playbook_saved",
                "message": f"Playbook saved to {playbook_path}",
                "actions_count": len(actions)
            }))

        except Exception as e:
            log.error(f"Error saving playbook: {e}")
            await self.send_error(websocket, f"Failed to save playbook: {e}")

    async def send_error(self, websocket, error_message: str):
        """Send error message to client."""
        await websocket.send(json.dumps({
            "type": "error",
            "message": error_message,
            "timestamp": datetime.now().isoformat()
        }))

    async def broadcast_status(self, status_data: dict[str, Any]):
        """Broadcast status update to all connected clients."""
        if not self.connected_clients:
            return

        message = json.dumps({
            "type": "status_update",
            **status_data,
            "timestamp": datetime.now().isoformat()
        })

        # Send to all connected clients
        disconnected_clients = set()
        for client in self.connected_clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected_clients.add(client)

        # Remove disconnected clients
        self.connected_clients.difference_update(disconnected_clients)


class WebSocketServer:
    """WebSocket server for interactive development."""

    def __init__(self, host: str = "localhost", port: int = 8765, playbook_controller: PlaybookController = None):
        self.host = host
        self.port = port
        self.bridge = WebSocketBridge(playbook_controller) if playbook_controller else None
        self.server = None

    async def start(self, playbook_controller: PlaybookController):
        """Start the WebSocket server."""
        if not self.bridge:
            self.bridge = WebSocketBridge(playbook_controller)

        self.server = await websockets.serve(
            self.bridge.handle_client,
            self.host,
            self.port
        )

        log.info(f"WebSocket server started on ws://{self.host}:{self.port}")
        return self.server

    async def stop(self):
        """Stop the WebSocket server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            log.info("WebSocket server stopped")
