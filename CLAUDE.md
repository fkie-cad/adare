# ADARE (Automated Desktop Analysis framework for Reproducible Experiments)

Framework for detecting forensic artifact changes across OS/software versions using automated GUI actions in VMs.

## Architecture
- **adare/** – Host client: manages projects, VMs, experiments  
- **adarevm/** – Guest agent: runs inside VM, executes playbooks via WebSocket  
- **adare-cv-server/** – External GUI automation server (screenshot analysis)  
- **adarelib/** – Shared utilities & test functions  
- **docsrc/** – Documentation  

## Testing
- Manual only (experiment commands, interactive mode) - so never built or perform tests

## Guidelines
- Prefix temp logs with `CLAUDE:`  
- Keep files <1000 lines  
- Update docs when adding features  
- Review flow & fix errors after changes  
- never catch generic exception but more specific ones