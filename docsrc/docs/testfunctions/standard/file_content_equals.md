# file_content_equals

<div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
<span class="test-status tested">Tested</span>
<span style="background-color: var(--md-code-bg-color); padding: 2px 6px; border-radius: 3px; font-family: monospace;">file_content_equals</span>
<span style="color: var(--md-default-fg-color--light);">File System</span>
</div>

**Tests if file content exactly equals the given content.**

This test function reads a file and performs an exact comparison with the expected content. It's useful for validating generated files, configuration output, or ensuring files contain precise expected content.

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `dst` | string | **Required.** The file path to read and test. Supports glob patterns for dynamic path resolution. |
| `content` | string | **Required.** The expected content that the file should contain exactly. |

## Usage Examples

### Configuration File Validation

```yaml
tests:
  - name: verify_config_generated
    function: file_content_equals
    parameter:
      dst: "/etc/myapp/settings.conf"
      content: |
        [database]
        host=localhost
        port=5432
        name=myapp
    description: "Verify configuration file was generated correctly"
```

### Generated Script Validation

```yaml
tests:
  - name: check_backup_script
    function: file_content_equals
    parameter:
      dst: "/home/user/backup.sh"
      content: |
        #!/bin/bash
        tar -czf backup_$(date +%Y%m%d).tar.gz /home/user/documents
        echo "Backup completed"
    description: "Verify backup script was generated with correct content"
```

### Small File Validation

```yaml
tests:
  - name: verify_status_file
    function: file_content_equals
    parameter:
      dst: "/tmp/process_status.txt"
      content: "COMPLETED"
    description: "Verify process completed successfully"
```

## Common Use Cases

!!! example "Generated File Validation"
    Verify that automated processes create files with exact expected content

!!! example "Configuration File Testing"
    Ensure configuration files are generated with precise settings

!!! example "Template Output Verification"
    Confirm template processing produces exact expected output

!!! example "Status File Monitoring"
    Validate that processes write correct status information

!!! example "Export Validation"
    Verify that data export produces files with expected content

!!! example "Script Generation"
    Ensure code generators create scripts with precise syntax

## Comparison Behavior

!!! info "Whitespace Handling"
    The comparison trims leading and trailing whitespace from both actual and expected content

!!! info "Line Ending Normalization"
    Different line endings (\\n, \\r\\n) are handled appropriately

!!! info "Placeholder Support"
    The function can handle placeholder patterns for dynamic content validation

!!! info "Diff Generation"
    On failure, the function provides detailed diff output showing differences between expected and actual content

## Return Values

### ✅ Success
Returns success when file content exactly matches the expected content (after whitespace trimming)

### ❌ Failure
Returns failure when:

- File content differs from expected content
- File is empty but content is expected
- File contains content but empty content is expected

### ⚠️ Execution Error
Returns execution error when:

- The file cannot be found or read
- Permission denied reading the file
- Path resolution fails due to glob pattern ambiguity
- Unicode decoding errors occur

## Example Results

```yaml
# Success case
result: success
message: "Direct content comparison"

# Failure case with diff
result: failed
details:
  - "Content comparison failed"
  - |
    Diff:
    --- expected
    +++ actual
    @@ -1,2 +1,2 @@
    -port=8080
    +port=3000

# Execution error case
result: execution_error
error: "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff"
context: "Cannot read file /tmp/binary_file.dat"
```

## Related Functions

- [file_content_contains](file_content_contains.md) - Tests partial content matching
- [file_content_matches_regex](file_content_matches_regex.md) - Tests pattern-based content matching
- [file_exists](file_exists.md) - Tests file existence before content validation

## See Also

- [Examples](../examples/index.md) - Practical usage examples
- [Playbook Guide](../../user-guide/playbooks.md) - Complete playbook guide