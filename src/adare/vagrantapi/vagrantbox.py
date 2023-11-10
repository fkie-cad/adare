# external imports
from pathlib import Path
from typing import Optional
import vagrant
import subprocess
from retry import retry
import os
import shutil

# internal imports
from .vagrantfile import VagrantFile
from .exceptions import VagrantBoxCreationError, VagrantBoxDestroyError, VagrantBoxRunError

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

    log_file: Optional[Path]

    def __init__(self, vagrantdirectory_path: Path, log_file: Optional[Path] = None, vm_name: Optional[str] = None):
        self.log_file = log_file
        self.vagrantfile_path = vagrantdirectory_path

        if vm_name:
            self.vm_name = vm_name

        if not vagrantdirectory_path.is_dir():
            raise VagrantBoxCreationError(f'provided path {vagrantdirectory_path} is not a directory')

        if not (vagrantdirectory_path/'Vagrantfile').is_file():
            raise VagrantBoxCreationError(f'provided path {vagrantdirectory_path} does not contain a Vagrantfile')

        log.info(f'vagrant initialized in {self.vagrantfile_path.absolute()} directory')

    @classmethod
    def fromVagrantFileObject(cls, vagrantdirectory_path: Path, vagrantfile: VagrantFile, log_file: Optional[Path] = None, vm_name: Optional[str] = None):
        """
        create a VagrantBox instance by a provided Vagrantfile object instance and a directory where the Vagrantfile will be stored
        """
        log.info(f'provided Vagrantfile will be saved in in the provided directory {vagrantdirectory_path.absolute()}')
        vagrantfile.create_vagrant_file(vagrantdirectory_path/'Vagrantfile')
        return cls(vagrantdirectory_path, log_file=log_file, vm_name=vm_name)

    @classmethod
    def fromVagrantDirectory(cls, vagrantdirectory_path: Path, log_file: Optional[Path] = None, vm_name: Optional[str] = None):
        """
        create a VagrantBox instance by a provided directory that contains a Vagrantfile
        """
        return cls(vagrantdirectory_path, log_file, vm_name=vm_name)

    def run(self, debug: bool = False) -> int:
        try:
            self.__clean_up_virtualbox()
        except (PermissionError, OSError) as e:
            log.error(e, exc_info=True)
            log.warning('clean up of virtualbox failed -> try to delete the VM manually!')
            raise VagrantBoxRunError()
        
        return_code = 0
        try:
            self.up()
        except subprocess.CalledProcessError as e:
            log.debug(e, exc_info=True)
            return_code = e.returncode
            log.error(f'vagrant up exited with returncode {return_code} -> log in {self.log_file} for more details')
        except KeyboardInterrupt as e:
            log.debug(e, exc_info=True)
            log.error(f'vagrant up interrupted by KeyboardInterrupt')

        if debug:
            log.info('debugmode - execution was stopped after the provisioning step and before destroying the vm')
            answer = ''
            while answer not in ['y', 'Y', 'Yes', 'YES']:
                answer = input('\ndebugmode: to continue press y/Y: ')
            log.info('debugmode - execution continued')

        self.destroy()
        return return_code

    def up(self):
        self.vagrant = vagrant.Vagrant(self.vagrantfile_path.as_posix(), quiet_stdout=False, quiet_stderr=False)

        log_file_handle = None
        if self.log_file:
            log_file_handle = self.log_file.open('w')

        for line in self.vagrant.up(stream_output=True, vm_name=self.vm_name):
            log.debug(line.rstrip())
            if self.log_file:
                log_file_handle.write(line)
                log_file_handle.flush()

        if self.log_file:
            log_file_handle.close()



    @retry(subprocess.CalledProcessError, tries=5, delay=1, backoff=2)
    def __destroy_box(self):
        self.vagrant.destroy()

    def destroy(self):
        try:
            self.__destroy_box()
        except subprocess.CalledProcessError as e:
            log.error(e, exc_info=True)
            log.fatal('destroy failed due to the exception above -> try to delete the VM manually!')
            raise VagrantBoxDestroyError()
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
