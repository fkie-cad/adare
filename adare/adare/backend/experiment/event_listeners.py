"""
Event listener and flow console bootstrapping for experiment runs.

Extracted from run.py to keep the orchestrator focused on step sequencing.
"""

# configure logging
import logging
import threading

log = logging.getLogger(__name__)


def start_event_listeners(experiment_run_ulid: str):
    """Start CLI and DB event listeners plus the stage coordinator.

    Returns the two daemon threads (cli_thread, db_thread).
    Raises RuntimeError if either listener fails to start within 10 s.
    """
    from adare.backend.events.coordinator import start_stage_coordinator
    from adare.backend.events.listener import event_listener_cli, event_listener_db

    start_stage_coordinator()
    log.info("Stage event coordinator started")

    cli_ready_event = threading.Event()
    db_ready_event = threading.Event()

    def cli_wrapper():
        cli_ready_event.set()
        event_listener_cli(experiment_run_ulid)

    def db_wrapper():
        db_ready_event.set()
        event_listener_db(experiment_run_ulid)

    cli_thread = threading.Thread(target=cli_wrapper, daemon=True)
    db_thread = threading.Thread(target=db_wrapper, daemon=True)

    cli_thread.start()
    db_thread.start()

    if not cli_ready_event.wait(timeout=10.0):
        raise RuntimeError("CLI event listener failed to start within 10 seconds")
    if not db_ready_event.wait(timeout=10.0):
        raise RuntimeError("DB event listener failed to start within 10 seconds")
    log.info("Event listeners are ready")

    return cli_thread, db_thread


def create_and_start_flow_console(
    experiment_run_ulid: str,
    disable_printing: bool,
    external_stop_event: threading.Event = None,
):
    """Create (or reuse) an :class:`ExperimentFlowConsole` and start it.

    If a handler is already registered for *experiment_run_ulid* (e.g. a TUI
    widget), it is returned as-is.
    """
    from adare.backend.experiment.print import ExperimentFlowConsole, flowconsolemanager

    existing_handler = flowconsolemanager.get_handler(experiment_run_ulid)
    if existing_handler:
        log.info(f"Reusing existing flow console handler for {experiment_run_ulid}")
        return existing_handler

    flow_console = ExperimentFlowConsole(disable_printing, external_stop_event)
    flowconsolemanager.add_handler(experiment_run_ulid, flow_console)
    flow_console.start()
    return flow_console
