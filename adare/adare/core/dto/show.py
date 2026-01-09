"""
Show Data Transfer Objects for API layer.

These DTOs provide type-safe request/response objects for show operations,
enabling consistent interfaces across CLI, REST API, and Web UI.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime


# =============================================================================
# Request DTOs
# =============================================================================

@dataclass
class RunListRequest:
    """Request for listing runs with filters."""
    project: Optional[str] = None
    environment: Optional[str] = None
    experiment: Optional[str] = None


@dataclass
class RunRemoveRequest:
    """Request to remove a run."""
    ulid: str
    project_path: Optional[Path] = None


# =============================================================================
# Result DTOs
# =============================================================================

@dataclass
class RunListItem:
    """Single run item in list."""
    ulid: str
    experiment_name: str
    experiment_ulid: str
    environment_name: str
    environment_ulid: str
    project_name: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    status: str = ""
    result_status: str = ""
    published: bool = False
    fake: bool = False

    def to_dict(self) -> Dict[str, Any]:
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
            'result_status': self.result_status,
            'metadata': {
                'published': self.published,
                'fake': self.fake,
            }
        }


@dataclass
class RunDetail:
    """Detailed run information."""
    ulid: str
    experiment_name: str
    experiment_ulid: str
    environment_name: str
    environment_ulid: str
    project_name: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    status: str = ""
    result_status: str = ""
    published: bool = False
    fake: bool = False
    os_info: str = ""
    vm_box: str = ""
    test_results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RunRemoveResult:
    """Result of run removal operation."""
    removed: bool
    ulid: str
    was_fake: bool = False


@dataclass
class ProjectListItem:
    """Single project item in list."""
    name: str
    description: str = ""
    created_at: Optional[datetime] = None
    experiment_count: int = 0
    environment_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'experiment_count': self.experiment_count,
            'environment_count': self.environment_count,
        }


@dataclass
class EnvironmentListItem:
    """Single environment item in list."""
    ulid: str
    name: str
    display_name: str
    dotnotation: str
    project: str
    description: str = ""
    vm_name: str = ""
    vm_id: str = ""
    os_info: str = ""
    osinfo_os: str = ""
    osinfo_distribution: str = ""
    osinfo_version: str = ""
    osinfo_language: str = ""
    published: bool = False
    in_request: bool = False
    created_at: Optional[datetime] = None
    file: str = ""

    def to_dict(self) -> Dict[str, Any]:
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
                'name': self.vm_name,
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
            },
            'file': self.file
        }


@dataclass
class EnvironmentDetail:
    """Detailed environment information."""
    ulid: str
    name: str
    display_name: str
    dotnotation: str
    project: str
    description: str = ""
    vm_name: str = ""
    vm_id: str = ""
    os_info: str = ""
    osinfo_os: str = ""
    osinfo_distribution: str = ""
    osinfo_version: str = ""
    osinfo_language: str = ""
    published: bool = False
    in_request: bool = False
    created_at: Optional[datetime] = None
    file: str = ""
    experiment_count: int = 0


@dataclass
class ExperimentListItem:
    """Single experiment item in list."""
    ulid: str
    name: str
    display_name: str
    dotnotation: str
    project: str
    environment: str
    environments: List[str] = field(default_factory=list)
    description: str = ""
    tags: List[str] = field(default_factory=list)
    published: bool = False
    in_request: bool = False
    created_at: Optional[datetime] = None
    run_count: int = 0
    last_run: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
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


@dataclass
class ExperimentDetail:
    """Detailed experiment information."""
    ulid: str
    name: str
    display_name: str
    dotnotation: str
    project: str
    environment: str
    environments: List[str] = field(default_factory=list)
    description: str = ""
    tags: List[str] = field(default_factory=list)
    published: bool = False
    in_request: bool = False
    created_at: Optional[datetime] = None
    run_count: int = 0
    last_run: Optional[datetime] = None
    playbook_items: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TestfunctionListItem:
    """Single testfunction item in list."""
    id: str
    name: str
    dotnotation: str
    display_name: str
    description: str = ""
    parameter_count: int = 0
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    file_id: str = ""
    file_name: str = ""
    file_path: str = ""
    full_file_path: str = ""
    file_sha256: str = ""
    file_description: str = ""

    def to_dict(self) -> Dict[str, Any]:
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


@dataclass
class TestfunctionDetail:
    """Detailed testfunction information."""
    id: str
    name: str
    dotnotation: str
    display_name: str
    description: str = ""
    parameter_count: int = 0
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    file_id: str = ""
    file_name: str = ""
    file_path: str = ""
    full_file_path: str = ""
    file_sha256: str = ""
    file_description: str = ""
    source_code: str = ""
