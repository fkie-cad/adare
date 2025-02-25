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
import contextlib

# internal imports
from adare.vagrantapi.vagrantfile import VagrantFile
from adare.vagrantapi.exceptions import VagrantBoxCreationError, VagrantBoxRunError
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

    def run(self, ctx_manager_up: VagrantCtxManager = None) -> int:
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

        log.info(f'Starting vagrant box ({self.vagrantfile_path})')
        ret = self.up(ctx_manager_up)
        if ret != 0:
            log.error(f'Vagrant Box ({self.vagrantfile_path}) failed to run')

        return ret

    def up(self, ctx_manager_up: VagrantCtxManager = None) -> int:
        self.vagrant = CustomVagrant(self.vagrantfile_path.as_posix(), quiet_stdout=False, quiet_stderr=False)

        log_file_handle = self.log_file.open('w') if self.log_file else None

        return_value = 0
        with ctx_manager_up if ctx_manager_up else contextlib.nullcontext():
            try:
                for line in self.vagrant.up(stream_output=True):
                    if log_file_handle:
                        log_file_handle.write(line.decode('utf-8'))
                        log_file_handle.flush()
            except subprocess.CalledProcessError as e:
                if ctx_manager_up:
                    ctx_manager_up.set_status(StatusEnum.FAILED)
                return_value = e.returncode

        if log_file_handle:
            log_file_handle.close()

        return return_value

    @retry(subprocess.CalledProcessError, tries=5, delay=1, backoff=2)
    def __destroy_box(self):
        with self.log_file.open('a') if self.log_file else contextlib.nullcontext() as log_file_handle:
            for line in self.vagrant.destroy():
                if log_file_handle:
                    log_file_handle.write(line.decode('utf-8'))
                    log_file_handle.flush()

    def destroy(self, ctx_manager_destroy: VagrantCtxManager = None):
        with ctx_manager_destroy if ctx_manager_destroy else contextlib.nullcontext():
            try:
                self.__destroy_box()
            except subprocess.CalledProcessError as e:
                ctx_manager_destroy.set_status(StatusEnum.FAILED)
                return e.returncode
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
