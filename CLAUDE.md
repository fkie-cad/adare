# ADARE (Automated Desktop Analysis framework for Reproducible Experiments)

Framework for detecting forensic artifact changes across OS/software versions using automated GUI actions in VMs.

## Architecture
- **adare/** – Host client: manages projects, VMs, experiments
- **adarevm/** – Guest agent: runs inside VM, executes playbooks via WebSocket
- **adare-cv-server/** – External GUI automation server (screenshot analysis)
- **adarelib/** – Shared utilities & test functions
- **docsrc/** – Documentation

## Playbook Execution Model
**Database-driven approach** for scalability and forensic auditability:

### On Experiment Load (`adare experiment load`)
1. Parse playbook YAML file
2. Store **original YAML content** in `Playbook.original_yaml_content` (for variables/tests)
3. Serialize actions to `PlaybookItem` database models (JSON format)
4. Hash validation for integrity enforcement

### On Experiment Execution (`adare experiment run`)
1. **Load actions from PlaybookItem database models** (no YAML parsing)
2. Reconstruct action objects via deserialization
3. Parse variables/tests from stored YAML (complex structures kept as YAML)
4. Execute using reconstructed Playbook object

### Benefits
- ✅ No YAML parsing overhead during execution
- ✅ Database-level caching and query optimization
- ✅ Complete audit trail with FK relationships to ActionExecution
- ✅ Integrity validation prevents tampering
- ✅ Scalable for analytics and web interfaces

## Test Execution Performance

### Testfunction Caching (2026-02-06)
**Problem**: Testfunction discovery ran on every test execution, taking ~32 seconds to load/compile all Python modules.

**Solution**: Instance-level caching in `AdareVMServer._testfunction_cache`
- First test pays 32s discovery cost (one-time per VM session)
- Subsequent tests have zero discovery overhead (instant cache lookup)
- Cache persists for VM lifetime (requires restart to pick up testfunction changes)

**Impact**: Experiments with 20+ tests save ~10 minutes of discovery overhead

### Test Timeouts
Tests support configurable timeouts via the `timeout` field:

**Default**: 120 seconds (2 minutes) - conservative with testfunction caching
- Most cached tests complete in <5 seconds
- Complex operations (Excel parsing, file operations) may need 30-60 seconds
- Default provides safety margin while catching truly hung operations

**YAML Configuration**:
```yaml
tests:
  - name: test_simple_file
    function: standard.file_exists
    # Uses default 120s timeout
    parameter:
      dst: /path/to/file

  - name: test_large_excel
    function: excel.validate_columns
    timeout: 300  # Override for very large files (5 minutes)
    parameter:
      dst: /path/to/huge.xlsx
```

**Timeout Flow**:
1. Action timeout (playbook YAML) overrides Test timeout (testfunction default)
2. WebSocket adds 10-second buffer for communication overhead
3. VM executes test within timeout limit

## Testing
- Manual only (experiment commands, interactive mode) - so never built or perform tests

## Guidelines
- Prefix temp logs with `CLAUDE:`
- Keep files <1000 lines
- Update docs when adding features
- Review flow & fix errors after changes
- never catch generic exception (with except Exception) - use more specific Excpetion that are expected instead