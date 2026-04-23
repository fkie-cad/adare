"""
CLI command handlers for dev mode recording.

Provides exec_* functions for:
- Session recording (capture user interactions to playbook)
"""

import logging
import time
from pathlib import Path

from adare.api import AdareAPI
from adare.cli.dev._helpers import _resolve_session_id
from adare.cli.utils import get_project_path, handle_api_error
from adare.console import print_error_message, print_success_message
from adare.core.dto.devmode import DevSessionRecordRequest

log = logging.getLogger(__name__)


def exec_dev_record(arguments):
    """
    Record user interactions in a dev session.

    Args:
        arguments: Parsed arguments
    """
    project_directory = get_project_path(arguments)
    session_id = _resolve_session_id(getattr(arguments, 'session_id', None), project_directory)
    output_file = Path(getattr(arguments, 'output', 'playbook.yml')).resolve()

    log.info(f"Recording session {session_id} to {output_file}")
    print(f"Starting recording for session {session_id}...")
    print(f"Output will be saved to: {output_file}")
    print("Press Ctrl+C to stop recording.")

    api = AdareAPI()

    try:
        # Start recording
        result = api.devmode.record_session(DevSessionRecordRequest(
            session_id=session_id,
            output_file=output_file
        ))

        if not result.success:
            handle_api_error(result)

        # Loop until interrupted
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nStopping recording...")

            # Stop recording
            stop_result = api.devmode.stop_recording_session(session_id)
            if stop_result.success:
                print_success_message(
                    title="Recording stopped",
                    next_steps=[f"View playbook: {output_file}"],
                    tip=f"Run with: adare dev playbook {session_id} -f {output_file}"
                )
            else:
                handle_api_error(stop_result)

    except Exception as e:
        print_error_message(title="Recording failed", next_steps=[str(e)])
        exit(1)
