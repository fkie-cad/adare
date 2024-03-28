# external imports
import threading
from pathlib import Path
from typing import Optional
import vagrant
import subprocess
from retry import retry
import os
import shutil

# internal imports
from adare.vagrantapi.vagrantfile import VagrantFile
from adare.vagrantapi.exceptions import VagrantBoxCreationError, VagrantBoxDestroyError, VagrantBoxRunError
from adarelib.exceptions import LoggedException
from adarelib.breakpoint import BreakPoint

# configure logging
import logging
log = logging.getLogger(__name__)


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

    def run(self, debug: bool = False, ctrlc_event: threading.Event = None) -> int:
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
            self.up(ctrlc_event)
        except subprocess.CalledProcessError as e:
            raise VagrantBoxRunError(
                log,
                f'vagrant up failed with return code {e.returncode}',
            ) from e
        except KeyboardInterrupt as e:
            raise LoggedException(log, 'vagrant up was interrupted by the user') from e

        if debug:
            log.info('debugmode - execution was stopped after the provisioning step and before destroying the vm')
            BreakPoint(
                'before_box_destroy',
            )
            log.info('debugmode - execution continued')

        self.destroy()
        return 0

    def up(self, ctrlc_event: threading.Event = None):
        self.should_watch = True
        self.vagrant = vagrant.Vagrant(self.vagrantfile_path.as_posix(), quiet_stdout=False, quiet_stderr=False)

        log_file_handle = self.log_file.open('w') if self.log_file else None
        for line in self.vagrant.up(stream_output=True):
            if ctrlc_event and ctrlc_event.is_set():
                self.destroy()
                raise KeyboardInterrupt('vagrant up was interrupted by the user')
            log.debug(line.rstrip())
            if self.log_file:
                log_file_handle.write(line)
                log_file_handle.flush()

        if self.log_file:
            log_file_handle.close()
        self.should_watch = False

    @retry(subprocess.CalledProcessError, tries=5, delay=1, backoff=2)
    def __destroy_box(self):
        self.vagrant.destroy()

    def destroy(self):
        self.should_watch = False
        try:
            self.__destroy_box()
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




