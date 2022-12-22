# external imports
from pathlib import Path
from typing import Optional
import vagrant
import subprocess
from retry import retry

# internal imports
from .vagrantfile import VagrantFile
from .exceptions import VagrantBoxCreationError, VagrantBoxDestroyError

# configure logging
import logging
log = logging.getLogger(__name__)


class VagrantBoxVM:
    """
    class that provides an api controlling a vagrant box (and multi machine feature). therefore commands like run and destroy are supported
    """

    vagrant: vagrant.Vagrant
    vagrantdirectory_path: Path

    # vm_name: Optional[str]

    log_file: Optional[Path]

    def __init__(self, vagrantdirectory_path: Path, log_file: Optional[Path] = None, vm_name: str = 'adarebox'):
        # self.vm_name = vm_name
        self.log_file = log_file
        self.vagrantfile_path = vagrantdirectory_path

        if not vagrantdirectory_path.is_dir():
            raise VagrantBoxCreationError(f'provided path {vagrantdirectory_path} is not a directory')

        if not (vagrantdirectory_path/'Vagrantfile').is_file():
            raise VagrantBoxCreationError(f'provided path {vagrantdirectory_path} does not contain a Vagrantfile')

        self.vagrant = vagrant.Vagrant(root=self.vagrantfile_path.as_posix())
        log.info(f'vagrant initialized in {self.vagrantfile_path.absolute()} directory')

    @classmethod
    def fromVagrantFileObject(cls, vagrantdirectory_path: Path, vagrantfile: VagrantFile, log_file: Optional[Path] = None):
        """
        create a VagrantBox instance by a provided Vagrantfile object instance and a directory where the Vagrantfile will be stored
        """
        log.info(f'provided Vagrantfile will be saved in in the provided directory {vagrantdirectory_path.absolute()}')
        vagrantfile.create_vagrant_file(vagrantdirectory_path/'Vagrantfile')
        return cls(vagrantdirectory_path, log_file=log_file)

    @classmethod
    def fromVagrantDirectory(cls, vagrantdirectory_path: Path, log_file: Optional[Path] = None):
        """
        create a VagrantBox instance by a provided directory that contains a Vagrantfile
        """
        return cls(vagrantdirectory_path, log_file)

    def run(self, debug: bool = False):
        try:
            self.up()
        except subprocess.CalledProcessError as e:
            log.debug(e, exc_info=True)
            log.error(f'vagrant up exited with returncode {e.returncode}')
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

    def up(self):
        if self.log_file:
            with open(self.log_file.as_posix(), mode='w') as lf:
                for output_line in self.vagrant.up(stream_output=True):
                    log.debug(output_line[:-1])
                    lf.write(output_line[:-1])
        else:
            for output_line in self.vagrant.up(stream_output=True):
                log.debug(output_line)

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


    # @retry((PermissionError, OSError), delay=2, tries=5)
    # def __clean_up_virtualbox(self):
    #     vm_dir = Path(os.path.expandvars(r"%UserProfile%\VirtualBox VMs"))
    #     vbox_name = self.vagrantfile.get_vbox_name()
    #     if vbox_name:
    #         vm_path = vm_dir / vbox_name
    #         if vm_path.is_dir():
    #             shutil.rmtree(vm_path)
    #             log.info(f'left over files ({vm_path}) in VirtualBox got deleted')
