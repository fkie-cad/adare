import base64
import subprocess
import platform
import logging

log = logging.getLogger(__name__)


def run_command_in_vm(vm_name: str, command: str, guest_os: str, username: str = 'vagrant', password: str = 'vagrant',
                      background: bool = False, silent: bool = False):
    """
    Runs a command inside a VirtualBox VM using VBoxManage.

    Parameters:
        vm_name (str): Name of the virtual machine in VirtualBox.
        username (str): Guest OS username.
        password (str): Guest OS password.
        command (str): Command to run inside the guest VM.
        guest_os (str): 'windows' or 'linux'.
        background (bool): If True, runs the command in the background.
        silent (bool): If True, suppress logs.

    Returns:
        tuple: (return_code, stdout, stderr)
    """
    try:
        host_os = platform.system().lower()
        vboxmanage_exe = 'VBoxManage.exe' if host_os == 'windows' else 'VBoxManage'

        if guest_os == 'windows':
            command_exe = r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
            log.info(f"Unencoded Command Run: {command_exe} {command}")
            # Encode the command to prevent escaping issues with quotes
            command_bytes = command.encode('utf-16le')
            encoded_command = base64.b64encode(command_bytes).decode('ascii')

            if background:
                command_args = f"-NoProfile -ExecutionPolicy Bypass -Command \"Start-Process -WindowStyle Hidden -PassThru -FilePath powershell.exe -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', '{encoded_command}'\""
            else:
                command_args = f"-NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded_command}"

        else:
            # Linux: append '&' for background execution
            command_exe = "/bin/bash"
            background_addon = ''
            if background:
                background_addon = " &"
            command_args = f"-c '{command}{background_addon}'"

        # Construct the VBoxManage command
        vbox_command = [
            vboxmanage_exe, "guestcontrol", vm_name, "run",
            "--username", username,
            "--password", password,
            "--exe", command_exe,
            "--", command_exe, command_args
        ]

        if not silent:
            log.info(f"Running command: {' '.join(vbox_command)}")

        # Execute the command and capture the output
        process = subprocess.Popen(vbox_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        ret = process.returncode

        if not silent:
            log.info(
                f'Command finished with return code {ret}\nstdout: {stdout.decode("utf-8")}\nstderr: {stderr.decode("utf-8")}')

        return ret, stdout.decode('utf-8'), stderr.decode('utf-8')

    except subprocess.CalledProcessError as e:
        log.error(f"Error running command in VM: {e}")
        return None


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