"""
Database API for DevMode session management.

This module provides CRUD operations for persistent dev mode sessions:
- Session creation and deletion
- Session retrieval and listing
- Status updates
- Stale session cleanup
"""

import logging
from datetime import datetime
from pathlib import Path

from adare.database.api.base import EnhancedDatabaseApi
from adare.database.exceptions import EntityNotFoundError, ValidationError
from adare.database.models.devcheckpoint import DevCheckpoint
from adare.database.models.devsession import DevSession
from adare.database.models.global_models import GlobalBase

log = logging.getLogger(__name__)


class DevModeApi(EnhancedDatabaseApi):
    """
    API for managing dev mode sessions in the database.

    Provides operations for:
    - Creating and persisting new sessions
    - Retrieving session metadata
    - Updating session status
    - Cleaning up stale sessions
    """

    def __init__(self, db_path: Path | None = None):
        """
        Initialize DevMode API with database connection.

        Args:
            db_path: Optional path to database file (uses global DB if None)
        """
        super().__init__(db_path)
        self._start_session()
        GlobalBase.metadata.create_all(self.engine)

    def save_session(
        self,
        session_id: str,
        project_path: Path,
        experiment_name: str,
        environment_name: str,
        vm_name: str
    ) -> DevSession:
        """
        Persist a new dev mode session to the database.

        Args:
            session_id: Unique ULID identifier for the session
            project_path: Path to the ADARE project
            experiment_name: Name of the experiment being developed
            environment_name: Name of the VM environment
            vm_name: Name of the VM instance

        Returns:
            Created DevSession instance

        Raises:
            ValidationError: If session_id already exists
        """
        # Check if session already exists
        existing = self._session.query(DevSession).filter(
            DevSession.session_id == session_id
        ).first()

        if existing:
            raise ValidationError(log, f"Dev session '{session_id}' already exists")

        # Create new session
        session = DevSession(
            session_id=session_id,
            project_path=str(project_path),
            experiment_name=experiment_name,
            environment_name=environment_name,
            vm_name=vm_name,
            status='running',
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        self._session.add(session)
        self._session.flush()
        self._session.commit()

        log.info(f"Saved dev session {session_id} to database")
        return session

    def get_session(self, session_id: str) -> DevSession | None:
        """
        Retrieve a dev session by ID.

        Args:
            session_id: Unique session identifier

        Returns:
            DevSession instance or None if not found
        """
        return self._session.query(DevSession).filter(
            DevSession.session_id == session_id
        ).first()

    def get_session_or_404(self, session_id: str) -> DevSession:
        """
        Retrieve a dev session or raise exception if not found.

        Args:
            session_id: Unique session identifier

        Returns:
            DevSession instance

        Raises:
            EntityNotFoundError: If session not found
        """
        session = self.get_session(session_id)
        if not session:
            raise EntityNotFoundError(log, f"Dev session '{session_id}' not found")
        return session

    def list_sessions(
        self,
        project_path: Path | None = None,
        status: str | None = None
    ) -> list[DevSession]:
        """
        List dev sessions with optional filtering.

        Args:
            project_path: Filter by project path (optional)
            status: Filter by status ('running', 'stopped', 'crashed') (optional)

        Returns:
            List of DevSession instances
        """
        query = self._session.query(DevSession)

        if project_path:
            query = query.filter(DevSession.project_path == str(project_path))

        if status:
            query = query.filter(DevSession.status == status)

        # Order by most recent first
        query = query.order_by(DevSession.created_at.desc())

        return query.all()

    def list_running_sessions(self, project_path: Path | None = None) -> list[DevSession]:
        """
        List all running dev sessions.

        Args:
            project_path: Filter by project path (optional)

        Returns:
            List of running DevSession instances
        """
        return self.list_sessions(project_path=project_path, status='running')

    def update_session_status(self, session_id: str, status: str) -> DevSession:
        """
        Update the status of a dev session.

        Args:
            session_id: Session ID to update
            status: New status ('running', 'stopped', 'crashed')

        Returns:
            Updated DevSession instance

        Raises:
            EntityNotFoundError: If session not found
            ValidationError: If status is invalid
        """
        valid_statuses = ['running', 'stopped', 'crashed']
        if status not in valid_statuses:
            raise ValidationError(
                log,
                f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}"
            )

        session = self.get_session_or_404(session_id)
        session.status = status
        session.updated_at = datetime.now()
        self._session.flush()
        self._session.commit()

        log.info(f"Updated dev session {session_id} status to '{status}'")
        return session

    def update_session_overlay_path(self, session_id: str, overlay_disk_path: str) -> DevSession:
        """
        Update the overlay disk path for a session.

        This is critical for preventing base disk deletion - we must track
        which overlay disk is being used so we delete the overlay, not the base.

        Args:
            session_id: Session ID to update
            overlay_disk_path: Path to the experiment overlay disk

        Returns:
            Updated DevSession instance

        Raises:
            EntityNotFoundError: If session not found
        """
        session = self.get_session_or_404(session_id)
        session.overlay_disk_path = overlay_disk_path
        session.updated_at = datetime.now()
        self._session.flush()
        self._session.commit()

        log.info(f"Updated dev session {session_id} overlay_disk_path to '{overlay_disk_path}'")
        return session

    def update_session_run_path(self, session_id: str, run_directory_path: str) -> DevSession:
        """
        Update the run directory path for a session.

        This prevents "None" directories by storing the exact path after creation
        and ensuring all operations (restoration, checkpoints, logging) use the
        same directory path.

        Args:
            session_id: Session ID to update
            run_directory_path: Absolute path to the experiment run directory

        Returns:
            Updated DevSession instance

        Raises:
            EntityNotFoundError: If session not found
        """
        session = self.get_session_or_404(session_id)
        session.run_directory_path = run_directory_path
        session.updated_at = datetime.now()
        self._session.flush()
        self._session.commit()

        log.info(f"Updated dev session {session_id} run_directory_path to '{run_directory_path}'")
        return session

    def update_session_cached_command(self, session_id: str, command: str) -> DevSession:
        """
        Update the cached start command for a session.

        Allows skipping environment detection and installation on restore.

        Args:
            session_id: Session ID to update
            command: The full command string to start adarevm

        Returns:
            Updated DevSession instance
        """
        session = self.get_session_or_404(session_id)
        session.cached_start_command = command
        session.updated_at = datetime.now()
        self._session.flush()
        self._session.commit()

        log.info(f"Updated dev session {session_id} cached_start_command")
        return session

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a dev session from the database.

        Args:
            session_id: Session ID to delete

        Returns:
            True if session was deleted, False if not found
        """
        session = self.get_session(session_id)
        if not session:
            log.warning(f"Dev session {session_id} not found for deletion")
            return False

        self._session.delete(session)
        self._session.flush()
        self._session.commit()

        log.info(f"Deleted dev session {session_id} from database")
        return True

    def cleanup_stale_sessions(self, check_vm_exists: callable | None = None) -> int:
        """
        Cleanup stale sessions (e.g., VMs that no longer exist).

        Args:
            check_vm_exists: Optional callback function that takes vm_name and returns bool
                           If provided, sessions for non-existent VMs will be removed

        Returns:
            Number of sessions cleaned up
        """
        sessions = self.list_sessions()
        cleaned = 0

        for session in sessions:
            should_cleanup = False

            # Check if VM still exists (if callback provided)
            if check_vm_exists:
                try:
                    if not check_vm_exists(session.vm_name):
                        log.info(
                            f"Cleaning up session {session.session_id} - "
                            f"VM '{session.vm_name}' no longer exists"
                        )
                        should_cleanup = True
                except (OSError, RuntimeError) as e:
                    log.warning(
                        f"Error checking VM existence for session {session.session_id}: {e}"
                    )

            if should_cleanup:
                self.delete_session(session.session_id)
                cleaned += 1

        if cleaned > 0:
            log.info(f"Cleaned up {cleaned} stale dev sessions")

        return cleaned

    def get_session_count(self, project_path: Path | None = None) -> int:
        """
        Get count of dev sessions.

        Args:
            project_path: Filter by project path (optional)

        Returns:
            Number of sessions
        """
        return len(self.list_sessions(project_path=project_path))

    def session_exists(self, session_id: str) -> bool:
        """
        Check if a dev session exists.

        Args:
            session_id: Session ID to check

        Returns:
            True if session exists, False otherwise
        """
        return self.get_session(session_id) is not None

    # Checkpoint Management Operations

    def save_checkpoint(self, checkpoint: DevCheckpoint) -> DevCheckpoint:
        """
        Persist a checkpoint to the database.

        Args:
            checkpoint: DevCheckpoint instance to save

        Returns:
            Saved DevCheckpoint instance

        Raises:
            ValidationError: If checkpoint with same name already exists for session
        """
        # Check if checkpoint with same name exists for this session
        existing = self._session.query(DevCheckpoint).filter(
            DevCheckpoint.session_id == checkpoint.session_id,
            DevCheckpoint.name == checkpoint.name
        ).first()

        if existing:
            raise ValidationError(
                log,
                f"Checkpoint '{checkpoint.name}' already exists for session {checkpoint.session_id}"
            )

        self._session.add(checkpoint)
        self._session.flush()
        self._session.commit()

        log.info(f"Saved checkpoint {checkpoint.name} for session {checkpoint.session_id}")
        return checkpoint

    def get_checkpoint(self, session_id: str, name: str) -> DevCheckpoint | None:
        """
        Retrieve a checkpoint by session ID and name.

        Args:
            session_id: Session ID
            name: Checkpoint name

        Returns:
            DevCheckpoint instance or None if not found
        """
        return self._session.query(DevCheckpoint).filter(
            DevCheckpoint.session_id == session_id,
            DevCheckpoint.name == name
        ).first()

    def get_checkpoint_by_id(self, checkpoint_id: str) -> DevCheckpoint | None:
        """
        Retrieve a checkpoint by ID.

        Args:
            checkpoint_id: Unique checkpoint identifier

        Returns:
            DevCheckpoint instance or None if not found
        """
        return self._session.query(DevCheckpoint).filter(
            DevCheckpoint.checkpoint_id == checkpoint_id
        ).first()

    def get_checkpoint_or_404(self, session_id: str, name: str) -> DevCheckpoint:
        """
        Retrieve a checkpoint or raise exception if not found.

        Args:
            session_id: Session ID
            name: Checkpoint name

        Returns:
            DevCheckpoint instance

        Raises:
            EntityNotFoundError: If checkpoint not found
        """
        checkpoint = self.get_checkpoint(session_id, name)
        if not checkpoint:
            raise EntityNotFoundError(
                log,
                f"Checkpoint '{name}' not found for session {session_id}"
            )
        return checkpoint

    def list_checkpoints(self, session_id: str) -> list[DevCheckpoint]:
        """
        List all checkpoints for a session.

        Args:
            session_id: Session ID to filter by

        Returns:
            List of DevCheckpoint instances ordered by creation time
        """
        return self._session.query(DevCheckpoint).filter(
            DevCheckpoint.session_id == session_id
        ).order_by(DevCheckpoint.created_at.asc()).all()

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """
        Delete a checkpoint from the database.

        Args:
            checkpoint_id: Checkpoint ID to delete

        Returns:
            True if checkpoint was deleted, False if not found
        """
        checkpoint = self.get_checkpoint_by_id(checkpoint_id)
        if not checkpoint:
            log.warning(f"Checkpoint {checkpoint_id} not found for deletion")
            return False

        self._session.delete(checkpoint)
        self._session.flush()
        self._session.commit()

        log.info(f"Deleted checkpoint {checkpoint_id} from database")
        return True

    def delete_session_checkpoints(self, session_id: str) -> int:
        """
        Delete all checkpoints for a session.

        Args:
            session_id: Session ID to delete checkpoints for

        Returns:
            Number of checkpoints deleted
        """
        checkpoints = self.list_checkpoints(session_id)
        count = len(checkpoints)

        for checkpoint in checkpoints:
            self._session.delete(checkpoint)

        self._session.flush()
        self._session.commit()

        if count > 0:
            log.info(f"Deleted {count} checkpoints for session {session_id}")

        return count

    def checkpoint_exists(self, session_id: str, name: str) -> bool:
        """
        Check if a checkpoint exists.

        Args:
            session_id: Session ID
            name: Checkpoint name

        Returns:
            True if checkpoint exists, False otherwise
        """
        return self.get_checkpoint(session_id, name) is not None

    def get_stopped_session_by_experiment(
        self,
        project_path: Path,
        experiment_name: str,
        environment_name: str
    ) -> DevSession | None:
        """
        Get most recent stopped session matching experiment and environment.

        This is used for session resumption when user runs 'adare dev start' again.

        Args:
            project_path: Path to the ADARE project
            experiment_name: Name of the experiment
            environment_name: Name of the environment

        Returns:
            Most recent stopped DevSession matching criteria, or None if not found
        """
        return self._session.query(DevSession).filter(
            DevSession.project_path == str(project_path),
            DevSession.experiment_name == experiment_name,
            DevSession.environment_name == environment_name,
            DevSession.status == 'stopped'
        ).order_by(DevSession.updated_at.desc()).first()
