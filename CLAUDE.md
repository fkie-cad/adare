## Project Overview

ADARE (Automated Desktop Analysis framework for Reproducible Experiments) is a forensic analysis framework for detecting changes in forensic artifacts across different software and operating system versions using automated GUI actions and structured tests in virtual machines.

## Architecture & Component Flow

- **adare/**: Host client that manages experiments, VMs, and coordinates all operations. Creates projects, manages VirtualBox VMs, orchestrates experiments.

- **adarevm/**: Guest software running inside VirtualBox VMs, controlled via WebSocket from the host client. Executes playbook actions inside VM, reports back via WebSocket.

- **adare-mcp-server/**: External MCP server for GUI automation (icon/text detection on screenshots), designed to run on separate/stronger hardware. Analyzes screenshots for GUI element detection and automation.

- **adarelib/**: Shared library with common utilities and test functions used across components adare and adarevm.

## Manual Testing
Tests are designed for manual execution only. Use experiment test commands and interactive development mode for functional testing.

## General Guidelines
- If you introduce log messages that are meant to be temporary add in front of the message "CLAUDE:", such that you can find it later and remove it again
- Always check after some new implementation the code quality
- Never write files with over 1500 lines, instead try to split the logic reasonable