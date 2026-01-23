"""
WebSocket connection manager for real-time updates.
"""

import asyncio
import logging
from typing import Any
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections for real-time session updates.

    Connections are tracked per session ID. Supports broadcasting
    events to all clients connected to a specific session.
    """

    def __init__(self):
        # session_id -> list of WebSocket connections
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """
        Accept and register a WebSocket connection.

        Args:
            websocket: WebSocket connection
            session_id: Session ID to associate with connection
        """
        await websocket.accept()
        async with self._lock:
            self._connections[session_id].append(websocket)
        logger.info(f"CLAUDE: WebSocket connected for session {session_id}")

    async def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """
        Unregister a WebSocket connection.

        Args:
            websocket: WebSocket connection
            session_id: Session ID associated with connection
        """
        async with self._lock:
            if session_id in self._connections:
                self._connections[session_id].remove(websocket)
                if not self._connections[session_id]:
                    del self._connections[session_id]
        logger.info(f"CLAUDE: WebSocket disconnected for session {session_id}")

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        """
        Broadcast a message to all clients connected to a session.

        Args:
            session_id: Session ID to broadcast to
            message: Message dict (will be JSON-serialized)
        """
        async with self._lock:
            connections = self._connections.get(session_id, []).copy()

        if not connections:
            logger.debug(f"CLAUDE: No WebSocket connections for session {session_id}")
            return

        # Send to all connections
        dead_connections = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except RuntimeError as e:
                logger.warning(
                    f"CLAUDE: Failed to send to WebSocket for session {session_id}: {e}"
                )
                dead_connections.append(websocket)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                for websocket in dead_connections:
                    if (
                        session_id in self._connections
                        and websocket in self._connections[session_id]
                    ):
                        self._connections[session_id].remove(websocket)
                if session_id in self._connections and not self._connections[session_id]:
                    del self._connections[session_id]

    def get_connection_count(self, session_id: str) -> int:
        """
        Get number of active connections for a session.

        Args:
            session_id: Session ID

        Returns:
            Number of active connections
        """
        return len(self._connections.get(session_id, []))

    async def send_session_state(
        self, session_id: str, state: dict[str, Any]
    ) -> None:
        """Send session state update."""
        await self.broadcast(
            session_id, {"type": "session_state", "session_id": session_id, "data": state}
        )

    async def send_action_start(
        self, session_id: str, action_type: str, description: str
    ) -> None:
        """Send action start event."""
        await self.broadcast(
            session_id,
            {
                "type": "action_start",
                "session_id": session_id,
                "data": {"action_type": action_type, "description": description},
            },
        )

    async def send_action_complete(
        self, session_id: str, action_type: str, success: bool, result: dict[str, Any]
    ) -> None:
        """Send action complete event."""
        await self.broadcast(
            session_id,
            {
                "type": "action_complete",
                "session_id": session_id,
                "data": {
                    "action_type": action_type,
                    "success": success,
                    "result": result,
                },
            },
        )

    async def send_vm_status(
        self, session_id: str, status: str, websocket_connected: bool
    ) -> None:
        """Send VM status update."""
        await self.broadcast(
            session_id,
            {
                "type": "vm_status",
                "session_id": session_id,
                "data": {"status": status, "websocket_connected": websocket_connected},
            },
        )

    async def send_checkpoint_created(
        self, session_id: str, checkpoint_name: str
    ) -> None:
        """Send checkpoint created event."""
        await self.broadcast(
            session_id,
            {
                "type": "checkpoint_created",
                "session_id": session_id,
                "data": {"checkpoint_name": checkpoint_name},
            },
        )


# Global WebSocket manager instance
ws_manager = WebSocketManager()
