# external imports
# configure logging
import datetime
import logging
from pathlib import Path

from sqlalchemy import exists

# internal imports
from adare.database.api.base import GlobalDatabaseApi
from adare.database.models.global_models import Environment, PostSetupInstallation, SyncMetadata, Tag
from adare.database.models.sync_identity import apply_remote_identity
from adare.types.environment import PostsetupInstallations as PostsetupInstallationsAttrs

log = logging.getLogger(__name__)


class EnvironmentDbApi(GlobalDatabaseApi):
    def __init__(self):
        super().__init__()
        self._start_session()

    def get_or_create_tags(self, tag_names: list[str]) -> list:
        """
        Get or create multiple tags.

        Args:
            tag_names: List of tag names

        Returns:
            List of Tag instances
        """
        tags = []
        for name in tag_names:
            if name and name.strip():
                tag, _ = self.get_or_create(Tag, name=name.strip().lower())
                tags.append(tag)
        return tags

    def get_environment_by_ulid(self, ulid: str) -> Environment:
        return self._session.query(Environment).filter(Environment.id == ulid).first()

    def is_vm_referenced(self, vm_id: str) -> bool:
        """True if any environment version (current or superseded) uses VM ``vm_id``."""
        return bool(self._session.query(exists().where(Environment.vm_id == vm_id)).scalar())

    def create_environment_version(
        self,
        name: str,
        description: str,
        vm_id: str | None,
        vm_hash: str | None,
        tags: list[str],
        installations: list[dict],
        environment_file: Path,
        sha256hash: str,
        hypervisor: str,
    ) -> Environment:
        """Insert a new current version of environment ``name``.

        The previous current version (if any) is kept and marked superseded, so
        experiment runs that reference it keep resolving -- loading a changed
        environment file never deletes results.
        """
        previous = self.get_current_environment(name)
        if previous is not None:
            previous.superseded_at = datetime.datetime.now(datetime.UTC)
            # Flush before the insert: the partial unique index allows only one
            # current row per name.
            self._session.flush()
            log.info(f"Environment '{name}' version {previous.id} superseded")

        environment = Environment(
            name=name,
            description=description,
            vm_id=vm_id,
            vm_hash=vm_hash,
            sha256hash=sha256hash,
            hypervisor=hypervisor,
            file=environment_file.resolve().as_posix(),  # Store absolute path
            tags=self.get_or_create_tags(tags),
        )
        environment.installations = [
            self.get_or_create(PostSetupInstallation, **install_dict)[0] for install_dict in installations
        ]
        self._session.add(environment)
        self._session.commit()
        return environment

    def get_current_environment(self, name: str) -> Environment | None:
        """The current (non-superseded) version of environment ``name``."""
        environment: Environment | None = (
            self._session.query(Environment).filter(Environment.name == name, Environment.is_current).first()
        )
        return environment

    def get_environment_versions(self, name: str) -> list[Environment]:
        """All versions of environment ``name``, oldest first."""
        return (
            self._session.query(Environment)
            .filter(Environment.name == name)
            .order_by(Environment.created_at, Environment.id)
            .all()
        )

    def delete_environment(self, environment: Environment):
        self._session.delete(environment)
        self._session.commit()
        log.info(f"Environment with hash '{environment.sha256hash}' deleted from database")

    def get_environments(self, project_path: Path = None, include_superseded: bool = False) -> list[Environment]:
        """All environments (they are global; ``project_path`` is ignored).

        Only current versions unless ``include_superseded`` -- callers deciding
        whether a VM or file is still referenced must pass True.
        """
        query = self._session.query(Environment)
        if not include_superseded:
            query = query.filter(Environment.is_current)
        return query.all()

    def get_environment_installations(self, environment_ulid: str):
        if env := self._session.query(Environment).filter_by(id=environment_ulid).first():
            return [
                PostsetupInstallationsAttrs(
                    name=installation.name, command=installation.command, description=installation.description
                )
                for installation in env.installations
            ]
        raise ValueError(f'environment {environment_ulid} not found in database')

    def get_environment_platform(self, environment_ulid: str):
        if env := self._session.query(Environment).filter_by(id=environment_ulid).first():
            return env.vm.osinfo.platform
        raise ValueError(f'environment {environment_ulid} not found in database')

    def get_environment(self, name: str, project_name: str) -> Environment | None:
        # Since environments are now global, we just search by name (project_name is ignored)
        env = self.get_current_environment(name)
        if env:
            return env
        log.error(f'environment {name} does not exist in the database')
        return None

    def get_environment_by_project_and_name(self, project_path: Path, environment_name: str) -> Environment | None:
        # Since environments are now global, we just search by name
        return self.get_current_environment(environment_name)

    def sync_environment(self, ulid: str, remote_ulid: str, remote_url: str, is_published: bool):
        """Record where this environment lives on the server.

        Writes the environment's SyncMetadata row — the same row
        ``safe_get_sync_status`` reads for the published / in-request display.
        ``remote_ulid`` etc. are read back through
        :class:`~adare.database.models.sync_identity.RemoteIdentityMixin`.
        """
        environment = self.get_environment_by_ulid(ulid)
        apply_remote_identity(
            self._session,
            environment,
            SyncMetadata,
            remote_ulid=remote_ulid,
            remote_url=remote_url,
            is_published=is_published,
        )
        self._session.commit()
        return environment
