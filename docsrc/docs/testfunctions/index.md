# Test Functions Reference

ADARE provides a comprehensive set of test functions to validate forensic artifacts and system states. This reference documents all available test functions organized by testsets.

## Test Function Status Legend

- 🟢 **Tested**: Fully implemented and tested in production
- 🟡 **Development**: Implemented but under active development
- 🔴 **Planned**: Planned for future implementation

## Available Testsets

ADARE organizes test functions into logical testsets based on their purpose and functionality:

| Testset | Functions | Description |
|---------|-----------|-------------|
| [Standard](testsets/standard.md) | 11 | File system operations, content validation, permissions, and metadata testing |

## All Test Functions

<div style="margin-bottom: 1em;">
<input type="text" id="function-search" placeholder="Search test functions..." style="padding: 8px 12px; border: 1px solid #ccc; border-radius: 4px; width: 100%; max-width: 400px;">
</div>

| Function Name | Testset | Status | Description | Parameters |
|---------------|---------|---------|-------------|------------|
| file_exists | Standard | 🟢 Tested | Tests if a file exists at the specified path | dst (string, required) |
| file_does_not_exist | Standard | 🟢 Tested | Tests if a file does NOT exist at the specified path | dst (string, required) |
| dir_exists | Standard | 🟢 Tested | Tests if a directory exists at the specified path | dst (string, required) |
| dir_does_not_exist | Standard | 🟢 Tested | Tests if a directory does NOT exist at the specified path | dst (string, required) |
| dir_content | Standard | 🟢 Tested | Tests if a directory contains the expected files/folders | dst (string, required), files (list, required) |
| file_content_matches_regex | Standard | 🟢 Tested | Tests if file content matches a regular expression | dst (string, required), regex (string, required) |
| file_content_equals | Standard | 🟢 Tested | Tests if file content exactly equals the given content | dst (string, required), content (string, required) |
| file_hash_matches | Standard | 🟢 Tested | Tests if file hash matches expected value | dst (string, required), expected_hash (string, required), hash_type (string, optional) |
| file_timestamps | Standard | 🟢 Tested | Tests file timestamps with various comparison types | dst (string, required), timestamp_type (string, optional), comparison_type (string, optional) |
| file_permissions | Standard | 🟢 Tested | Tests file permissions, owner, and group | dst (string, required), expected_permissions (string, required), check_owner (string, optional) |
| file_content_contains | Standard | 🟢 Tested | Tests if file content contains specified string or byte pattern | dst (string, required), content (string, required), content_type (string, optional) |

<script>
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('function-search');
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

## Usage in Playbooks

Test functions are used in the `tests` section of ADARE playbooks:

```yaml
tests:
  - name: check_file_exists
    function: file_exists
    parameter:
      dst: "/path/to/file.txt"
    description: "Verify the file was created"

  - name: check_content
    function: file_content_contains
    parameter:
      dst: "/path/to/logfile.log"
      content: "ERROR: Authentication failed"
    description: "Verify error was logged"
```

## Common Parameters

Most test functions share common parameters:

- `name`: A unique identifier for the test
- `function`: The test function to use
- `parameter`: Function-specific parameters (see individual function documentation)
- `description`: Optional human-readable description

## External Resources

- [Practical Examples](examples/index.md) - Comprehensive usage examples
- [Playbook Guide](../user-guide/playbooks.md) - Complete playbook writing guide
- [ADARE Web Examples](https://adare.seclab-bonn.de/experiments) - Community shared experiments