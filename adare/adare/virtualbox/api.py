import base64
import subprocess
import platform
import logging
import time
import threading
from typing import Optional

log = logging.getLogger(__name__)


def run_command_in_vm(vm_name: str, command: str, guest_os: str, username: str = 'vagrant',
                      password: str = 'vagrant', background: bool = False, silent: bool = False,
                      stop_event: Optional[threading.Event] = None):
    """
    Runs a command inside a VirtualBox VM using VBoxManage.
    If stop_event is provided and is set, the subprocess is forcefully killed.
    """
    import subprocess, platform, base64
    try:
        host_os = platform.system().lower()
        vboxmanage_exe = 'VBoxManage.exe' if host_os == 'windows' else 'VBoxManage'

        if guest_os == 'windows':
            command_exe = r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
            log.info(f"Unencoded Command Run: {command_exe} {command}")
            command_bytes = command.encode('utf-16le')
            encoded_command = base64.b64encode(command_bytes).decode('ascii')
            if background:
                command_args = f"-NoProfile -ExecutionPolicy Bypass -Command \"Start-Process -WindowStyle Hidden -PassThru -FilePath powershell.exe -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', '{encoded_command}'\""
            else:
                command_args = f"-NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded_command}"
        else:
            command_exe = "/bin/bash"
            background_addon = " &" if background else ""
            command_args = f"-c '{command}{background_addon}'"

        vbox_command = [
            vboxmanage_exe, "guestcontrol", vm_name, "run",
            "--username", username,
            "--password", password,
            "--exe", command_exe,
            "--", command_exe, command_args
        ]

        if not silent:
            log.info(f"Running command: {' '.join(vbox_command)}")

        process = subprocess.Popen(vbox_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Instead of a blocking communicate(), loop and check for cancellation.
        stdout_chunks = []
        stderr_chunks = []
        while process.poll() is None:
            # If a stop event is provided and has been set, kill the process.
            if stop_event and stop_event.is_set():
                log.info("Stop event detected; forcefully terminating subprocess.")
                process.kill()
                break
            # Non-blocking read could be implemented here; for simplicity, wait a short interval.
            time.sleep(0.1)

        # Now read any remaining output.
        stdout, stderr = process.communicate()
        stdout_chunks.append(stdout)
        stderr_chunks.append(stderr)
        ret = process.returncode

        if not silent:
            log.info(
                f'Command finished with return code {ret}\nstdout: {b"".join(stdout_chunks).decode("utf-8")}\nstderr: {b"".join(stderr_chunks).decode("utf-8")}')
        return ret, b"".join(stdout_chunks).decode('utf-8'), b"".join(stderr_chunks).decode('utf-8')

    except subprocess.CalledProcessError as e:
        log.error(f"Error running command in VM: {e}")
        return None, None, None


def vm_is_fully_booted(vm_name: str, guest_os: str, silent: bool = False):
    """
    Checks if a VirtualBox VM is fully booted by running a simple command.

    Parameters:
        vm_name (str): Name of the virtual machine in VirtualBox.
        guest_os (str): 'windows', 'linux'

    Returns:
        bool: True if the VM is fully booted, False otherwise.
    """
    command = "echo Fully booted"

    try:
        # Run the command in the VM
        ret, _, _ = run_command_in_vm(vm_name, command, guest_os, silent=silent)
        return ret == 0
    except subprocess.CalledProcessError as e:
        return False


def wait_until_vm_is_fully_booted(vm_name: str, guest_os: str, timeout: int = 360):
    """
    Waits until a VirtualBox VM is fully booted.

    Parameters:
        vm_name (str): Name of the virtual machine in VirtualBox.
        guest_os (str): 'windows', 'linux'
        timeout (int): Maximum time to wait for the VM to boot.

    Returns:
        bool: True if the VM is fully booted, False otherwise.
    """
    import time
    log.info(f"Waiting for VM {vm_name} to boot...")
    time_slept = 0
    while not vm_is_fully_booted(vm_name, guest_os, silent=True):
        if time_slept > timeout:
            log.error(f"VM {vm_name} did not boot within {timeout} seconds")
            return False
        if time_slept % 30 == 0 and time_slept != 0:
            log.info(f"Waiting for VM {vm_name} to boot... {time_slept} seconds")
        time.sleep(2)
        time_slept += 2
    log.info(f"VM {vm_name} is fully booted")
    return True