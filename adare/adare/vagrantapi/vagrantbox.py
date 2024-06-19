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
import queue
import contextlib

# internal imports
from adare.vagrantapi.vagrantfile import VagrantFile
from adare.vagrantapi.exceptions import VagrantBoxCreationError, VagrantBoxRunError
from adare.vagrantapi.outputprocessor import OutputProcessor
from adare.vagrantapi.ctxmanager import VagrantCtxManager
from adarelib.config import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


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
        }

        # Iterate over output lines.
        # See http://stackoverflow.com/questions/2715847/python-read-streaming-input-from-subprocess-communicate#17698359
        with subprocess.Popen(**sp_args) as p:
            stdout = typing.cast(typing.IO, p.stdout)
            with stdout:
                yield from iter(stdout.readline, b"")
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

    def run(self, ctrlc_event: threading.Event = None, shutdown_event: threading.Event = None,
            output_processor: OutputProcessor = None, destroy_output_processor: OutputProcessor = None, ctx_manager_up: VagrantCtxManager = None, ctx_manager_destroy: VagrantCtxManager = None, disable_destroy: bool = False) -> int:
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

        ret = self.up(ctrlc_event, shutdown_event, output_processor, ctx_manager_up)

        if not disable_destroy:
            self.destroy(destroy_output_processor, ctx_manager_destroy)
        return ret

    def _close_output_processor_thread(self, thread: threading.Thread, message_queue: queue.Queue):
        log.info(f'stopping output processor thread for vagrant box {self.vm_name}')
        message_queue.put(None)
        thread.join()
        log.info(f'output processor thread for vagrant box {self.vm_name} stopped')

    def _output_processor_thread(self, message_queue: queue.Queue, output_processor: OutputProcessor):
        log.info(f'output processor thread for vagrant box {self.vm_name} started')
        while True:
            line = message_queue.get()
            if line is None:
                break
            if line.strip().rstrip() == '':
                continue
            output_processor.process(line)

    def up(self, ctrlc_event: threading.Event = None, shutdown_event: threading.Event = None,
           output_processor: OutputProcessor = None, ctx_manager_up: VagrantCtxManager = None) -> int:
        message_queue = None
        output_processor_thread = None

        self.vagrant = CustomVagrant(self.vagrantfile_path.as_posix(), quiet_stdout=False, quiet_stderr=False)

        log_file_handle = self.log_file.open('w') if self.log_file else None

        if output_processor:
            message_queue = queue.Queue()
            output_processor_thread = threading.Thread(target=self._output_processor_thread,
                                                       args=(message_queue, output_processor))
            output_processor_thread.start()

        return_value = 0
        with ctx_manager_up if ctx_manager_up else contextlib.nullcontext():
            try:
                for line in self.vagrant.up(stream_output=True):
                    if ctrlc_event and ctrlc_event.is_set():
                        log.info(f'vagrant box received a ctrl+c event')
                        if output_processor:
                            self._close_output_processor_thread(output_processor_thread, message_queue)
                            log.info(f'output processor thread for vagrant box {self.vm_name} stopped')
                        if ctx_manager_up:
                            ctx_manager_up.set_status(StatusEnum.INTERRUPTED)
                        return_value = -2
                        break
                    if shutdown_event and shutdown_event.is_set():
                        log.info(f'vagrant box received a shutdown event')
                        if output_processor:
                            self._close_output_processor_thread(output_processor_thread, message_queue)
                            log.info(f'output processor thread for vagrant box {self.vm_name} stopped')
                        return_value = -1
                        break
                    if message_queue:
                        message_queue.put(line.decode('utf-8'))
                    if self.log_file:
                        log_file_handle.write(line.decode('utf-8'))
                        log_file_handle.flush()
            except subprocess.CalledProcessError as e:
                if ctx_manager_up:
                    ctx_manager_up.set_status(StatusEnum.FAILED)
                return_value = e.returncode

        if output_processor:
            self._close_output_processor_thread(output_processor_thread, message_queue)
        if log_file_handle:
            log_file_handle.close()

        return return_value

    @retry(subprocess.CalledProcessError, tries=5, delay=1, backoff=2)
    def __destroy_box(self, message_queue: queue.Queue):
        for line in self.vagrant.destroy():
            if message_queue:
                message_queue.put(line.decode('utf-8'))

    def destroy(self, destroy_output_processor: OutputProcessor = None, ctx_manager_destroy: VagrantCtxManager = None):
        output_processor_thread = None
        message_queue = None
        if destroy_output_processor:
            message_queue = queue.Queue()
            output_processor_thread = threading.Thread(target=self._output_processor_thread,
                                                       args=(message_queue, destroy_output_processor))
            output_processor_thread.start()

        with ctx_manager_destroy if ctx_manager_destroy else contextlib.nullcontext():
            try:
                self.__destroy_box(message_queue)
            except subprocess.CalledProcessError as e:
                ctx_manager_destroy.set_status(StatusEnum.FAILED)
                return e.returncode
            finally:
                if destroy_output_processor:
                    self._close_output_processor_thread(output_processor_thread, message_queue)
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
