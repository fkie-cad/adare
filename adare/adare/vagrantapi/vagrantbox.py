# external imports
import threading
from pathlib import Path
from typing import Iterator, Optional
import typing
import vagrant
import subprocess
from retry import retry
import os
import shutil
import re

# internal imports
from adare.vagrantapi.vagrantfile import VagrantFile
from adare.vagrantapi.exceptions import VagrantBoxCreationError, VagrantBoxDestroyError, VagrantBoxRunError
from adarelib.exceptions import LoggedException
from adarelib.types.experiment import Stage
from adare.database.api.stage import StageDbApi

# configure logging
import logging
log = logging.getLogger(__name__)


class VagrantOutputProcessor:
    experiment_run_uuid: str
    machine: str
    provider: str

    # pattern to match the header which contains the machine and provider
    # e.g. Bringing machine 'X' up with 'Y' provider...
    header_pattern = re.compile(r"Bringing machine '(?P<machine>.+)' up with '(?P<provider>.+)' provider\.\.\.")
    vagrant_message_pattern = re.compile(r"==> (?P<machine>.+): (?P<message>.+)")
    submessage_pattern = re.compile(r" {4}(?P<machine>.+): (?P<message>.+)")

    stage_message_pattern = re.compile(r"stage (?P<stage>.+): (?P<message>.+) \((?P<timestamp>.+)\)")

    def __init__(self, experiment_run_uuid: str):
        self.experiment_run_uuid = experiment_run_uuid
        self.machine = ''
        self.provider = ''

    def process(self, line: str):
        if match := self.header_pattern.match(line):
            self.machine = match.group('machine')
            self.provider = match.group('provider')
        elif match := self.vagrant_message_pattern.match(line):
            # these are vagrant log messages sent by vagrant
            if match:
                message = match.group('message')
                log.debug(message)
        elif match := self.submessage_pattern.match(line):
            # these are messages within a provisioner, ...
            if match:
                message = match.group('message')
                if match := self.stage_message_pattern.match(message):
                    stage = match.group('stage')
                    message = match.group('message')
                    timestamp = match.group('timestamp')
                    if message not in ['start', 'end']:
                        log.warning(f'so far only start and end messages are supported for stages')
                    stage_data = {
                        'name': stage,
                    }
                    if message == 'start':
                        stage_data['start_time'] = timestamp
                    if message == 'end':
                        stage_data['end_time'] = timestamp
                    stage = Stage.from_data(stage_data)
                    with StageDbApi() as api:
                        api.update_stage_in_run(stage, self.experiment_run_uuid)
                else:
                    log.debug(message)


class CustomVagrant(vagrant.Vagrant):

    def _stream_vagrant_command(self, args) -> Iterator[str]:
        """
        Execute a vagrant command, returning a generator of the output lines.
        Caller should consume the entire generator to avoid the hanging the
        subprocess.

        :param args: Arguments for the Vagrant command.
        :return: generator that yields each line of the command stdout.
        :rtype: generator iterator
        """
        # Make subprocess command
        command = self._make_vagrant_command(args)
        sp_args = {
            "args": command,
            "cwd": self.root,
            "env": self.env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "bufsize": 1,  # line-buffered,
            "universal_newlines": True,
            "start_new_session": True,
        }

        # Iterate over output lines.
        # See http://stackoverflow.com/questions/2715847/python-read-streaming-input-from-subprocess-communicate#17698359
        with subprocess.Popen(**sp_args) as p:
            stdout = typing.cast(typing.IO, p.stdout)
            with stdout:
                for line in iter(stdout.readline, b""):
                    yield line
            p.wait()
            # Raise CalledProcessError for consistency with _call_vagrant_command
            if p.returncode != 0:
                raise subprocess.CalledProcessError(p.returncode, command)

    def destroy(self, vm_name=None) -> Iterator[str]:
        """
        Terminate the running Vagrant box.
        """
        generator = self._stream_vagrant_command(["destroy", vm_name, "--force"])
        self._cached_conf[vm_name] = None  # remove cached configuration
        return generator


