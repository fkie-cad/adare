# Standard Testset

<div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
<span class="test-status tested">Tested</span>
<strong>11 Functions</strong>
<span style="color: var(--md-default-fg-color--light);">File System Operations</span>
</div>

The **Standard** testset provides fundamental file system testing capabilities for ADARE experiments. This testset focuses on file and directory operations, content validation, permissions, and metadata verification.

## Overview

The Standard testset is the core foundation for ADARE testing, providing essential functions for:

- **File and Directory Existence Testing**: Verify creation, deletion, and presence of filesystem objects
- **Content Validation**: Test file contents using exact matching, pattern matching, and substring searching
- **Metadata Verification**: Validate file timestamps, permissions, ownership, and integrity
- **Directory Structure Testing**: Verify directory contents and structure

This testset is particularly useful for:

- Forensic artifact detection and validation
- System behavior verification
- Security compliance testing
- File integrity monitoring
- Log analysis and monitoring

## Test Functions

<div style="margin-bottom: 1em;">
<input type="text" id="standard-search" placeholder="Search standard test functions..." style="padding: 8px 12px; border: 1px solid #ccc; border-radius: 4px; width: 100%; max-width: 400px;">
</div>

| Function Name | Status | Description | Parameters | Documentation Link |
|---------------|--------|-------------|------------|-------------------|
| file_exists | 🟢 Tested | Tests if a file exists at the specified path | dst (string, required) | [file_exists](../standard/file_exists.md) |
| file_does_not_exist | 🟢 Tested | Tests if a file does NOT exist at the specified path | dst (string, required) | [file_does_not_exist](../standard/file_does_not_exist.md) |
| dir_exists | 🟢 Tested | Tests if a directory exists at the specified path | dst (string, required) | [dir_exists](../standard/dir_exists.md) |
| dir_does_not_exist | 🟢 Tested | Tests if a directory does NOT exist at the specified path | dst (string, required) | [dir_does_not_exist](../standard/dir_does_not_exist.md) |
| dir_content | 🟢 Tested | Tests if a directory contains the expected files/folders | dst (string, required), files (list, required) | [dir_content](../standard/dir_content.md) |
| file_content_matches_regex | 🟢 Tested | Tests if file content matches a regular expression | dst (string, required), regex (string, required) | [file_content_matches_regex](../standard/file_content_matches_regex.md) |
| file_content_equals | 🟢 Tested | Tests if file content exactly equals the given content | dst (string, required), content (string, required) | [file_content_equals](../standard/file_content_equals.md) |
| file_hash_matches | 🟢 Tested | Tests if file hash matches expected value | dst (string, required), expected_hash (string, required), hash_type (string, optional) | [file_hash_matches](../standard/file_hash_matches.md) |
| file_timestamps | 🟢 Tested | Tests file timestamps with various comparison types | dst (string, required), timestamp_type (string, optional), comparison_type (string, optional) | [file_timestamps](../standard/file_timestamps.md) |
| file_permissions | 🟢 Tested | Tests file permissions, owner, and group | dst (string, required), expected_permissions (string, required), check_owner (string, optional) | [file_permissions](../standard/file_permissions.md) |
| file_content_contains | 🟢 Tested | Tests if file content contains specified string or byte pattern | dst (string, required), content (string, required), content_type (string, optional) | [file_content_contains](../standard/file_content_contains.md) |

<script>
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('standard-search');
    const table = document.querySelector('table');

    if (searchInput && table) {
        searchInput.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            const rows = table.querySelectorAll('tbody tr');

            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                let found = false;

                cells.forEach(cell => {
                    if (cell.textContent.toLowerCase().includes(searchTerm)) {
                        found = true;
                    }
                });

                row.style.display = found ? '' : 'none';
            });
        });
    }
});
</script>

## Function Categories

### File and Directory Existence

These functions test whether files and directories exist or don't exist at specified paths:

- [file_exists](../standard/file_exists.md) - Verify file presence
- [file_does_not_exist](../standard/file_does_not_exist.md) - Verify file absence
- [dir_exists](../standard/dir_exists.md) - Verify directory presence
- [dir_does_not_exist](../standard/dir_does_not_exist.md) - Verify directory absence

