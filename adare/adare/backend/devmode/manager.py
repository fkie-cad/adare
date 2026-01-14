"""
Development mode session manager.

Singleton class for managing multiple concurrent dev mode sessions.
"""

from typing import Dict, Optional, List
from pathlib import Path
import logging
import ulid

from .session import DevModeSession, DevModeState

log = logging.getLogger(__name__)


class DevModeSessionManager:
    """
    Manages multiple dev mode sessions (singleton pattern).

    Allows multiple concurrent dev sessions for different experiments.
    Each session has its own VM instance, WebSocket connection, and state.

    Usage:
        manager = DevModeSessionManager()
        session_id = await manager.create_session(project_path, exp_name, env_name)
        session = manager.get_session(session_id)
        await manager.stop_session(session_id)
    """

    _instance: Optional['DevModeSessionManager'] = None

    def __new__(cls):
        """Singleton pattern: ensure only one instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the session manager (only once)."""
        if self._initialized:
            return

        self._sessions: Dict[str, DevModeSession] = {}
        self._initialized = True
        log.info("DevModeSessionManager initialized")

    async def create_session(
        self,
        project_path: Path,
        experiment_name: str,
        environment_name: str
    ) -> str:
        """
        Create and start a new dev mode session.

        Args:
            project_path: Path to the ADARE project
            experiment_name: Name of the experiment to develop
            environment_name: Name of the environment (VM) to use

        Returns:
            Session ID (ULID string)

        Raises:
            RuntimeError: If session fails to start
        """
        session_id = str(ulid.ULID())

        log.info(
            f"Creating dev mode session {session_id} for "
            f"experiment='{experiment_name}' environment='{environment_name}'"
        )

        session = DevModeSession(
            session_id=session_id,
            project_path=project_path,
            experiment_name=experiment_name,
            environment_name=environment_name
        )

        success = await session.start()
        if not success:
            raise RuntimeError(
                f"Failed to start dev mode session for {experiment_name}"
            )

        self._sessions[session_id] = session
        log.info(f"Dev mode session {session_id} created successfully")
        return session_id

    def get_session(self, session_id: str) -> Optional[DevModeSession]:
        """
        Get active session by ID.

        Args:
            session_id: Session ID to retrieve

        Returns:
            DevModeSession if found, None otherwise
        """
        return self._sessions.get(session_id)

    async def stop_session(self, session_id: str) -> bool:
        """
        Stop and remove a session.

        Args:
            session_id: Session ID to stop

        Returns:
            True if session was stopped, False if not found
        """
        session = self._sessions.get(session_id)
        if not session:
            log.warning(f"Session {session_id} not found")
            return False

        log.info(f"Stopping session {session_id}")
        await session.stop()
        del self._sessions[session_id]
        return True

    def list_sessions(self) -> List[DevModeState]:
        """
        List all active sessions.

        Returns:
            List of DevModeState objects representing active sessions
        """
        return [session.get_state() for session in self._sessions.values()]

    async def stop_all(self):
        """
        Stop all active sessions (cleanup on shutdown).

        This should be called when the application is shutting down to
        ensure all VMs are properly stopped and resources released.
        """
        log.info(f"Stopping all {len(self._sessions)} active sessions")
        session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            await self.stop_session(session_id)
        log.info("All sessions stopped")

    def get_session_count(self) -> int:
        """
        Get the number of active sessions.

        Returns:
            Number of active sessions
        """
        return len(self._sessions)
