# ADARE Documentation

**Automated Desktop Analysis framework for Reproducible Experiments**

<div style="float: right; margin: 0 0 1em 2em;">
<img src="assets/logo.png" width="150" alt="ADARE Logo">
</div>

ADARE is a powerful framework designed for **forensic artifact analysis** and **digital forensics research**. It automates desktop interactions within virtual machines to detect and analyze changes in forensic artifacts across different software and operating system versions.

## What makes ADARE unique?

🔬 **Forensic Focus**
Specifically designed for digital forensics research with built-in artifact analysis capabilities

🤖 **GUI Automation**
Uses advanced computer vision and GUI automation to simulate realistic user interactions

📊 **Reproducible Experiments**
YAML-based playbooks ensure experiments can be shared, reproduced, and validated by others

🔄 **Cross-Platform Testing**
Test forensic tools and artifacts across multiple OS versions and software configurations

🌐 **Community Sharing**
Integration with [ADARE Web](https://adare.seclab-bonn.de/) for sharing experiments and results

## Key Use Cases

**Forensic Tool Validation**
Test how forensic tools behave across different OS versions and validate their reliability

**Artifact Analysis**
Analyze how user actions create, modify, or delete forensic artifacts (registry entries, file timestamps, browser history, etc.)

**Research & Education**
Create reproducible experiments for forensic research papers or educational content

**Compliance Testing**
Ensure forensic procedures work consistently across different system configurations

## Quick Example

Here's what a simple ADARE experiment looks like:

```yaml
# Delete a file and verify trash bin artifacts
actions:
  - click:
      target:
        image: "file_explorer.png"
  - click:
      target:
        text: "testfile.txt"
  - keyboard:
      combination: ["delete"]

tests:
  - name: file_deleted
    function: file_does_not_exist
    parameter:
      dst: "/home/user/testfile.txt"
  - name: trash_artifact_created
    function: file_exists
    parameter:
      dst: "/home/user/.local/share/Trash/files/testfile.txt"
```

## Getting Started

Ready to start?

1. **Install ADARE** → [Installation](installation/index.md)
2. **Quick Tutorial** → [Quick Start](quickstart/index.md)

## Documentation Structure

**🚀 Quick Start**
[Quick Start Guide](quickstart/index.md) - Get up and running with ADARE in minutes

**👤 User Guide**
[User Guide](user-guide/index.md) - Complete guide for daily ADARE usage

**💻 CLI Reference**
[CLI Reference](cli-reference/index.md) - Complete command-line interface documentation

**🧪 Test Functions**
[Test Functions](testfunctions/index.md) - Complete reference for all available test functions with examples

**🏗️ Architecture**
[Architecture](architecture/index.md) - Understanding how ADARE works internally

**⚡ Advanced Topics**
[Advanced Topics](advanced/index.md) - Custom test functions, VM management, and performance tuning