# file_exists

<div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
<span class="test-status tested">Tested</span>
<span style="background-color: var(--md-code-bg-color); padding: 2px 6px; border-radius: 3px; font-family: monospace;">file_exists</span>
<span style="color: var(--md-default-fg-color--light);">File System</span>
</div>

**Tests if a file exists at the specified path.**

This test function verifies that a file is present at the given destination path. It's commonly used to confirm that user actions or system processes have successfully created files.

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `dst` | string | **Required.** The file path to check for existence. Supports glob patterns for dynamic path resolution. |

## Usage Examples

### Basic Usage

```yaml
tests:
  - name: verify_log_created
    function: file_exists
    parameter:
      dst: "/var/log/application.log"
    description: "Verify application log file was created"
```

### With Glob Patterns

```yaml
tests:
  - name: verify_temp_file_created
    function: file_exists
    parameter:
      dst: "/tmp/temp_*.txt"
    description: "Verify temporary file was created with timestamp"
```

## Common Use Cases

!!! example "File Creation Verification"
    Confirm that user actions or applications have created expected files

!!! example "Log File Monitoring"
    Verify that applications are generating log files as expected

!!! example "Configuration File Validation"
    Ensure configuration files exist after installation or setup

!!! example "Artifact Detection"
    Detect forensic artifacts created by user actions

## Return Values

### ✅ Success
Returns success when the file exists at the specified path

### ❌ Failure
Returns failure when:

- The file does not exist at the specified path
- The path exists but points to a directory, not a file

### ⚠️ Execution Error
Returns execution error when:

- Permission denied accessing the path
- Path resolution fails due to glob pattern ambiguity
- System I/O errors occur

## Example Results

```yaml
# Success case
result: success
message: "File exists at /var/log/application.log"

# Failure case
result: failed
details:
  - "file with path /var/log/missing.log does not exist"

# Execution error case
result: execution_error
error: "PermissionError: [Errno 13] Permission denied"
context: "Cannot check file existence for /root/protected.log"
```

## Related Functions

- [file_does_not_exist](file_does_not_exist.md) - Tests that a file does NOT exist
- [dir_exists](dir_exists.md) - Tests directory existence
- [file_content_equals](file_content_equals.md) - Tests file content after confirming existence

## See Also

- [Examples](../examples/index.md) - Practical usage examples
- [Playbook Guide](../../user-guide/playbooks.md) - Complete playbook guide