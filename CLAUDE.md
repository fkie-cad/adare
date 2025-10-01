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

## Testing
- Manual only (experiment commands, interactive mode) - so never built or perform tests

## Guidelines
- Prefix temp logs with `CLAUDE:`
- Keep files <1000 lines
- Update docs when adding features
- Review flow & fix errors after changes
- never catch generic exception (with except Exception) - use more specific Excpetion that are expected instead