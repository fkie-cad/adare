"""Shared tool registry over :class:`~adare.api.AdareAPI`.

One declarative set of ADARE operations — each a :class:`ChatTool` with a
name, description, JSON-Schema parameters, and a callable that invokes an
``AdareAPI`` method and normalizes its :class:`~adare.core.result.Result` to a
uniform ``{ok, data|error}`` dict. Both brains consume this same set: the MCP
control server (:mod:`.mcp_control_server`) registers each tool as an
``@mcp.tool()``; the embedded REPL (:mod:`.repl`) feeds the same list to its
provider-agnostic brain (:mod:`.brain`), which exposes them over either native
OpenAI function-calling or a JSON-in-text contract.

Scope is the full lifecycle (project/env/experiment/run/vm/dev-session) plus the
LLM playbook-authoring harness wired in Phase 0
(``api.devmode.author_playbook``). Fine-grained per-step VM "hands" (click /
type / screenshot) are intentionally NOT here: a QMP connection is bound to the
event loop that created it, so a stateless per-call registry cannot safely drive
one live VM step-by-step. That remains the job of the long-lived, single-loop
``adare dev mcp`` server. The two conversational VM operations that DO own their
own loop internally — ``execute_playbook`` and ``author_playbook`` — are
exposed here and flagged ``serialized_vm`` (one VM, one input focus).

Tool callables are synchronous and may call ``asyncio.run`` internally (for the
few async ``AdareAPI`` methods); callers therefore MUST invoke them off the main
event loop — the MCP server and REPL both dispatch via ``asyncio.to_thread``.
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from adare.core.result import Result

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Tool model
# --------------------------------------------------------------------------- #
@dataclass
class ChatTool:
    """A single callable ADARE operation exposed to a brain.

    ``parameters`` is a JSON-Schema object (``{"type": "object", ...}``).
    ``func(**kwargs)`` returns a :class:`Result`, a dict, or any serializable
    value; :func:`call_tool` normalizes it. ``serialized_vm`` marks tools that
    drive the one live VM (must not overlap another VM-touching call).
    """

    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Any]
    serialized_vm: bool = False
    group: str = ''


# --------------------------------------------------------------------------- #
# Serialization: Result / dataclass / Path / datetime -> JSON-safe
# --------------------------------------------------------------------------- #
def _to_serializable(obj: Any) -> Any:
    """Recursively convert an API return value into JSON-safe primitives."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, datetime.timedelta):
        return obj.total_seconds()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k): _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_serializable(v) for v in obj]
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_serializable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if hasattr(obj, '__dict__'):
        return {k: _to_serializable(v) for k, v in vars(obj).items() if not k.startswith('_')}
    return str(obj)


def _normalize(value: Any) -> dict[str, Any]:
    """Normalize any tool return into a uniform ``{ok, data|error}`` envelope."""
    if isinstance(value, Result):
        if value.success:
            out: dict[str, Any] = {'ok': True, 'data': _to_serializable(value.data)}
            if value.warnings:
                out['warnings'] = list(value.warnings)
            return out
        err = value.error
        return {
            'ok': False,
            'error': {
                'code': err.code if err else 'ERROR',
                'message': err.message if err else 'unknown error',
                'solutions': (err.solutions if err else None) or [],
            },
        }
    return {'ok': True, 'data': _to_serializable(value)}


# Exceptions a tool callable may raise while building a request / resolving a
# project / running the API call. Caught per project convention (no bare
# ``except Exception``) and surfaced as a uniform error envelope.
_TOOL_ERRORS = (
    ValueError, KeyError, TypeError, AttributeError, FileNotFoundError,
    NotADirectoryError, IsADirectoryError, PermissionError, OSError, RuntimeError,
)


