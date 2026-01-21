"""
Development mode session manager.

Singleton class for managing multiple concurrent dev mode sessions.
"""

from typing import Dict, Optional, List
from pathlib import Path
import logging
import ulid

from .session import DevModeSession, DevModeState
from .vm_state_checker import is_vm_running
from .session_restorer import restore_context

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
        environment_name: str,
        gui_mode: Optional[str] = None,
        vm_memory: Optional[int] = None,
        vm_cpus: Optional[int] = None,
        debug_screenshots: bool = False,
        console_ulid: Optional[str] = None
    ) -> str:
        """
        Create and start a new dev mode session.

        Args:
            project_path: Path to the ADARE project
            experiment_name: Name of the experiment to develop
            environment_name: Name of the environment (VM) to use
            gui_mode: GUI execution mode override ('auto', 'agent', 'host')
            vm_memory: VM RAM in MB (None uses platform defaults)
            vm_cpus: VM CPU count (None uses default of 4)
            debug_screenshots: Save debug screenshots during execution
            console_ulid: Optional flow console ULID for event integration

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
            environment_name=environment_name,
            gui_mode=gui_mode,
            vm_memory=vm_memory,
            vm_cpus=vm_cpus,
            debug_screenshots=debug_screenshots,
            console_ulid=console_ulid
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

    async def shutdown_session(self, session_id: str) -> bool:
        """
        Shutdown a session (VM only, keep all resources).

        This is the new default for 'adare dev stop' - graceful shutdown
        without deleting any resources.

        Args:
            session_id: Session ID to shutdown

        Returns:
            True if session was shut down, False if not found
        """
        session = self._sessions.get(session_id)
        if not session:
            log.warning(f"Session {session_id} not found in memory")
            return False

        log.info(f"Shutting down session {session_id} (keeping resources)")
        await session.shutdown()
        del self._sessions[session_id]
        return True

    async def stop_and_remove_session(self, session_id: str) -> bool:
        """
        Stop a session and remove ALL resources (VM, snapshots, disks).

        This is used by 'adare dev stop --rm' and 'adare dev remove'.

        Args:
            session_id: Session ID to remove

        Returns:
            True if session was removed, False if not found
        """
        session = self._sessions.get(session_id)
        if not session:
            log.warning(f"Session {session_id} not found in memory")
            return False

        log.info(f"Stopping and removing session {session_id} with full cleanup")
        await session.stop_and_remove()
        del self._sessions[session_id]
        return True

    async def stop_session(self, session_id: str) -> bool:
        """
        DEPRECATED: Use shutdown_session() or stop_and_remove_session() instead.

        This method is kept for backward compatibility with existing code.
        Defaults to shutdown-only mode.
        """
        return await self.shutdown_session(session_id)

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

    async def restore_session(self, session_id: str) -> Optional[DevModeSession]:
        """
        Restore a session from database when not in memory but VM is running.

        This method implements lazy session restoration by:
        1. Querying database for session metadata
        2. Validating VM is actually running
        3. Reconstructing session context
        4. Attempting WebSocket reconnection
        5. Adding to in-memory session dict

        Args:
            session_id: Session ID to restore

        Returns:
            DevModeSession if restored successfully, None otherwise
        """
        log.info(f"Attempting to restore session {session_id}")

        # Import database API
        from adare.database.api.devmode import DevModeApi

        try:
            # 1. Query database for session metadata
            db_api = DevModeApi()
            db_session = db_api.get_session(session_id)

            if not db_session:
                log.warning(f"Session {session_id} not found in database")
                return None

            if db_session.status != 'running':
                log.warning(
                    f"Session {session_id} has status '{db_session.status}', "
                    f"cannot restore"
                )
                return None

            # 2. Get hypervisor type from environment
            from adare.backend.environment import database as environment_database

            try:
                environment_ulid = environment_database.resolve_environment_identifier(
                    db_session.environment_name
                )
                hypervisor_type = environment_database.get_environment_hypervisor(environment_ulid)
            except Exception as e:
                log.error(f"Failed to resolve environment: {e}")
                return None

            # 3. Validate VM is actually running via hypervisor
            if not is_vm_running(db_session.vm_name, hypervisor_type):
                log.warning(
                    f"Session {session_id}: VM '{db_session.vm_name}' is not running. "
                    f"Cannot restore session."
                )
                # Update database status to 'stopped' for cleanup
                db_api.update_session_status(session_id, 'stopped')
                return None

            log.info(f"VM '{db_session.vm_name}' is running, proceeding with restoration")

            # 4. Create session object with metadata from database
            session = DevModeSession(
                session_id=session_id,
                project_path=Path(db_session.project_path),
                experiment_name=db_session.experiment_name,
                environment_name=db_session.environment_name,
                gui_mode=None,  # Will be loaded from context
                vm_memory=None,  # Will use defaults
                vm_cpus=None,  # Will use defaults
                debug_screenshots=False,
                console_ulid=None
            )

            # 5. Restore context (directories, VM, playbook, etc.)
            success = await restore_context(session, db_session)

            if not success:
                log.error(f"Failed to restore context for session {session_id}")
                return None

            # 6. Attempt WebSocket reconnection (optional - some ops work without it)
            websocket_reconnected = False
            try:
                from adare.backend.experiment.websocket_client import AdareVMClient

                # Get WebSocket port from database or config
                # For now, try default port
                client = AdareVMClient(port=18765)  # TODO: Get actual port from session

                # Try to reconnect
                if hasattr(client, 'reconnect'):
                    websocket_reconnected = await client.reconnect(retries=2)
                else:
                    # Fallback to connect if reconnect not available yet
                    websocket_reconnected = await client.connect(timeout=5.0)

                if websocket_reconnected:
                    session.experiment_ctx.client = client
                    session.playbook_controller.websocket_client = client
                    log.info("WebSocket reconnected successfully")
                else:
                    log.warning(
                        "WebSocket reconnection failed. Some operations "
                        "(playbook execution) will not work."
                    )

            except Exception as e:
                log.warning(f"WebSocket reconnection failed: {e}")
                log.info(
                    "Session restored but WebSocket unavailable. "
                    "Stop/cleanup operations will still work."
                )

            # 7. Add to sessions dict
            self._sessions[session_id] = session

            log.info(
                f"Session {session_id} restored successfully "
                f"(WebSocket: {'connected' if websocket_reconnected else 'disconnected'})"
            )

            return session

        except Exception as e:
            log.error(f"Failed to restore session {session_id}: {e}", exc_info=True)
            return None

    def get_or_restore_session(self, session_id: str) -> Optional[DevModeSession]:
        """
        Get session from memory or restore from database if not present.

        This is the primary method that should be used by service layer.
        It provides transparent session restoration without client awareness.

        Args:
            session_id: Session ID to retrieve

        Returns:
            DevModeSession if found or restored, None otherwise
        """
        # Fast path: return from memory if present
        session = self._sessions.get(session_id)
        if session:
            return session

        # Slow path: attempt restoration from database
        log.info(f"Session {session_id} not in memory, attempting restoration")

        # Run async restoration - use asyncio.run() for simplicity
        import asyncio
        try:
            restored = asyncio.run(self.restore_session(session_id))
            return restored
        except Exception as e:
            log.error(f"Failed to restore session {session_id}: {e}", exc_info=True)
            return None
