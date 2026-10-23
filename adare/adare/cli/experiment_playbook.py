"""`adare experiment playbook show|validate|set` implementations.

Split out of ``cli/experiment.py`` to keep that module under the project's
1000-line ceiling.
"""

import logging

from adare.api import AdareAPI
from adare.cli.output import emit, is_machine_output
from adare.cli.utils import get_project_path, handle_api_error
from adare.console import print_error_message, print_success_message
from adare.helperfunctions.output_formatter import RawText
from adare.helperfunctions.path_resolution import resolve_experiment_path

log = logging.getLogger(__name__)


def exec_playbook_show(arguments):
    """Print an experiment's playbook YAML (disk, DB fallback)."""
    from adare.core.dto.playbook import PlaybookReadRequest

    project_directory = get_project_path(arguments)
    experiment_name = resolve_experiment_path(arguments.experiment, project_directory)

    api = AdareAPI()
    result = api.experiment.read_playbook(
        PlaybookReadRequest(
            project_path=project_directory,
            experiment=experiment_name,
        )
    )

    if not result.success:
        handle_api_error(result)
        return

    log.info('Playbook source: %s (%s)', result.data.path, result.data.source)
    if is_machine_output():
        # json/yaml: wrap the document so a parser gets the provenance too.
        emit(
            {
                'experiment': experiment_name,
                'path': result.data.path,
                'source': result.data.source,
                'yaml': RawText(result.data.yaml),  # verbatim, not markup-stripped
            }
        )
        return
    # rich/plain: the playbook YAML itself is the data.
    print(result.data.yaml)


def exec_playbook_validate(arguments):
    """Statically validate a playbook YAML file (no VM)."""
    import sys
    from pathlib import Path

    from adare.core.dto.playbook import PlaybookValidateRequest

    playbook_path = Path(arguments.file)
    try:
        yaml_content = playbook_path.read_text(encoding='utf-8')
    except OSError as e:
        print_error_message(title=f'Cannot read {playbook_path}: {e}')
        sys.exit(1)

    api = AdareAPI()
    result = api.experiment.validate_playbook(PlaybookValidateRequest(yaml=yaml_content))

    if not result.success:
        handle_api_error(result)
        return

    for warning in result.data.warnings:
        print(f'warning: {warning}', file=sys.stderr)
    if result.data.valid:
        print_success_message(
            title=f'Playbook "{playbook_path}" is valid'
            + (f' ({len(result.data.warnings)} warning(s))' if result.data.warnings else '')
        )
    else:
        print_error_message(
            title=f'Playbook "{playbook_path}" is invalid',
            next_steps=result.data.errors,
        )
        sys.exit(1)


def exec_playbook_set(arguments):
    """Validate then write a playbook YAML file to an experiment (DB re-ingest)."""
    import sys
    from pathlib import Path

    from adare.core.dto.playbook import PlaybookWriteRequest

    project_directory = get_project_path(arguments)
    experiment_name = resolve_experiment_path(arguments.experiment, project_directory)

    source_path = Path(arguments.file)
    try:
        yaml_content = source_path.read_text(encoding='utf-8')
    except OSError as e:
        print_error_message(title=f'Cannot read {source_path}: {e}')
        sys.exit(1)

    api = AdareAPI()
    result = api.experiment.write_playbook(
        PlaybookWriteRequest(
            project_path=project_directory,
            experiment=experiment_name,
            yaml=yaml_content,
            backup=arguments.backup,
        )
    )

    if not result.success:
        handle_api_error(result)
        return

    next_steps = []
    if result.data.backup_path:
        next_steps.append(f'Previous playbook backed up to {result.data.backup_path}')
    if result.data.db_ingested:
        next_steps.append(f'Database re-ingested (playbook version {result.data.version})')
    else:
        next_steps.append(
            f'Experiment not loaded in DB — file written only; run `adare experiment load {experiment_name}` to ingest'
        )
    print_success_message(
        title=f'Playbook written to {result.data.path}',
        next_steps=next_steps,
    )
