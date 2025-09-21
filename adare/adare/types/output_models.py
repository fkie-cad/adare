"""
Output models for structured JSON/YAML data.

These models provide standardized data structures for CLI output formatting.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import attrs


@attrs.define
class ProjectInfo:
    """Project information for structured output."""
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


@attrs.define
class EnvironmentInfo:
    """Environment information for structured output."""
    name: str
    ulid: str
    project: str
    description: str = ""
    os_info: str = ""
    vm_box: str = ""
    created_at: Optional[datetime] = None
    experiment_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            'name': self.name,
            'ulid': self.ulid,
            'project': self.project,
            'description': self.description,
            'os_info': self.os_info,
            'vm_box': self.vm_box,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'experiment_count': self.experiment_count,
        }


@attrs.define
class ExperimentInfo:
    """Experiment information for structured output."""
    name: str
    ulid: str
    project: str
    environment: str
    description: str = ""
    tags: List[str] = attrs.Factory(list)
    created_at: Optional[datetime] = None
    run_count: int = 0
    last_run: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            'name': self.name,
            'ulid': self.ulid,
            'project': self.project,
            'environment': self.environment,
            'description': self.description,
            'tags': self.tags,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'run_count': self.run_count,
            'last_run': self.last_run.isoformat() if self.last_run else None,
        }


@attrs.define
class TestFunctionInfo:
    """Test function information for structured output."""
    name: str
    dotnotation: str
    description: str = ""
    parameters: List[Dict[str, Any]] = attrs.Factory(list)
    file_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            'name': self.name,
            'dotnotation': self.dotnotation,
            'description': self.description,
            'parameters': self.parameters,
            'file_path': self.file_path,
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
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    status: str = ""
    published: bool = False
    fake: bool = False
    os_info: str = ""
    vm_box: str = ""
    test_results: List[Dict[str, Any]] = attrs.Factory(list)
    overall_result: str = ""

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
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
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