def call_tool(tool: ChatTool, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Invoke ``tool`` with ``arguments`` and return a normalized envelope."""
    args = arguments or {}
    try:
        return _normalize(tool.func(**args))
    except _TOOL_ERRORS as exc:
        log.warning('Tool %s failed: %s', tool.name, exc)
        return {'ok': False, 'error': {'code': type(exc).__name__, 'message': str(exc), 'solutions': []}}


# --------------------------------------------------------------------------- #
# JSON-Schema helpers
# --------------------------------------------------------------------------- #
def _schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        'type': 'object',
        'properties': properties or {},
        'required': required or [],
        'additionalProperties': False,
    }


def _str(desc: str) -> dict[str, Any]:
    return {'type': 'string', 'description': desc}


def _int(desc: str) -> dict[str, Any]:
    return {'type': 'integer', 'description': desc}


def _bool(desc: str) -> dict[str, Any]:
    return {'type': 'boolean', 'description': desc}


def _arr(desc: str) -> dict[str, Any]:
    return {'type': 'array', 'items': {'type': 'string'}, 'description': desc}


def _resolve_project(project: str | None) -> Path:
    """Resolve a project path from a name / dir, or the current directory."""
    from adare.backend.basics import determine_projectdirectory

    path = determine_projectdirectory(project, silent=True)
    if path is None:
        raise ValueError(
            'No ADARE project found. Pass "project" (a name or path) or run from '
            'within a project directory.'
        )
    return Path(path)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def build_tools(api: Any | None = None) -> list[ChatTool]:
    """Build the full tool registry, closing over a single ``AdareAPI``."""
    if api is None:
        from adare.api import AdareAPI
        api = AdareAPI()

    tools: list[ChatTool] = []

    def add(name, description, func, *, properties=None, required=None,
            serialized_vm=False, group=''):
        tools.append(ChatTool(
            name=name, description=description,
            parameters=_schema(properties, required), func=func,
            serialized_vm=serialized_vm, group=group,
        ))

    # -- projects -----------------------------------------------------------
    add('project_list', 'List all ADARE projects.',
        lambda: api.project.list_all(), group='project')

    def _project_create(name, description=''):
        from adare.core.dto.project import ProjectCreateRequest
        return api.project.create(ProjectCreateRequest(
            name=name, path=Path.cwd() / name, description=description or ''))
    add('project_create', 'Create a new project (in a subdirectory of the CWD).',
        _project_create,
        properties={'name': _str('Project name'), 'description': _str('Optional description')},
        required=['name'], group='project')

    # -- environments -------------------------------------------------------
    add('env_list', 'List all registered environments.',
        lambda: api.environment.list_all(), group='environment')

    add('env_info', 'Get details of one environment by name.',
        lambda name: api.environment.get_by_name(name),
        properties={'name': _str('Environment name')}, required=['name'], group='environment')

    def _env_load(environment, force=False, no_copy=False):
        from adare.core.dto.environment import EnvironmentLoadRequest
        return api.environment.load(EnvironmentLoadRequest(
            environment=environment, force=force, no_copy=no_copy))
    add('env_load', 'Load/register an environment from a name or descriptor path.',
        _env_load,
        properties={
            'environment': _str('Environment name or path to its YAML descriptor'),
            'force': _bool('Overwrite an existing environment of the same name'),
            'no_copy': _bool('Keep the VM disk at its original path instead of copying'),
        },
        required=['environment'], group='environment')

    add('env_list_os_profiles', 'List OS profiles available for building recipe environments.',
        lambda: api.environment.list_os_profiles(), group='environment')

    # -- experiments --------------------------------------------------------
    add('experiment_list', 'List all experiments (optionally filtered by tags).',
        lambda tags=None: api.show.list_experiments(tags=tags),
        properties={'tags': _arr('Only experiments carrying all these tags')}, group='experiment')

    add('experiment_info', 'Get details of one experiment by name.',
        lambda name: api.show.get_experiment(name=name),
        properties={'name': _str('Experiment name')}, required=['name'], group='experiment')

    def _experiment_create(name, project=None):
        from adare.core.dto.experiment import ExperimentCreateRequest
        return api.experiment.create(ExperimentCreateRequest(
            project_path=_resolve_project(project), name=name))
    add('experiment_create', 'Create a new (empty) experiment in a project.',
        _experiment_create,
        properties={'name': _str('Experiment name'), 'project': _str('Project name/path (default: CWD)')},
        required=['name'], group='experiment')

    def _experiment_add_envs(experiment, environments, project=None):
        from adare.core.dto.experiment import ExperimentEnvModifyRequest
        return api.experiment.add_environments(ExperimentEnvModifyRequest(
            project_path=_resolve_project(project),
            experiment_pattern=experiment, environments=list(environments)))
    add('experiment_add_environments', 'Attach one or more environments to an experiment.',
        _experiment_add_envs,
        properties={
            'experiment': _str('Experiment name (or glob pattern)'),
            'environments': _arr('Environment names to attach'),
            'project': _str('Project name/path (default: CWD)'),
        },
        required=['experiment', 'environments'], group='experiment')

    def _experiment_run(experiment, environment, project=None):
        import asyncio
        return asyncio.run(api.experiment.run(_resolve_project(project), experiment, environment))
    add('experiment_run',
        'Run an experiment against one of its environments (boots a VM; long-running). '
        'Returns the run result including its ULID.',
        _experiment_run,
        properties={
            'experiment': _str('Experiment name'),
            'environment': _str('Environment name to run against'),
            'project': _str('Project name/path (default: CWD)'),
        },
        required=['experiment', 'environment'], serialized_vm=True, group='experiment')

    add('experiment_validate',
        'Validate an experiment\'s configuration and integrity.',
        lambda name, environment=None, project=None: api.experiment.validate(
            _experiment_validate_request(name, environment, project)),
        properties={
            'name': _str('Experiment name'),
            'environment': _str('Restrict validation to this environment'),
            'project': _str('Project name/path (default: CWD)'),
        },
        required=['name'], group='experiment')

    # -- playbooks ----------------------------------------------------------
    # File/DB operations on an experiment's playbook.yml (never touch a VM):
    # the deterministic "fix a playbook" loop read -> edit -> validate ->
    # (devmode_execute_playbook replay) -> write. Listing is covered by
    # experiment_list / experiment_info (one playbook per experiment).
    def _playbook_read(experiment, project=None):
        from adare.core.dto.playbook import PlaybookReadRequest
        return api.experiment.read_playbook(PlaybookReadRequest(
            project_path=_resolve_project(project), experiment=experiment))
    add('playbook_read',
        "Read an experiment's playbook YAML (prefers playbook.yml on disk, "
        'falls back to the loaded DB copy). Returns {path, yaml, source}.',
        _playbook_read,
        properties={
            'experiment': _str('Experiment name'),
            'project': _str('Project name/path (default: CWD)'),
        },
        required=['experiment'], group='playbook')

    def _playbook_validate(yaml):
        from adare.core.dto.playbook import PlaybookValidateRequest
        return api.experiment.validate_playbook(PlaybookValidateRequest(yaml=yaml))
    add('playbook_validate',
        'Statically validate a playbook YAML string (parse + schema, no VM). '
        'Always succeeds with {valid, errors}; read errors to fix the YAML.',
        _playbook_validate,
        properties={'yaml': _str('Playbook YAML to validate')},
        required=['yaml'], group='playbook')

    def _playbook_write(experiment, yaml, project=None, backup=True):
        from adare.core.dto.playbook import PlaybookWriteRequest
        return api.experiment.write_playbook(PlaybookWriteRequest(
            project_path=_resolve_project(project), experiment=experiment,
            yaml=yaml, backup=backup))
    add('playbook_write',
        "Validate then write playbook YAML to an experiment's playbook.yml "
        '(optional .bak backup) and re-ingest the DB (version bump). Refuses '
        'invalid YAML (PLAYBOOK_INVALID). Returns {path, version}.',
        _playbook_write,
        properties={
            'experiment': _str('Experiment name'),
            'yaml': _str('Validated playbook YAML to write'),
            'project': _str('Project name/path (default: CWD)'),
            'backup': _bool('Back up the existing playbook.yml to .bak first (default: true)'),
        },
        required=['experiment', 'yaml'], group='playbook')

    # -- runs ---------------------------------------------------------------
    add('run_list', 'List experiment runs.',
        lambda: api.show.list_runs(), group='run')

    add('run_info', 'Get details of a run by ULID (or the latest run).',
        lambda ulid=None: api.show.get_run(ulid=ulid),
        properties={'ulid': _str('Run ULID (omit for the most recent run)')}, group='run')

    # -- test functions -----------------------------------------------------
    add('testfunction_list', 'List available test functions (assertions).',
        lambda: api.show.list_testfunctions(), group='testfunction')

    add('testfunction_info', 'Get details of one test function by dotnotation.',
        lambda dotnotation: api.show.get_testfunction(dotnotation),
        properties={'dotnotation': _str('Test function dotnotation, e.g. standard.file_exists')},
        required=['dotnotation'], group='testfunction')

    # -- VMs ----------------------------------------------------------------
    add('vm_list', 'List all registered base VMs.',
        lambda: api.vm.list_all(), group='vm')

    add('vm_list_instances', 'List VM instances (optionally for one VM).',
        lambda vm_id=None: api.vm.list_instances(vm_id=vm_id),
        properties={'vm_id': _str('Restrict to instances of this VM id')}, group='vm')

    # -- dev sessions -------------------------------------------------------
    def _session_list(project=None):
        from adare.core.dto.devmode import DevSessionListRequest
        pp = None
        if project:
            pp = _resolve_project(project)
        return api.devmode.list_sessions(DevSessionListRequest(project_path=pp))
    add('devmode_list_sessions', 'List dev-mode sessions.',
        _session_list,
        properties={'project': _str('Filter by project name/path')}, group='devmode')

    def _session_start(environment, project=None, name=None):
        from adare.core.dto.devmode import DevSessionStartRequest
        return api.devmode.start_session(DevSessionStartRequest(
            project_path=_resolve_project(project), environment_name=environment, name=name))
    add('devmode_start_session',
        'Start a dev-mode session: boot a VM for an environment for interactive driving. '
        'Returns the session id.',
        _session_start,
        properties={
            'environment': _str('Environment name to boot'),
            'project': _str('Project name/path (default: CWD)'),
            'name': _str('Optional human-friendly session label'),
        },
        required=['environment'], serialized_vm=True, group='devmode')

    def _session_stop(session_id, remove_resources=False):
        from adare.core.dto.devmode import DevSessionStopRequest
        return api.devmode.stop_session(DevSessionStopRequest(
            session_id=session_id, remove_resources=remove_resources))
    add('devmode_stop_session', 'Stop a dev-mode session (optionally removing all its resources).',
        _session_stop,
        properties={
            'session_id': _str('Session id to stop'),
            'remove_resources': _bool('Also delete VM, snapshots, and DB entries'),
        },
        required=['session_id'], group='devmode')

    def _session_playbook(session_id, playbook_yaml=None, playbook_file=None, restore_initial=False):
        from adare.core.dto.devmode import DevPlaybookExecuteRequest
        if playbook_file:
            source, content = 'file', playbook_file
        elif playbook_yaml:
            source, content = 'stdin', playbook_yaml
        else:
            raise ValueError('Provide either playbook_yaml or playbook_file')
        return api.devmode.execute_playbook(DevPlaybookExecuteRequest(
            session_id=session_id, playbook_source=source, playbook_content=content,
            restore_initial=restore_initial))
    add('devmode_execute_playbook',
        'Run a playbook (inline YAML or a file path) on a dev-mode session VM.',
        _session_playbook,
        properties={
            'session_id': _str('Target session id'),
            'playbook_yaml': _str('Inline playbook YAML'),
            'playbook_file': _str('Path to a playbook YAML file'),
            'restore_initial': _bool('Restore to the initial checkpoint before running'),
        },
        required=['session_id'], serialized_vm=True, group='devmode')

    def _author(session_id, goal, models=None, rounds=3, replay=False, os_key='linux', output_file=None):
        from adare.core.dto.devmode import DevAuthorPlaybookRequest
        return api.devmode.author_playbook(DevAuthorPlaybookRequest(
            session_id=session_id, goal=goal,
            models=list(models) if models else None,
            rounds=rounds, replay=replay, os_key=os_key,
            output_file=Path(output_file) if output_file else None))
    add('devmode_author_playbook',
        'Have a cloud vision model author a UI-action playbook for a goal from a '
        'screenshot of the session VM, validate it, and (with replay) verify it '
        'live on the VM and repair on failure. Returns the best authored YAML.',
        _author,
        properties={
            'session_id': _str('Target session id (must be running)'),
            'goal': _str('Natural-language task the playbook must accomplish'),
            'models': _arr('Ollama Cloud vision models in preference order (default: harness defaults)'),
            'rounds': _int('Max author/repair rounds per model (default 3)'),
            'replay': _bool('Verify each valid playbook live on the VM (serialized)'),
            'os_key': _str('Replay OS key / CV grounding profile (default: linux)'),
            'output_file': _str('Write the best authored playbook YAML to this path'),
        },
        required=['session_id', 'goal'], serialized_vm=True, group='devmode')

    return tools


def _experiment_validate_request(name, environment, project):
    from adare.core.dto.experiment import ExperimentValidateRequest
    return ExperimentValidateRequest(
        project_path=_resolve_project(project), name=name, environment=environment)
