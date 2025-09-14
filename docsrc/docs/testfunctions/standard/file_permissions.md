# file_permissions

<div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
<span class="test-status tested">Tested</span>
<span style="background-color: var(--md-code-bg-color); padding: 2px 6px; border-radius: 3px; font-family: monospace;">file_permissions</span>
<span style="color: var(--md-default-fg-color--light);">File System</span>
</div>

**Tests file permissions, owner, and group.**

This test function validates file system permissions and ownership information. It's essential for security analysis, system administration validation, and ensuring proper file access controls are in place.

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `dst` | string | **Required.** The file path to examine. Supports glob patterns for dynamic path resolution. |
| `expected_permissions` | string | **Required.** Expected permissions in octal (e.g., "755") or symbolic (e.g., "rwxr-xr-x") format. |
| `check_owner` | string | **Optional.** Expected file owner username to verify. |
| `check_group` | string | **Optional.** Expected file group name to verify. |

## Usage Examples

### Basic Permission Check

```yaml
tests:
  - name: verify_script_executable
    function: file_permissions
    parameter:
      dst: "/home/user/bin/backup_script.sh"
      expected_permissions: "755"
    description: "Verify backup script has correct executable permissions"
```

### Symbolic Permission Format

```yaml
tests:
  - name: verify_config_readonly
    function: file_permissions
    parameter:
      dst: "/etc/myapp/config.conf"
      expected_permissions: "rw-r--r--"
    description: "Verify config file is readable by owner, readable by others"
```

### Owner and Group Verification

```yaml
tests:
  - name: verify_log_ownership
    function: file_permissions
    parameter:
      dst: "/var/log/myapp.log"
      expected_permissions: "644"
      check_owner: "myapp"
      check_group: "adm"
    description: "Verify log file has correct permissions and ownership"
```

### Security File Validation

```yaml
tests:
  - name: verify_private_key_secure
    function: file_permissions
    parameter:
      dst: "/home/user/.ssh/id_rsa"
      expected_permissions: "600"
      check_owner: "user"
    description: "Verify private key is only accessible to owner"
```

## Permission Formats

### Octal Format (Recommended)

Three-digit octal notation:

| Octal | Symbolic | Description |
|-------|----------|-------------|
| `755` | `rwxr-xr-x` | Owner: read/write/execute, Group/Others: read/execute |
| `644` | `rw-r--r--` | Owner: read/write, Group/Others: read-only |
| `600` | `rw-------` | Owner: read/write, Group/Others: no access |
| `777` | `rwxrwxrwx` | All: full access (security risk!) |

### Symbolic Format

Nine-character symbolic notation (rwxrwxrwx):

- Position 1-3: Owner permissions (user)
- Position 4-6: Group permissions
- Position 7-9: Other permissions

Each position can be:
- `r` - read permission
- `w` - write permission
- `x` - execute permission
- `-` - no permission

## Permission Bits Explanation

| Bit | Octal | Symbol | Meaning |
|-----|-------|--------|---------|
| 4 | 4 | r | Read permission |
| 2 | 2 | w | Write permission |
| 1 | 1 | x | Execute permission |

**Combined Values:**
- 7 (4+2+1) = rwx (read, write, execute)
- 6 (4+2) = rw- (read, write)
- 5 (4+1) = r-x (read, execute)
- 4 = r-- (read only)

## Common Permission Patterns

| Octal | Use Case | Description |
|-------|----------|-------------|
| `644` | Regular files | Owner can read/write, others can read |
| `755` | Executable files/directories | Owner can read/write/execute, others can read/execute |
| `600` | Private files | Only owner can read/write |
| `700` | Private directories | Only owner can access |
| `666` | Shared files | Everyone can read/write (use with caution) |

## Platform Considerations

!!! info "Unix/Linux Systems"
    - Full support for user/group ownership
    - Standard permission model applies
    - Creation time uses change time (ctime) or birth time where available

!!! warning "Windows Systems"
    - Limited permission model support
    - Owner/group checking may not be available
    - Permissions may be approximated

!!! info "macOS Systems"
    - Full Unix-style permissions
    - Extended attributes may affect actual access

## Common Use Cases

!!! example "Security Validation"
    Ensure sensitive files have appropriate restrictive permissions

!!! example "Script Execution"
    Verify scripts and binaries have execute permissions

!!! example "Configuration Files"
    Ensure config files are readable but not writable by unauthorized users

!!! example "Log Files"
    Verify log files have proper ownership for log rotation and access

!!! example "Web Server Files"
    Validate web content has appropriate permissions for security

!!! example "System Administration"
    Ensure system files maintain proper permissions after changes

!!! example "Forensic Analysis"
    Analyze file permissions to understand access patterns and security posture

## Return Values

### ✅ Success
Returns success when all specified checks pass (permissions, owner, group)

### ❌ Failure
Returns failure when any check fails, showing expected vs actual values

### ⚠️ Execution Error
Returns execution error when:

- File cannot be found or accessed
- Invalid permission format specified
- Permission denied accessing file metadata
- Platform doesn't support owner/group checking

## Example Results

```yaml
# Success case - all checks pass
result: success
details:
  - "permissions match: 755"
  - "owner matches: user"
  - "group matches: staff"

# Failure case - permission mismatch
result: failed
details:
  - "permission mismatch. Expected: 644, Got: 755"

# Failure case - multiple issues
result: failed
details:
  - "permission mismatch. Expected: 600, Got: 644"
  - "owner mismatch. Expected: user, Got: root"

# Execution error case
result: execution_error
error: "ValueError: Invalid permission format: 888"
context: "Permission parsing error"
```

## Related Functions

- [file_exists](file_exists.md) - Tests file existence before permission validation
- [file_timestamps](file_timestamps.md) - Other file metadata validation
- [dir_exists](dir_exists.md) - Directory existence (permissions apply to directories too)

## See Also

- [Examples](../examples/index.md) - Practical usage examples
- [Playbook Guide](../../user-guide/playbooks.md) - Complete playbook guide