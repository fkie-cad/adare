"""Database API for host resource history and measured per-run usage."""

import logging
from datetime import datetime

from adare.database.api.base import GlobalDatabaseApi
from adare.database.models.global_models import ResourceSample, RunResourceUsage

log = logging.getLogger(__name__)


class SystemDbApi(GlobalDatabaseApi):
    def add_sample(self, **values) -> ResourceSample:
        sample = ResourceSample(**values)
        self._session.add(sample)
        return sample

    def samples_since(self, since: datetime) -> list[ResourceSample]:
        return list(
            self._session.query(ResourceSample)
            .filter(ResourceSample.taken_at >= since)
            .order_by(ResourceSample.taken_at)
            .all()
        )

    def delete_samples_before(self, before: datetime) -> int:
        return int(self._session.query(ResourceSample).filter(ResourceSample.taken_at < before).delete())

    def add_run_usage(self, **values) -> RunResourceUsage:
        usage = RunResourceUsage(**values)
        self._session.add(usage)
        return usage

    def run_usage(self, environment_name: str | None = None, limit: int | None = None) -> list[RunResourceUsage]:
        """Measured run usage, newest first."""
        query = self._session.query(RunResourceUsage)
        if environment_name is not None:
            query = query.filter(RunResourceUsage.environment_name == environment_name)
        query = query.order_by(RunResourceUsage.started_at.desc())
        if limit is not None:
            query = query.limit(limit)
        return list(query.all())