class VagrantBoxVM:
    """
    class that provides an api controlling a vagrant box (and multi machine feature). therefore commands like run and destroy are supported
    """

    vagrant: vagrant.Vagrant
    vm_name: str = 'ADARE'
    vagrantdirectory_path: Path
    should_watch: bool = False

    log_file: Optional[Path]

    def __init__(self, vagrantdirectory_path: Path, log_file: Optional[Path] = None, vm_name: Optional[str] = None):
        self.log_file = log_file
        self.vagrantfile_path = vagrantdirectory_path

        if vm_name:
            self.vm_name = vm_name

        if not vagrantdirectory_path.is_dir():
            raise VagrantBoxCreationError(f'provided path {vagrantdirectory_path} is not a directory')

        if not (vagrantdirectory_path / 'Vagrantfile').is_file():
            raise VagrantBoxCreationError(f'provided path {vagrantdirectory_path} does not contain a Vagrantfile')

        log.info(f'vagrant initialized in {self.vagrantfile_path.absolute()} directory')

    @classmethod
    def fromVagrantFileObject(cls, vagrantdirectory_path: Path, vagrantfile: VagrantFile,
                              log_file: Optional[Path] = None, vm_name: Optional[str] = None):
        """
        create a VagrantBox instance by a provided Vagrantfile object instance and a directory where the Vagrantfile will be stored
        """
        log.info(f'provided Vagrantfile will be saved in in the provided directory {vagrantdirectory_path.absolute()}')
        vagrantfile.create_vagrant_file(vagrantdirectory_path / 'Vagrantfile')
        return cls(vagrantdirectory_path, log_file=log_file, vm_name=vm_name)

    @classmethod
    def fromVagrantDirectory(cls, vagrantdirectory_path: Path, log_file: Optional[Path] = None,
                             vm_name: Optional[str] = None):
        """
        create a VagrantBox instance by a provided directory that contains a Vagrantfile
        """
        return cls(vagrantdirectory_path, log_file, vm_name=vm_name)

    def run(self, ctrlc_event: threading.Event = None, output_processor: VagrantOutputProcessor = None) -> int:
        try:
            self.__clean_up_virtualbox()
        except OSError as e:
            raise VagrantBoxRunError(
                log,
                'clean up of left over files in VirtualBox failed due to the exception above',
                possible_solutions=[
                    'try to delete the files manually',
                ],
            ) from e

        try:
            self.up(ctrlc_event, output_processor)
        except subprocess.CalledProcessError as e:
            raise VagrantBoxRunError(
                log,
                f'vagrant up failed with return code {e.returncode}',
            ) from e
        except KeyboardInterrupt as e:
            #raise LoggedException(log, 'vagrant up was interrupted by the user') from e
            return 1

        self.destroy(output_processor)
        return 0

    def up(self, ctrlc_event: threading.Event = None, output_processor: VagrantOutputProcessor = None):
        self.should_watch = True
        self.vagrant = CustomVagrant(self.vagrantfile_path.as_posix(), quiet_stdout=False, quiet_stderr=False)

        log_file_handle = self.log_file.open('w') if self.log_file else None
        for line in self.vagrant.up(stream_output=True):
            if ctrlc_event and ctrlc_event.is_set():
                self.destroy(output_processor)
                raise KeyboardInterrupt('vagrant up was interrupted by the user')
            if output_processor:
                output_processor.process(line)
            if self.log_file:
                log_file_handle.write(line)
                log_file_handle.flush()

        if self.log_file:
            log_file_handle.close()
        self.should_watch = False

    @retry(subprocess.CalledProcessError, tries=5, delay=1, backoff=2)
    def __destroy_box(self, output_processor: VagrantOutputProcessor = None):
        for line in self.vagrant.destroy():
            if output_processor:
                output_processor.process(line)

    def destroy(self, output_processor: VagrantOutputProcessor = None):
        self.should_watch = False
        try:
            self.__destroy_box(output_processor)
        except subprocess.CalledProcessError as e:
            raise VagrantBoxDestroyError(
                log,
                'vagrant destroy failed with return code {e.returncode}',
                possible_solutions=[
                    'try to delete the VM manually',
                ],
            ) from e
        log.info(f'vagrant box ({self.vagrantfile_path}) got destroyed successfully')

    @retry((PermissionError, OSError), delay=2, tries=5)
    def __clean_up_virtualbox(self):
        # check if host is windows
        if os.name == 'nt':
            vm_dir = Path(os.path.expandvars(r"%UserProfile%\VirtualBox VMs"))
        else:
            vm_dir = Path(os.path.expandvars(r"$HOME/VirtualBox VMs"))

        if self.vm_name:
            vm_path = vm_dir / self.vm_name
            if vm_path.is_dir():
                shutil.rmtree(vm_path)
                log.info(f'left over files ({vm_path}) in VirtualBox got deleted')