!!! tip "Common Use Cases"
    - Verify file creation after user actions
    - Confirm file deletion/cleanup
    - Validate installation/uninstallation processes
    - Monitor temporary file management

### Content Validation

These functions validate the contents of files using different matching strategies:

- [file_content_equals](../standard/file_content_equals.md) - Exact content matching
- [file_content_contains](../standard/file_content_contains.md) - Substring/pattern searching
- [file_content_matches_regex](../standard/file_content_matches_regex.md) - Regular expression matching

!!! tip "Common Use Cases"
    - Verify generated configuration files
    - Validate log entries and error messages
    - Check data export formats
    - Confirm template processing results

### Directory Operations

Functions for testing directory structures and contents:

- [dir_content](../standard/dir_content.md) - Verify expected directory contents

!!! tip "Common Use Cases"
    - Validate project structure creation
    - Verify backup/extraction operations
    - Check installation directory layouts
    - Monitor directory changes

### File Metadata and Security

Functions for testing file properties, security, and integrity:

- [file_hash_matches](../standard/file_hash_matches.md) - File integrity verification
- [file_timestamps](../standard/file_timestamps.md) - Timestamp validation
- [file_permissions](../standard/file_permissions.md) - Permission and ownership testing

!!! tip "Common Use Cases"
    - Verify file integrity after operations
    - Monitor file access patterns
    - Validate security permissions
    - Detect unauthorized modifications

## Usage Examples

### Basic File Operations

```yaml
# Test file creation and content
tests:
  - name: config_created
    function: file_exists
    parameter:
      dst: "/etc/myapp/config.yml"
    description: "Verify config file was created"

  - name: config_content_valid
    function: file_content_contains
    parameter:
      dst: "/etc/myapp/config.yml"
      content: "database_url: postgresql://"
    description: "Verify config contains database URL"
```

### Security Validation

```yaml
# Test file security properties
tests:
  - name: ssh_key_secure
    function: file_permissions
    parameter:
      dst: "/home/user/.ssh/id_rsa"
      expected_permissions: "600"
      check_owner: "user"
    description: "Verify SSH private key has secure permissions"

  - name: key_integrity
    function: file_hash_matches
    parameter:
      dst: "/home/user/.ssh/id_rsa.pub"
      expected_hash: "a1b2c3d4e5f6789012345678901234567890abcdef"
      hash_type: "sha256"
    description: "Verify public key integrity"
```

### Directory Structure Validation

```yaml
# Test project structure
tests:
  - name: project_structure
    function: dir_content
    parameter:
      dst: "/home/user/projects/myapp"
      files:
        - "src"
        - "tests"
        - "docs"
        - "package.json"
        - "README.md"
    description: "Verify complete project structure"
```

## Implementation Details

!!! info "Path Resolution"
    All functions in the Standard testset support glob pattern path resolution for dynamic file/directory matching.

!!! info "Error Handling"
    Functions distinguish between test failures (expected behavior not met) and execution errors (technical issues preventing test execution).

!!! info "Performance"
    The testset is optimized for efficient file system operations with appropriate chunked reading for large files.

!!! info "Platform Support"
    Functions are designed to work across different operating systems with appropriate platform-specific handling for features like file permissions and timestamps.

## Best Practices

!!! tip "Test Ordering"
    Structure tests to validate the complete workflow, testing file creation before content validation.

!!! tip "Path Specifications"
    Use absolute paths for reliability and glob patterns judiciously for maintainability.

!!! tip "Security Considerations"
    Always test both positive cases (expected behavior) and negative cases (security violations).

!!! tip "Performance Optimization"
    For large files, use hash-based integrity checking rather than full content comparison.

## Related Resources

- [Comprehensive Examples](../examples/index.md) - Detailed usage scenarios
- [Playbook Guide](../../user-guide/playbooks.md) - Complete playbook writing guide
- [Individual Function Documentation](../standard/index.md) - Detailed function references