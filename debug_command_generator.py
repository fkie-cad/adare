
import json
import logging

# Mock the class logic
class MockC:
    def __init__(self, username):
        self.username = username
        self.guest_os = 'windows'

    def _build_guest_command_args(self, command, background=False, cwd=None, admin=False):
        if background:
            stderr_redirect = " 2>>C:\\adare\\run\\logs\\adarevmstartup.log"
            command = f"{command}{stderr_redirect}"

        path_inject_prefix = (
            f"& {{ "
            f"$sid = (New-Object System.Security.Principal.NTAccount('{self.username}')).Translate([System.Security.Principal.SecurityIdentifier]).Value; "
            f"$regPath = 'Registry::HKEY_USERS\\' + $sid + '\\Environment'; "
            f"$UserPath = (Get-ItemProperty $regPath -ErrorAction SilentlyContinue).Path; "
            f"if ($UserPath) {{ $Env:Path = $UserPath + ';' + $Env:Path }}; "
        )
        path_inject_suffix = " }"
        
        command = f"{path_inject_prefix}{command}{path_inject_suffix}"

        if admin:
             shell = ['powershell.exe', '-NoProfile', '-WindowStyle', 'Hidden', '-Command']
             command = f"{command}"
        
        return shell + [command]

mock = MockC('adare')
# The "command" from agent_command_builders.build_run_command for Windows Wheels
# "adarevm C:\adare\run\logs\adarevm.log"
# Note: In build_run_command it is:
# return (rf'adarevm {log_path}', None)  -> log_path = r'C:\adare\run\logs\adarevm.log'
# So exact string is: "adarevm C:\adare\run\logs\adarevm.log" 
# (assuming wheels, non-conda, or conda if wheels available)

# Wait, in the user log, we see:
# ... adarevm C:\adare\run\logs\adarevm.log 2>>C:\adare\run\logs\adarevmstartup.log }
# So the input command to _build_guest_command_args is "adarevm C:\adare\run\logs\adarevm.log"

cmd_input = "adarevm C:\\adare\\run\\logs\\adarevm.log"
cmd_args = mock._build_guest_command_args(cmd_input, background=True, admin=True)

qga_cmd = {
    "execute": "guest-exec",
    "arguments": {
        "path": cmd_args[0],
        "arg": cmd_args[1:],
        "capture-output": True
    }
}

print(json.dumps(qga_cmd, indent=2))
with open('debug_command.json', 'w') as f:
    json.dump(qga_cmd, f)
