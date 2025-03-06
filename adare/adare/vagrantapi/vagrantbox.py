import threading
import subprocess
import select
import queue
import contextlib
import os
import shutil
from pathlib import Path
from typing import Iterator, Optional
import vagrant
from retry import retry

from adare.vagrantapi.vagrantfile import VagrantFile
from adare.vagrantapi.exceptions import VagrantBoxCreationError, VagrantBoxRunError
from adare.vagrantapi.ctxmanager import VagrantCtxManager
from adarelib.config import StatusEnum

import logging
log = logging.getLogger(__name__)


class CustomVagrant(vagrant.Vagrant):
    pid: Optional[int] = None

    def _stream_vagrant_command(self, args) -> Iterator[str]:
        """
        Execute a Vagrant command and yield output lines.
        """
        command = self._make_vagrant_command(args)
        sp_args = {
            "args": command,
            "cwd": self.root,
            "env": self.env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
        }
        with subprocess.Popen(**sp_args) as p:
            stdout = p.stdout  # type: ignore
            with stdout:
                for line in iter(stdout.readline, b""):
                    yield line
            p.wait()
            if p.returncode != 0:
                raise subprocess.CalledProcessError(p.returncode, command)

    def destroy(self, vm_name=None) -> Iterator[str]:
        """
        Destroy the Vagrant machine (using --force).
        """
        # Remove cached config for consistency
        self._cached_conf[vm_name] = None
        return self._stream_vagrant_command(["destroy", vm_name, "--force"])


