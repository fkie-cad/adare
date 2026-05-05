"""
Output models for structured JSON/YAML data.

These models provide standardized data structures for CLI output formatting.
"""
from datetime import datetime
from typing import Any

import attrs


@attrs.define
class ProjectInfo:
    """Project information for structured output."""
    name: str
    description: str = ""
    path: str = ""
    created_at: datetime | None = None
    experiment_count: int = 0
    environment_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            'name': self.name,
            'description': self.description,
            'path': self.path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'experiment_count': self.experiment_count,
            'environment_count': self.environment_count,
        }


@attrs.define
class EnvironmentInfo:
    """Environment information for structured output."""
    name: str
    ulid: str
    project: str
    description: str = ""
    os_info: str = ""
    vm_box: str = ""
    created_at: datetime | None = None
    experiment_count: int = 0
    dotnotation: str = ""
    display_name: str = ""
    vm_id: str = ""
    osinfo_os: str = ""
    osinfo_distribution: str = ""
    osinfo_version: str = ""
    osinfo_language: str = ""
    published: bool = False
    in_request: bool = False
    file: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            'ulid': self.ulid,
            'name': self.name,
            'display_name': self.display_name,
            'dotnotation': self.dotnotation,
            'project': self.project,
            'description': self.description,
            'vm': {
                'id': self.vm_id,
                'name': self.vm_box,
                'os_info': self.os_info,
            },
            'os_details': {
                'os': self.osinfo_os,
                'distribution': self.osinfo_distribution,
                'version': self.osinfo_version,
                'language': self.osinfo_language,
            },
            'sync_status': {
                'published': self.published,
                'in_request': self.in_request,
            },
            'metadata': {
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'experiment_count': self.experiment_count,
            },
            'file': self.file
        }


@attrs.define
class ExperimentInfo:
    """Experiment information for structured output."""
    name: str
    ulid: str
    project: str
    environment: str
    description: str = ""
    tags: list[str] = attrs.Factory(list)
    created_at: datetime | None = None
    run_count: int = 0
    last_run: datetime | None = None
    dotnotation: str = ""
    display_name: str = ""
    environments: list[str] = attrs.Factory(list)
    environment_ids: list[str] = attrs.Factory(list)
    environment_names: list[str] = attrs.Factory(list)
    published: bool = False
    in_request: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            'ulid': self.ulid,
            'name': self.name,
            'display_name': self.display_name,
            'dotnotation': self.dotnotation,
            'description': self.description,
            'tags': self.tags,
            'project': self.project,
            'environments': self.environments,
            'environment_ids': self.environment_ids,
            'environment_names': self.environment_names,
            'primary_environment': self.environment,
            'sync_status': {
                'published': self.published,
                'in_request': self.in_request,
            },
            'metadata': {
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'run_count': self.run_count,
                'last_run': self.last_run.isoformat() if self.last_run else None,
            }
        }


@attrs.define
class TestFunctionInfo:
    """Test function information for structured output."""
    name: str
    dotnotation: str
    description: str = ""
    parameters: list[dict[str, Any]] = attrs.Factory(list)
    file_path: str = ""
    id: str | None = None
    file_id: str | None = None
    display_name: str = ""
    parameter_count: int = 0
    file_name: str = ""
    file_sha256: str = ""
    file_description: str = ""
    full_file_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'dotnotation': self.dotnotation,
            'display_name': self.display_name,
            'description': self.description,
            'parameter_count': self.parameter_count,
            'parameters': self.parameters,
            'file': {
                'id': self.file_id,
                'name': self.file_name,
                'path': self.file_path,
                'full_path': self.full_file_path,
                'sha256': self.file_sha256,
                'description': self.file_description,
            }
        }


@attrs.define
class RunInfo:
    """Experiment run information for structured output."""
    ulid: str
    experiment_name: str
    experiment_ulid: str
    environment_name: str
    environment_ulid: str
    project_name: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_seconds: float = 0.0
    status: str = ""
    published: bool = False
    fake: bool = False
    os_info: str = ""
    vm_box: str = ""
    test_results: list[dict[str, Any]] = attrs.Factory(list)
    overall_result: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            'ulid': self.ulid,
            'experiment': {
                'name': self.experiment_name,
                'ulid': self.experiment_ulid,
            },
            'environment': {
                'name': self.environment_name,
                'ulid': self.environment_ulid,
            },
            'project': self.project_name,
            'timing': {
                'start_time': self.start_time.isoformat() if self.start_time else None,
                'end_time': self.end_time.isoformat() if self.end_time else None,
                'duration_seconds': self.duration_seconds,
            },
            'status': self.status,
            'metadata': {
                'published': self.published,
                'fake': self.fake,
                'os_info': self.os_info,
                'vm_box': self.vm_box,
            },
            'test_results': {
                'overall_result': self.overall_result,
                'tests': self.test_results,
            }
        }


@attrs.define
class VMInfo:
    """VM information for structured output."""
    name: str
    status: str = ""
    environment: str = ""
    project: str = ""
    memory: str = ""
    cpus: int = 0
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            'name': self.name,
            'status': self.status,
            'environment': self.environment,
            'project': self.project,
            'memory': self.memory,
            'cpus': self.cpus,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
