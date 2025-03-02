import attrs
from datetime import datetime
from pathlib import Path
import threading
from adare.vagrantapi.vagrantbox import VagrantBoxVM
from adare.backend.project.directory import ProjectDirectory
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
from adare.vagrantapi.vagrantfile import VagrantFile
from adare.backend.wsclient.client import WebSocketClient

@attrs.define
class ExperimentRunCtx:
    project_path: Path
    experiment_name: str
    environment_name: str
    experiment_run_ulid: str = attrs.field(default=None)
    client: WebSocketClient = attrs.field(default=None)
    box: VagrantBoxVM = attrs.field(default=None)
    project_directory: ProjectDirectory = attrs.field(default=None)
    experiment_directory: ExperimentDirectory = attrs.field(default=None)
    environment_file: Path = attrs.field(default=None)
    environment_ulid: str = attrs.field(default=None)
    guest_platform: str = attrs.field(default=None)
    experiment_run_directory: ExperimentRunDirectory = attrs.field(default=None)
    vm_name: str = attrs.field(default=None)
    timestamp_start: datetime = attrs.field(default=None)
    timestamp_before_box_start: datetime = attrs.field(default=None)
    timestamp_end: datetime = attrs.field(default=None)
    vagrantbox_download_required: bool = attrs.field(default=None)
    vagrantfile: VagrantFile = attrs.field(default=None)
    stop_event: threading.Event = attrs.field(default=threading.Event())
    lock: threading.Lock = attrs.field(default=threading.Lock())