class VagrantBoxVM:
    vagrant: CustomVagrant or None
    vm_name: str = 'ADARE'
    vagrantdirectory_path: Path
    log_file: Optional[Path]

    def __init__(self, vagrantdirectory_path: Path, log_file: Optional[Path] = None, vm_name: Optional[str] = None):
        self.vagrant = None
        self.log_file = log_file
        self.vagrantfile_path = vagrantdirectory_path
        if vm_name:
            self.vm_name = vm_name
        if not vagrantdirectory_path.is_dir():
            raise VagrantBoxCreationError(f'Provided path {vagrantdirectory_path} is not a directory')
        if not (vagrantdirectory_path / 'Vagrantfile').is_file():
            raise VagrantBoxCreationError(f'Provided path {vagrantdirectory_path} does not contain a Vagrantfile')
        log.info(f'Vagrant initialized in {self.vagrantfile_path.absolute()}')

    @classmethod
    def fromVagrantFileObject(cls, vagrantdirectory_path: Path, vagrantfile: VagrantFile,
                              log_file: Optional[Path] = None, vm_name: Optional[str] = None):
        log.info(f'Creating Vagrantfile in {vagrantdirectory_path.absolute()}')
        vagrantfile.create_vagrant_file(vagrantdirectory_path / 'Vagrantfile')
        return cls(vagrantdirectory_path, log_file=log_file, vm_name=vm_name)

    @classmethod
    def fromVagrantDirectory(cls, vagrantdirectory_path: Path, log_file: Optional[Path] = None,
                             vm_name: Optional[str] = None):
        return cls(vagrantdirectory_path, log_file, vm_name=vm_name)

    def run(self, ctx_manager_up: VagrantCtxManager = None, stop_event: Optional[threading.Event] = None) -> int:
        try:
            self.__clean_up_virtualbox()
        except OSError as e:
            raise VagrantBoxRunError(
                log,
                'Cleanup of leftover VirtualBox files failed',
                possible_solutions=['try to delete the files manually']
            ) from e

        log.info(f'Starting vagrant box ({self.vagrantfile_path})')
        ret = self.up(ctx_manager_up, stop_event)
        if ret != 0:
            log.error(f'Vagrant box ({self.vagrantfile_path}) failed to run')
        return ret

    def up(self, ctx_manager_up: VagrantCtxManager = None, stop_event: Optional[threading.Event] = None) -> int:
        import signal
        import os
        self.vagrant = CustomVagrant(self.vagrantfile_path.as_posix(), quiet_stdout=False, quiet_stderr=False)
        log_file_handle = self.log_file.open('w') if self.log_file else None
        return_value = 0
        line_queue = queue.Queue()

        def generator_worker():
            command = self.vagrant._make_vagrant_command(["up"])
            sp_args = {
                "args": command,
                "cwd": self.vagrant.root,
                "env": self.vagrant.env,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "preexec_fn": os.setsid  # Start the process in a new session
            }
            proc = subprocess.Popen(**sp_args)
            try:
                while True:
                    # Check for a stop event to terminate the subprocess
                    if stop_event and stop_event.is_set():
                        log.info("Stop event detected; terminating subprocess and its child processes...")
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        log.info("Subprocess and its child processes terminated")
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            log.info("Subprocess did not exit in time; killing it.")
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                            proc.wait()
                        log.info("Subprocess and its child processes killed")
                        break

                    # Use select to wait briefly for output
                    ready, _, _ = select.select([proc.stdout], [], [], 0.1)
                    if ready:
                        line = proc.stdout.readline()
                        if not line:
                            break
                        line_queue.put(line)
                    if proc.poll() is not None:
                        break
                proc.wait()
                if proc.returncode != 0:
                    raise subprocess.CalledProcessError(proc.returncode, command)
            except Exception as e:
                line_queue.put(e)
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            finally:
                # Ensure the subprocess and its child processes are terminated before exiting
                if proc.poll() is None:
                    log.info("Ensuring subprocess and its child processes are terminated before exiting...")
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        log.info("Subprocess did not exit in time; killing it.")
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        proc.wait()
                line_queue.put(None)
                log.info("Vagrant up worker finished")

        worker = threading.Thread(target=generator_worker)
        worker.start()

        with (ctx_manager_up if ctx_manager_up else contextlib.nullcontext()):
            while True:
                try:
                    item = line_queue.get(timeout=0.1)
                except queue.Empty:
                    if not worker.is_alive() and line_queue.empty():
                        break
                    continue

                if item is None:
                    # Sentinel received; exit loop.
                    break

                if isinstance(item, Exception):
                    ctx_manager_up.set_status(StatusEnum.INTERRUPTED)
                    if log_file_handle:
                        log_file_handle.close()

                    if worker.is_alive():
                        log.info('Waiting for worker to finish...')
                        worker.join()
                    log.info(f'Reraising exception: {item}')
                    break

                if log_file_handle:
                    log_file_handle.write(item.decode('utf-8'))
                    log_file_handle.flush()

        log.info('Waiting for worker to finish...')
        worker.join()
        if log_file_handle:
            log_file_handle.close()

        log.info(f'Vagrant box ({self.vagrantfile_path}) up finished')
        return return_value

    def exists(self):
        if not self.vagrant:
            return False
        return self.vagrant.status()[0].state != 'not_created'

    def status(self):
        if not self.vagrant:
            return 'not_created'
        return self.vagrant.status()[0].state

    @retry(subprocess.CalledProcessError, tries=10, delay=1, backoff=2)
    def __destroy_box(self):
        with self.log_file.open('a') if self.log_file else contextlib.nullcontext() as log_file_handle:
            for line in self.vagrant.destroy():
                if log_file_handle:
                    log_file_handle.write(line.decode('utf-8'))
                    log_file_handle.flush()

    def destroy(self, ctx_manager_destroy: VagrantCtxManager = None):
        if not self.vagrant:
            log.info(f'Vagrant box ({self.vagrantfile_path}) does not exist')
            return
        with ctx_manager_destroy if ctx_manager_destroy else contextlib.nullcontext():
            try:
                self.__destroy_box()
            except subprocess.CalledProcessError as e:
                if ctx_manager_destroy:
                    ctx_manager_destroy.set_status(StatusEnum.FAILED)
                log.debug(f'Destroying vagrant box ({self.vagrantfile_path}) failed: {e.stderr}')
                return e.returncode
        log.info(f'Vagrant box ({self.vagrantfile_path}) got destroyed successfully')

    @retry((PermissionError, OSError), delay=2, tries=5)
    def __clean_up_virtualbox(self):
        if os.name == 'nt':
            vm_dir = Path(os.path.expandvars(r"%UserProfile%\VirtualBox VMs"))
        else:
            vm_dir = Path(os.path.expandvars(r"$HOME/VirtualBox VMs"))
        if self.vm_name:
            vm_path = vm_dir / self.vm_name
            if vm_path.is_dir():
                shutil.rmtree(vm_path)
                log.info(f'Leftover files ({vm_path}) in VirtualBox have been deleted')

