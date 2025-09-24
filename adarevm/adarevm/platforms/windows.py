def get_windows_by_search_string(search_string: str):
    raise NotImplementedError("Windows GUI automation not implemented")


def get_os_info():
    """Get Windows OS information."""
    import subprocess

    info = {}

    try:
        # Use systeminfo command for basic info
        result = subprocess.run(['systeminfo'], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            info.update(_parse_systeminfo(result.stdout))

        # Try PowerShell for more detailed info
        ps_cmd = 'powershell -Command "Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, WindowsBuildLabEx | ConvertTo-Json"'
        result = subprocess.run(ps_cmd, capture_output=True, text=True, shell=True, timeout=20)
        if result.returncode == 0:
            try:
                import json
                computer_info = json.loads(result.stdout)
                if computer_info.get('WindowsProductName'):
                    info['name'] = computer_info['WindowsProductName']
                if computer_info.get('WindowsVersion'):
                    info['version'] = computer_info['WindowsVersion']
                if computer_info.get('WindowsBuildLabEx'):
                    info['build'] = computer_info['WindowsBuildLabEx']
            except (json.JSONDecodeError, Exception):
                pass  # Fallback to systeminfo data

    except Exception as e:
        # Basic fallback
        import platform
        info['name'] = platform.system()
        info['version'] = platform.release()
        info['architecture'] = platform.machine()

    return info


def get_installed_programs():
    """Get list of installed programs from Windows registry."""
    import subprocess

    programs = []

    try:
        # Query registry for installed programs
        reg_cmd = r'reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" /s /f "DisplayName" /t REG_SZ'
        result = subprocess.run(reg_cmd, capture_output=True, text=True, shell=True, timeout=60)

        if result.returncode == 0:
            programs = _parse_registry_programs(result.stdout)

    except Exception as e:
        # Fallback to PowerShell WMI query (slower but more reliable)
        try:
            ps_cmd = 'powershell -Command "Get-WmiObject -Class Win32_Product | Select-Object Name, Version | ConvertTo-Json"'
            result = subprocess.run(ps_cmd, capture_output=True, text=True, shell=True, timeout=120)

            if result.returncode == 0:
                try:
                    import json
                    wmi_data = json.loads(result.stdout)
                    if isinstance(wmi_data, list):
                        programs = [{'name': p.get('Name', ''), 'version': p.get('Version', '')}
                                  for p in wmi_data if p.get('Name')]
                    elif isinstance(wmi_data, dict) and wmi_data.get('Name'):
                        programs = [{'name': wmi_data['Name'], 'version': wmi_data.get('Version', '')}]
                except (json.JSONDecodeError, Exception):
                    pass

        except Exception:
            pass  # Return empty list if all methods fail

    return programs


def get_windows_features():
    """Get list of enabled Windows features."""
    import subprocess

    features = []

    try:
        ps_cmd = 'powershell -Command "Get-WindowsOptionalFeature -Online | Where-Object State -eq Enabled | Select-Object FeatureName | ConvertTo-Json"'
        result = subprocess.run(ps_cmd, capture_output=True, text=True, shell=True, timeout=30)

        if result.returncode == 0:
            try:
                import json
                features_data = json.loads(result.stdout)
                if isinstance(features_data, list):
                    features = [f.get('FeatureName', '') for f in features_data if f.get('FeatureName')]
                elif isinstance(features_data, dict) and features_data.get('FeatureName'):
                    features = [features_data['FeatureName']]
            except (json.JSONDecodeError, Exception):
                pass

    except Exception:
        pass  # Return empty list if command fails

    return features


def get_installed_updates():
    """Get list of installed Windows updates."""
    import subprocess

    updates = []

    try:
        ps_cmd = 'powershell -Command "Get-HotFix | Select-Object HotFixID, InstalledOn | ConvertTo-Json"'
        result = subprocess.run(ps_cmd, capture_output=True, text=True, shell=True, timeout=30)

        if result.returncode == 0:
            try:
                import json
                updates_data = json.loads(result.stdout)
                if isinstance(updates_data, list):
                    updates = [{'id': u.get('HotFixID', ''), 'installed_on': u.get('InstalledOn', '')}
                             for u in updates_data if u.get('HotFixID')]
                elif isinstance(updates_data, dict) and updates_data.get('HotFixID'):
                    updates = [{'id': updates_data['HotFixID'], 'installed_on': updates_data.get('InstalledOn', '')}]
            except (json.JSONDecodeError, Exception):
                pass

    except Exception:
        pass

    return updates


def _parse_systeminfo(output):
    """Parse systeminfo command output."""
    info = {}

    for line in output.split('\n'):
        line = line.strip()
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()

            if 'OS Name' in key:
                info['name'] = value
            elif 'OS Version' in key:
                info['version'] = value
            elif 'System Type' in key:
                info['architecture'] = value
            elif 'Total Physical Memory' in key:
                info['memory'] = value

    return info


def _parse_registry_programs(output):
    """Parse Windows registry output for installed programs."""
    programs = []
    lines = output.split('\n')
    current_program = {}

    for line in lines:
        line = line.strip()

        if line.startswith('HKEY_'):
            # New registry key - save previous program if we have one
            if current_program.get('name'):
                programs.append(current_program)
            current_program = {}

        elif 'DisplayName' in line and 'REG_SZ' in line:
            # Extract program name
            parts = line.split('REG_SZ')
            if len(parts) > 1:
                name = parts[1].strip()
                current_program['name'] = name

        elif 'DisplayVersion' in line and 'REG_SZ' in line:
            # Extract version
            parts = line.split('REG_SZ')
            if len(parts) > 1:
                version = parts[1].strip()
                current_program['version'] = version

    # Don't forget the last program
    if current_program.get('name'):
        programs.append(current_program)

    return programs
