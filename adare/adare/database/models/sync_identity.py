"""Read/write access to an entity's remote (server-side) identity.

Every entity that can be published to the ADARE web app records *where it went*:
the server's ULID, its Gitea URL, and whether the publish completed or is still
sitting in a submit request. That state lives in a ``SyncMetadata`` row which the
entity points at through ``sync_metadata_id``.

Both bases have their own ``SyncMetadata`` class — the global DB
(:mod:`adare.database.models.global_models`) and the project DB
(:mod:`adare.database.models.project_models`) are separate SQLite files, so a
cross-database foreign key is impossible. The mixin here is plain Python and
therefore works for both.

Why this module exists: the ``sync_*`` APIs used to assign ``remote_ulid`` /
``remote_url`` / ``published`` / ``in_request`` straight onto the model. None of
those is a mapped column, so SQLAlchemy took the assignment as an ordinary
instance attribute and ``commit()`` wrote nothing — the remote identity was lost
the moment the session closed, and `adare web publish <run>` then failed with
*"Experiment X is not published on the server"* for an experiment that was.
Meanwhile the read side (``database/utils/display_helpers.safe_get_sync_status``)
was already looking at ``sync_metadata``, i.e. at the right place.
"""

import logging
from datetime import UTC, datetime

log = logging.getLogger(__name__)

# SyncStatusEnum values that encode publish state. 'synced' = live on the server;
# 'pending' = submitted, waiting for the maintainer to merge the request.
SYNC_STATUS_PUBLISHED = 'synced'
SYNC_STATUS_IN_REQUEST = 'pending'


class RemoteIdentityMixin:
    """Read-side view of the entity's ``SyncMetadata`` row.

    Read-only on purpose. Writing goes through :func:`apply_remote_identity`,
    which needs the session so it can INSERT the row when there is none — and a
    property setter that silently did nothing is the exact bug this replaces.
    """

    @property
    def remote_ulid(self) -> str | None:
        """ULID this entity has on the server, or None if never published."""
        meta = self.sync_metadata
        return meta.remote_id if meta else None

    @property
    def remote_url(self) -> str | None:
        """Gitea URL of the published entity, or None."""
        meta = self.sync_metadata
        return meta.remote_url if meta else None

    @property
    def published(self) -> bool:
        """True once the server confirmed the entity is live."""
        meta = self.sync_metadata
        return bool(meta.is_synced) if meta else False

    @property
    def in_request(self) -> bool:
        """True while a submit request for this entity is awaiting merge."""
        meta = self.sync_metadata
        return bool(meta.needs_sync) if meta else False


def apply_remote_identity(session, entity, sync_metadata_cls, *,
                          remote_ulid: str | None,
                          remote_url: str | None,
                          is_published: bool):
    """Persist *entity*'s remote identity, creating its SyncMetadata row if needed.

    Args:
        session: the open SQLAlchemy session owning *entity*.
        entity: a model carrying ``sync_metadata`` (see :class:`RemoteIdentityMixin`).
        sync_metadata_cls: the ``SyncMetadata`` class of *entity*'s own base —
            ``global_models.SyncMetadata`` or ``project_models.SyncMetadata``.
        remote_ulid: the server's ULID for this entity.
        remote_url: the Gitea URL of the published entity.
        is_published: True if live on the server, False if only submitted.

    The caller commits.
    """
    meta = entity.sync_metadata
    if meta is None:
        meta = sync_metadata_cls()
        session.add(meta)
        entity.sync_metadata = meta
    meta.remote_id = remote_ulid
    meta.remote_url = remote_url
    meta.sync_status = SYNC_STATUS_PUBLISHED if is_published else SYNC_STATUS_IN_REQUEST
    meta.sync_direction = 'push'
    meta.last_sync_at = datetime.now(UTC)
    meta.failure_reason = None
    return meta
