"""Run-page details for ``ShowService.get_run``: test results and the run environment's VM.

Kept out of ``show_service.py`` to keep that file small. All lookups are best-effort: a
run whose environment was deleted still opens, just without OS / VM box.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class RunExtras:
    """What a run page shows beyond the run row."""

    test_results: list[dict[str, Any]] = field(default_factory=list)
    os_info: str | None = None
    vm_box: str | None = None


def load_run_extras(
    query_across_projects: Callable[..., list], ulid: str, project_name: str, fallback_environment_id: str
) -> RunExtras:
    """Test results (from the run's TestEvents) and OS / VM box (from the run's environment).

    Args:
        query_across_projects: ``ShowService._query_across_projects``.
        ulid: Run ULID.
        project_name: Project whose database holds the run.
        fallback_environment_id: Environment id to use when the run row names none.
    """
    found = query_across_projects(
        lambda api, _name: [extras] if (extras := api.get_run_detail_extras(ulid)) is not None else [],
        project_name=project_name,
    )
    if not found:
        return RunExtras()
    extras = found[0]
    environment_id = extras['environment_id'] or fallback_environment_id
    os_info, vm_box = _environment_vm(environment_id)
    return RunExtras(test_results=extras['test_results'], os_info=os_info, vm_box=vm_box)


def _environment_vm(environment_id: str) -> tuple[str | None, str | None]:
    """``(os_info, vm_name)`` of the (global) environment, ``(None, None)`` if unavailable."""
    if not environment_id:
        return None, None
    from sqlalchemy.exc import SQLAlchemyError

    from adare.database.api.structured_data import StructuredDataApi

    try:
        with StructuredDataApi() as global_api:
            summary = global_api.get_environment_vm_summary(environment_id)
    except (SQLAlchemyError, OSError) as e:
        log.warning(f"Could not read the VM of environment {environment_id}: {e}")
        return None, None
    return summary if summary is not None else (None, None)


def find_run_project_path(query_across_projects: Callable[..., list], ulid: str) -> Path | None:
    """Project directory whose database holds run ``ulid``, or None if no registered project has it."""
    owners = query_across_projects(lambda api, name: [name] if api.get_run_files(ulid) is not None else [])
    if not owners:
        return None
    path = project_paths_by_name().get(owners[0])
    return Path(path) if path else None


def project_paths_by_name() -> dict[str, str]:
    """Registered project name -> filesystem path."""
    from adare.database.api.structured_data import StructuredDataApi

    with StructuredDataApi() as global_api:
        return {project.name: project.path for project in global_api.get_projects_structured()}
