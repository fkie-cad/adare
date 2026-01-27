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
from .session_restorer import restore_context, restore_infrastructure_context
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adare.types.stages import ConnectToVMStage

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
            f"environment='{environment_name}'"
        )

        session = DevModeSession(
            session_id=session_id,
            project_path=project_path,
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
                f"Failed to start dev mode session"
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

    async def restore_session(
        self,
        session_id: str,
        console_ulid: Optional[str] = None,
        connect_websocket: bool = True
    ) -> Optional[DevModeSession]:
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
            console_ulid: Optional console ULID for flow console routing
            connect_websocket: Whether to reconnect WebSocket (default: True)

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

            if db_session.status not in ['running', 'stopped']:
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
                console_ulid=console_ulid
            )

            # 5. Restore context (directories, VM, playbook, etc.)
            success = await restore_context(session, db_session)

            if not success:
                log.error(f"Failed to restore context for session {session_id}")
                return None

            # 5.5. Restore VM instance ID for cleanup
            try:
                from adare.database.api.experiment import ExperimentApi
                from adare.database.models.project_models import ExperimentRun

                with ExperimentApi(session.project_path) as api:
                    experiment_run = api._session.query(ExperimentRun).filter(
                        ExperimentRun.id == session.experiment_ctx.experiment_run_ulid
                    ).first()

                    if experiment_run and experiment_run.vm_instance_id:
                        session.vm_instance_id = experiment_run.vm_instance_id
                        log.info(f"Restored VM instance ID: {session.vm_instance_id}")
                    else:
                        log.warning("No VM instance ID found during restoration")
            except Exception as e:
                log.error(f"Failed to restore VM instance ID: {e}")

            # 6. Attempt WebSocket reconnection (optional - some ops work without it)
            websocket_reconnected = False
            if connect_websocket:
                try:
                    from adare.backend.experiment.websocket_client import AdareVMClient

                    # Verify VM is running before attempting reconnection
                    vm_state = None
                    try:
                        if session.experiment_ctx.hypervisor_type == 'qemu':
                            # QEMU: Check if process is running
                            if hasattr(session.experiment_ctx.vm, '_qemu_process') and session.experiment_ctx.vm._qemu_process:
                                vm_state = 'running' if session.experiment_ctx.vm._qemu_process.poll() is None else 'stopped'
                            else:
                                log.debug("QEMU process not available - cannot verify VM state")

                        elif session.experiment_ctx.hypervisor_type == 'virtualbox':
                            # VirtualBox: Use get_state() method
                            vm_state = session.experiment_ctx.vm.get_state()

                        if vm_state and vm_state not in ['running', 'Running', 'running (since']:
                            log.error(f"VM is not running (state: {vm_state}) - WebSocket reconnection will fail")
                            raise RuntimeError(f"VM is not running (state: {vm_state})")

                        if vm_state:
                            log.debug(f"VM state verified: {vm_state}")

                    except RuntimeError:
                        raise  # Re-raise VM not running error
                    except Exception as e:
                        log.debug(f"Could not verify VM status: {e} - proceeding with reconnection attempt")

                    # Query actual forwarded port from VM port forwarding rules
                    websocket_port = None
                    try:
                        # Both QEMU and VirtualBox VMs have list_port_forwarding_rules()
                        port_forwarding_rules = await session.experiment_ctx.vm.list_port_forwarding_rules(silent=True)

                        if 'adarevm' in port_forwarding_rules:
                            adarevm_rule = port_forwarding_rules['adarevm']
                            websocket_port = adarevm_rule.host_port
                            log.debug(
                                f"Found adarevm port forwarding: host:{adarevm_rule.host_port} -> "
                                f"guest:{adarevm_rule.guest_port}"
                            )
                        else:
                            log.error("No 'adarevm' port forwarding rule found in VM config")
                            raise RuntimeError("adarevm port forwarding rule not found")

                    except Exception as e:
                        log.error(f"Failed to query port forwarding rules: {e}")
                        # Try database fallback as last resort
                        if hasattr(session.experiment_ctx.config, 'websocket_port') and session.experiment_ctx.config.websocket_port:
                            websocket_port = session.experiment_ctx.config.websocket_port
                            log.warning(f"Using websocket_port from config as fallback: {websocket_port}")
                        else:
                            log.error("No websocket port available from VM config or database")
                            raise RuntimeError("Cannot determine WebSocket port for reconnection")

                    # Use console_ulid if available, otherwise fall back to session/context ulid
                    stage_ulid = console_ulid or session.console_ulid or session.experiment_ctx.experiment_run_ulid

                    with StageCtxManager(
                        ConnectToVMStage(),
                        stage_ulid,
                        event=None  # Dev mode doesn't have a dedicated interrupt event at this point
                    ) as stage_ctx:
                        stage_ctx.stage.sub_msg = f"Reconnecting to localhost:{websocket_port}"

                        log.info(f"Attempting WebSocket reconnection to localhost:{websocket_port}")
                        client = AdareVMClient(port=websocket_port)

                        # Try to reconnect
                        if hasattr(client, 'reconnect'):
                            websocket_reconnected = await client.reconnect(retries=2)
                        else:
                            # Fallback to connect if reconnect not available yet
                            websocket_reconnected = await client.connect(timeout=5.0)

                        if websocket_reconnected:
                            session.experiment_ctx.client = client
                            session.playbook_controller.update_websocket_client(client)
                            log.info("WebSocket reconnected successfully")
                            stage_ctx.stage.sub_msg = "Connected successfully"
                        else:
                            log.warning(
                                "WebSocket reconnection failed. Some operations "
                                "(playbook execution) will not work."
                            )
                            stage_ctx.stage.sub_msg = "Connection failed"
                            # Don't raise error - session can still be used for cleanup operations

                except Exception as e:
                    log.warning(f"WebSocket reconnection failed: {e}")
                    log.info(
                        "Session restored but WebSocket unavailable. "
                        "This can happen if:\n"
                        "  1. adarevm server crashed after session was created\n"
                        "  2. Port forwarding is not configured (port 18765)\n"
                        "  3. VM firewall is blocking the connection\n"
                        "  4. VM is not running or not accessible\n"
                        "Stop/cleanup operations will still work, but playbook execution requires WebSocket."
                    )
            else:
                log.debug("Skipping WebSocket reconnection as requested")
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

    async def restore_and_restart_session(
        self,
        session_id: str,
        console_ulid: Optional[str] = None
    ) -> Optional[DevModeSession]:
        """
        Restore a stopped session and restart its VM.

        This method is used when user runs 'adare dev start' to resume a stopped session.
        Unlike restore_session(), this method starts the VM if it's not running.

        Args:
            session_id: Session ID to restore and restart
            console_ulid: Optional flow console ULID for event integration

        Returns:
            DevModeSession if restored successfully, None otherwise
        """
        log.info(f"Restoring and restarting stopped session {session_id}")

        # Import database API
        from adare.database.api.devmode import DevModeApi

        try:
            # 1. Query database for session metadata
            db_api = DevModeApi()
            db_session = db_api.get_session(session_id)

            if not db_session:
                log.warning(f"Session {session_id} not found in database")
                return None

            if db_session.status != 'stopped':
                log.warning(
                    f"Session {session_id} has status '{db_session.status}', "
                    f"expected 'stopped' for restart operation"
                )
                return None

            # 2. Validate VM resources exist
            from adare.backend.environment import database as environment_database

            try:
                environment_ulid = environment_database.resolve_environment_identifier(
                    db_session.environment_name
                )
                hypervisor_type = environment_database.get_environment_hypervisor(environment_ulid)
            except Exception as e:
                log.error(f"Failed to resolve environment: {e}")
                return None

            # 3. Check if VM disk file exists
            vm_file = environment_database.get_environment_vm_file(environment_ulid)
            if vm_file and not vm_file.exists():
                log.error(
                    f"VM disk file not found: {vm_file}. "
                    f"Cannot restart session {session_id}."
                )
                return None

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
                console_ulid=console_ulid
            )

            # 5. Restore context with VM startup
            success = await restore_context(
                session,
                db_session,
                console_ulid=console_ulid,
                should_start_vm=True
            )

            if not success:
                log.error(f"Failed to restore context for session {session_id}")
                return None

            # 6. Update database status to 'running'
            db_api.update_session_status(session_id, 'running')
            log.info(f"Updated session {session_id} status to 'running'")

            # 7. Add to sessions dict
            self._sessions[session_id] = session

            log.info(f"Session {session_id} restored and restarted successfully")
            return session

        except Exception as e:
            log.error(f"Failed to restore and restart session {session_id}: {e}", exc_info=True)
    async def load_session_for_cleanup(
        self,
        session_id: str
    ) -> Optional[DevModeSession]:
        """
        Load session infrastructure for cleanup operation.

        This method restores ONLY the infrastructure context (directories, VM object)
        needed to destroy resources. It does NOT load playbooks, start servers,
        or attempt to reconnect to the VM application layer.

        Args:
            session_id: Session ID to load

        Returns:
            DevModeSession with infrastructure loaded, or None if failed
        """
        log.info(f"Loading session context for cleanup: {session_id}")

        # Import database API
        from adare.database.api.devmode import DevModeApi

        try:
            # 1. Query database for session metadata
            db_api = DevModeApi()
            db_session = db_api.get_session(session_id)

            if not db_session:
                log.warning(f"Session {session_id} not found in database")
                return None

            # 2. Create session object
            session = DevModeSession(
                session_id=session_id,
                project_path=Path(db_session.project_path),
                experiment_name=db_session.experiment_name,
                environment_name=db_session.environment_name,
                gui_mode=None,
                vm_memory=None,
                vm_cpus=None,
                debug_screenshots=False
            )

            # 3. Restore ONLY infrastructure context
            # This attaches to the VM object (so we can destroy it) but doesn't
            # try to connect to the agent
            success = await restore_infrastructure_context(session, db_session)

            if not success:
                log.error(f"Failed to restore infrastructure context for cleanup of {session_id}")
                return None
            
            # 4. Attempt to find VM instance ID for release (best effort)
            try:
                from adare.database.api.experiment import ExperimentApi
                from adare.database.models.project_models import ExperimentRun
                
                # Check if we can get the instance ID from fake experiment run (if it exists)
                # But since we didn't fully restore, check DB directly again
                if session.experiment_ctx:
                     with ExperimentApi(session.project_path) as api:
                        # Construct fake experiment run ID
                        # In new model, the run ID is exactly the session ID
                        fake_run_id = session_id
                        experiment_run = api._session.query(ExperimentRun).filter(
                            ExperimentRun.id == fake_run_id
                        ).first()

                        if experiment_run and experiment_run.vm_instance_id:
                            session.vm_instance_id = experiment_run.vm_instance_id
                            log.debug(f"Loaded VM instance ID for cleanup: {session.vm_instance_id}")
            except Exception as e:
                log.debug(f"Could not load VM instance ID (non-fatal): {e}")

            return session

        except Exception as e:
            log.error(f"Failed to load session for cleanup {session_id}: {e}", exc_info=True)
            return None

    async def get_or_restore_session(
        self,
        session_id: str,
        console_ulid: Optional[str] = None,
        connect_websocket: bool = True
    ) -> Optional[DevModeSession]:
        """
        Get session from memory or restore from database if not present.

        This is the primary method that should be used by service layer.
        It provides transparent session restoration without client awareness.

        NOTE: Only restores 'running' sessions. Stopped sessions must be
        explicitly resumed via restore_and_restart_session() (typically
        called from start_session() in the service layer).

        Args:
            session_id: Session ID to retrieve
            console_ulid: Optional console ULID for flow console routing
            connect_websocket: Whether to reconnect WebSocket if restored (default: True)

        Returns:
            DevModeSession if found or restored, None otherwise
        """
        # Fast path: return from memory if present
        session = self._sessions.get(session_id)
        if session:
            # Update console_ulid if provided
            if console_ulid and session.console_ulid != console_ulid:
                session.console_ulid = console_ulid
            return session

        # Slow path: attempt restoration from database
        log.info(f"Session {session_id} not in memory, attempting restoration")

        try:
            # Check database status first
            from adare.database.api.devmode import DevModeApi
            db_api = DevModeApi()
            db_session = db_api.get_session(session_id)

            if not db_session:
                log.warning(f"Session {session_id} not found in database")
                return None

            # Only restore 'running' sessions automatically
            # Stopped sessions must be explicitly resumed via restore_and_restart_session()
            if db_session.status == 'running':
                restored = await self.restore_session(
                    session_id, 
                    console_ulid=console_ulid,
                    connect_websocket=connect_websocket
                )
                return restored
            elif db_session.status == 'stopped':
                log.info(
                    f"Session {session_id} is stopped. "
                    f"Use 'adare dev start' to resume it."
                )
                return None
            else:
                log.warning(
                    f"Session {session_id} has unexpected status '{db_session.status}'"
                )
                return None

        except Exception as e:
            log.error(f"Failed to restore session {session_id}: {e}", exc_info=True)
            return None
