import base64

def construct_command(tag, mount_point):
    virtiofs_exe = r'C:\Program Files\Virtio-Win\VioFS\virtiofs.exe'
    # Redirect stdout and stderr to a file we can read
    mount_cmd = f'& "{virtiofs_exe}" -t {tag} -m {mount_point} > C:\\adare\\mount_debug.log 2>&1'
    return mount_cmd

def wrap_in_schtasks(command, user="adare", pwd="adare"):
    task_name = "mount_run"
    user_safe = user.replace("'", "''")
    pwd_safe = pwd.replace("'", "''")
    
    encoded_cmd = base64.b64encode(command.encode('utf-16-le')).decode('utf-8')

    final_command = (
        f"& {{ "
        f"$u = '{user_safe}'; $p = '{pwd_safe}'; $t = '{task_name}'; "
        f"$enc = '{encoded_cmd}'; "
        # We call powershell with -EncodedCommand instead of -Command
        f"$c = 'powershell.exe -NoProfile -WindowStyle Hidden -EncodedCommand {encoded_cmd}'; "
        f"schtasks /Create /TN $t /TR \"$c\" /SC ONCE /ST 00:00 /SD 01/01/1910 /RU $u /RP $p /RL LIMITED /F; "
        f"schtasks /Run /TN $t; "
        f"Start-Sleep -Seconds 2; "
        f"$info = schtasks /Query /TN $t /V /FO CSV | ConvertFrom-Csv; "
        f"Write-Host \"Task_Status: $($info.Status)\"; "
        f"Write-Host \"Exit_Code: $($info.'Last Run Result')\"; "
        f"schtasks /Delete /TN $t /F; "
        f"}} "
    )
    return final_command

tag = "run"
mount_point = r"C:\adare\run"
cmd = construct_command(tag, mount_point)
print(f"Original Command: {cmd}")
wrapped = wrap_in_schtasks(cmd)
# print(f"Wrapped Command: {wrapped}")

# Generate virsh command
import json
# guest-exec takes path and arg list
# The command is: powershell.exe -Command "WRAPPED_COMMAND"
# We need to be careful with quotes in JSON
args = ["-Command", wrapped]
cmd_json = {
    "execute": "guest-exec",
    "arguments": {
        "path": "powershell.exe",
        "arg": args,
        "capture-output": True
    }
}
json_str = json.dumps(cmd_json)
import subprocess
import time
import sys

# ... previous code ...

# Execute virsh command
print(f"\nExecuting via virsh...")
try:
    result = subprocess.run(
        ["virsh", "-c", "qemu:///system", "qemu-agent-command", "Windows11Qemu_exp_01KF3FM6", json_str],
        capture_output=True, text=True, check=True
    )
    print(f"Start Result: {result.stdout}")
    response = json.loads(result.stdout)
    pid = response["return"]["pid"]
    print(f"Command started with PID: {pid}")

    # Poll status
    status_cmd = {"execute": "guest-exec-status", "arguments": {"pid": pid}}
    status_json = json.dumps(status_cmd)
    
    for i in range(10):
        time.sleep(2) # increased sleep
        res = subprocess.run(
            ["virsh", "-c", "qemu:///system", "qemu-agent-command", "Windows11Qemu_exp_01KF3FM6", status_json],
            capture_output=True, text=True, check=True
        )
        status_resp = json.loads(res.stdout)
        exited = status_resp["return"]["exited"]
        if exited:
            print(f"Command exited.")
            print(f"Exit Code: {status_resp['return'].get('exitcode')}")
            
            # Now read the log file
            print("\nReading debug log C:\\adare\\mount_debug.log...")
            read_cmd = {"execute": "guest-exec", "arguments": {"path": "cmd", "arg": ["/c", "type", "C:\\adare\\mount_debug.log"], "capture-output": True}}
            read_json = json.dumps(read_cmd)
            
            res_read = subprocess.run(
                ["virsh", "-c", "qemu:///system", "qemu-agent-command", "Windows11Qemu_exp_01KF3FM6", read_json],
                capture_output=True, text=True, check=True
            )
            read_resp = json.loads(res_read.stdout)
            pid_read = read_resp["return"]["pid"]
            
            # verify mount
            print("\nVerifying mount C:\\adare\\run ...")
            verify_cmd = {"execute": "guest-exec", "arguments": {"path": "powershell", "arg": ["-Command", "Get-ChildItem C:\\adare\\run"], "capture-output": True}}
            verify_json = json.dumps(verify_cmd)
            res_verify = subprocess.run(
                 ["virsh", "-c", "qemu:///system", "qemu-agent-command", "Windows11Qemu_exp_01KF3FM6", verify_json],
                 capture_output=True, text=True, check=True
            )
            pid_verify = json.loads(res_verify.stdout)["return"]["pid"]

            # Wait for read
            time.sleep(1)
            status_read_cmd = {"execute": "guest-exec-status", "arguments": {"pid": pid_read}}
            res_status_read = subprocess.run(
                ["virsh", "-c", "qemu:///system", "qemu-agent-command", "Windows11Qemu_exp_01KF3FM6", json.dumps(status_read_cmd)],
                capture_output=True, text=True, check=True
            )
            status_read = json.loads(res_status_read.stdout)
            if "out-data" in status_read["return"]:
                print(f"Log content:\n{base64.b64decode(status_read['return']['out-data']).decode('utf-8', errors='replace')}")
            else:
                print("Log content is empty or file not found.")

             # Wait for verify
            time.sleep(1)
            status_verify_cmd = {"execute": "guest-exec-status", "arguments": {"pid": pid_verify}}
            res_status_verify = subprocess.run(
                ["virsh", "-c", "qemu:///system", "qemu-agent-command", "Windows11Qemu_exp_01KF3FM6", json.dumps(status_verify_cmd)],
                capture_output=True, text=True, check=True
            )
            status_verify = json.loads(res_status_verify.stdout)
            if "out-data" in status_verify["return"]:
                 print(f"Mount verification stdout:\n{base64.b64decode(status_verify['return']['out-data']).decode('utf-8', errors='replace')}")
            if "err-data" in status_verify["return"]:
                 print(f"Mount verification stderr:\n{base64.b64decode(status_verify['return']['err-data']).decode('utf-8', errors='replace')}")

            break
            
except subprocess.CalledProcessError as e:
    print(f"Error executing virsh: {e}")
    print(f"Stderr: {e.stderr}")
