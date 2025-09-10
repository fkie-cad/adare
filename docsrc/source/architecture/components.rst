**********
Components
**********

ADARE consists of three main components that work together to provide automated forensic analysis capabilities.

System Architecture
*******************

.. code-block:: text

   ┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
   │   Host System       │    │  Virtual Machine    │    │   MCP Server        │
   │   (adare client)    │    │   (adarevm agent)   │    │ (GUI automation)    │
   └─────────────────────┘    └─────────────────────┘    └─────────────────────┘
              │                           │                           │
              │        WebSocket          │         HTTP API          │
              ├───────────────────────────┼───────────────────────────┤
              │                           │                           │
              │ • Project Management      │ • Playbook Execution      │ • Screenshot Analysis
              │ • VM Lifecycle Control    │ • Test Runner             │ • Image Recognition  
              │ • Result Storage          │ • Artifact Collection     │ • Text Extraction
              │ • Web Platform Access     │ • System Monitoring       │ • Coordinate Mapping
              └───────────────────────────┴───────────────────────────┴─────────────────────

Component Details
*****************

ADARE Host Client
=================

**Location**: ``adare/`` directory  
**Role**: Main orchestration and user interface component  
**Language**: Python

**Responsibilities**

- **Project Management**: Create, organize, and manage forensic research projects
- **Environment Configuration**: Set up and maintain virtual machine environments  
- **Experiment Orchestration**: Coordinate experiment execution across VMs
- **VM Lifecycle Management**: Start, stop, snapshot, and reset virtual machines
- **Result Collection & Analysis**: Gather, store, and analyze experiment results
- **Web Platform Integration**: Sync with ADARE Web for sharing experiments
- **User Interfaces**: Provide CLI and web interfaces for user interaction

**Key Modules**

.. code-block:: text

   adare/
   ├── cli/                    # Command-line interface
   ├── web/                    # Web interface  
   ├── backend/
   │   ├── project/           # Project management
   │   ├── environment/       # Environment handling
   │   ├── experiment/        # Experiment orchestration
   │   ├── vm/               # VirtualBox integration
   │   └── events/           # Event processing
   ├── database/             # Data persistence
   ├── virtualbox/           # VirtualBox API wrapper
   └── types/               # Core data structures

**Communication Protocols**

- **VirtualBox API**: Control VM lifecycle and snapshots
- **WebSocket**: Real-time communication with VM agents  
- **HTTP REST**: Communication with MCP server
- **Database**: SQLite for local data storage
- **File System**: Project and result storage

ADARE VM Agent  
==============

**Location**: ``adarevm/`` directory  
**Role**: In-VM execution agent for forensic experiments  
**Language**: Python

**Responsibilities**

- **Playbook Execution**: Parse and execute YAML-based automation scripts
- **GUI Automation**: Perform mouse clicks, keyboard input, and screen captures
- **System Command Execution**: Run shell commands and system operations
- **Test Validation**: Execute forensic tests and artifact verification
- **Artifact Collection**: Gather and analyze forensic evidence
- **Real-time Communication**: Report progress and results to host

**Key Modules**

.. code-block:: text

   adarevm/
   ├── core/                  # Core agent functionality
   ├── automation/            # GUI automation engine
   │   ├── actions/          # Action implementations
   │   ├── targets/          # Target selection strategies  
   │   └── screenshot/       # Screen capture utilities
   ├── testing/              # Test framework
   │   ├── functions/        # Built-in test functions
   │   └── validators/       # Result validation
   ├── platforms/            # OS-specific implementations
   │   ├── windows/          # Windows-specific code
   │   └── linux/            # Linux-specific code
   └── clients/              # Communication clients

**Supported Platforms**

- **Windows**: Windows 10, 11 (GUI automation, registry access, file operations)
- **Linux**: Ubuntu, CentOS, Fedora (X11/Wayland GUI, file system operations)  
- **macOS**: Basic support (limited GUI automation capabilities)

MCP Server
===========

**Location**: ``adare-mcp-server/`` directory  
**Role**: External GUI automation and computer vision service  
**Language**: Python (with OpenCV and Tesseract)

**Responsibilities**

- **Screenshot Analysis**: Process VM screenshots for GUI elements
- **Image Recognition**: Match UI elements using template matching  
- **Text Extraction**: OCR capabilities for finding text on screen
- **Coordinate Calculation**: Determine click coordinates for GUI elements
- **Multi-language Support**: Handle different UI languages and fonts

**Key Features**

.. code-block:: text

   adare-mcp-server/
   ├── vision/               # Computer vision algorithms
   │   ├── image_matching/   # Template matching algorithms
   │   ├── text_detection/   # OCR and text recognition  
   │   └── preprocessing/    # Image enhancement
   ├── api/                  # HTTP API endpoints
   ├── models/              # Machine learning models
   └── config/              # Server configuration

**Computer Vision Capabilities**

- **Template Matching**: Find UI elements using reference images
- **Feature Detection**: Identify UI components automatically  
- **OCR (Optical Character Recognition)**: Extract text from screenshots
- **Multi-scale Analysis**: Handle different screen resolutions and DPI
- **Fuzzy Matching**: Handle slight variations in UI appearance

Shared Libraries
================

**Location**: ``adarelib/`` directory  
**Role**: Common utilities and test functions  
**Language**: Python

**Components**

- **Common Utilities**: Shared helper functions and data structures
- **Test Functions**: Reusable forensic test implementations  
- **Variable Handling**: Template processing and variable substitution
- **Validation Framework**: Common validation and verification utilities

Communication Flow
******************

Experiment Execution Flow
=========================

1. **Host** receives experiment request from user
2. **Host** starts VM and ensures agent is running  
3. **Host** sends playbook to **VM Agent** via WebSocket
4. **VM Agent** begins playbook execution
5. For GUI actions:
   a. **VM Agent** takes screenshot
   b. **VM Agent** sends screenshot to **MCP Server**
   c. **MCP Server** analyzes image and returns coordinates
   d. **VM Agent** performs click/action at coordinates
6. **VM Agent** executes tests and collects artifacts
7. **VM Agent** sends results back to **Host**
8. **Host** stores results and generates reports

Data Flow Diagram
=================

.. code-block:: text

   User Command
        │
        ▼
   ┌─────────┐    Playbook    ┌──────────┐    Screenshot    ┌─────────────┐
   │  Host   │─────────────►  │ VM Agent │─────────────────► │ MCP Server  │
   │ Client  │                │          │                   │             │
   └─────────┘                └──────────┘                   └─────────────┘
        │                           │                               │
        │         Results           │         Coordinates           │
        │◄──────────────────────────┼───────────────────────────────┘
        │                           │
        ▼                           ▼
   [Results DB]              [Artifacts & Logs]

Security Architecture
*********************

Network Isolation
==================

- **VM Network Isolation**: Test VMs can be isolated from production networks
- **Controlled Communication**: Only required protocols (WebSocket, HTTP) are used
- **Local-first**: All processing can run locally without internet access
- **Firewall Integration**: Works with host firewall configurations

Data Protection
===============

- **Encrypted Communication**: WebSocket connections use TLS when configured
- **Local Storage**: Sensitive data stays on local machine
- **Access Control**: File system permissions protect experiment data
- **Clean Snapshots**: VMs reset to clean state between experiments

Process Isolation  
=================

- **Containerization Ready**: Components can run in containers
- **Privilege Separation**: MCP server runs with minimal privileges
- **VM Sandboxing**: VirtualBox provides hardware-level isolation
- **Resource Limits**: Configurable limits on CPU, memory, and disk usage

Deployment Architecture
***********************

Single-Host Deployment
======================

All components run on one machine:

.. code-block:: text

   ┌─────────────────────────────────────────────────────────┐
   │                    Host Machine                         │
   │                                                         │
   │  ┌────────────┐  ┌─────────────────┐  ┌──────────────┐  │
   │  │    ADARE   │  │   VirtualBox    │  │ MCP Server   │  │
   │  │   Client   │  │      VMs        │  │   (local)    │  │
   │  └────────────┘  └─────────────────┘  └──────────────┘  │
   └─────────────────────────────────────────────────────────┘

**Pros**: Simple setup, low latency, complete isolation  
**Cons**: Resource limitations, single point of failure

Distributed Deployment
======================

Components spread across multiple machines:

.. code-block:: text

   ┌──────────────┐    ┌──────────────────┐    ┌────────────────┐
   │ Control Host │    │  VM Host Farm    │    │  MCP Cluster   │
   │              │    │                  │    │                │
   │ ┌──────────┐ │    │ ┌──────────────┐ │    │ ┌────────────┐ │
   │ │  ADARE   │ │    │ │ VirtualBox   │ │    │ │    MCP     │ │
   │ │ Client   │◄┼────┼►│     VMs      │◄┼────┼►│  Servers   │ │
   │ └──────────┘ │    │ └──────────────┘ │    │ └────────────┘ │
   └──────────────┘    └──────────────────┘    └────────────────┘

**Pros**: Scalability, resource distribution, fault tolerance  
**Cons**: Network complexity, configuration overhead

Scalability Considerations
**************************

Horizontal Scaling
==================

- **Multiple VM Hosts**: Distribute VMs across multiple machines
- **MCP Server Clusters**: Load balance computer vision processing  
- **Parallel Experiments**: Run multiple experiments simultaneously
- **Resource Pooling**: Share computational resources efficiently

Performance Optimization
=========================

- **Snapshot Management**: Optimize VM snapshot creation and restoration
- **Image Caching**: Cache commonly-used GUI images for faster matching
- **Database Indexing**: Optimize result queries and searches  
- **Compression**: Compress screenshots and artifacts for storage efficiency

Monitoring and Observability
=============================

- **Health Checks**: Monitor component health and connectivity
- **Performance Metrics**: Track experiment execution times and resource usage
- **Logging Integration**: Centralized logging for troubleshooting
- **Alerting**: Notify on experiment failures or resource issues

Extension Points
****************

Plugin Architecture
===================

ADARE supports extensions through:

- **Custom Test Functions**: Add new forensic validation capabilities
- **Action Plugins**: Implement new automation actions  
- **Platform Support**: Add support for new operating systems
- **Result Exporters**: Create custom report formats

API Integration
===============

- **REST APIs**: HTTP endpoints for external integration
- **WebHook Support**: Real-time notifications to external systems  
- **Database Access**: Direct database integration for custom tools
- **File System Integration**: Access to experiment data and results

Next Steps
**********

To dive deeper into ADARE's architecture:

- **Data Flow**: :doc:`data-flow` - How data moves through the system
- **Module Structure**: :doc:`module_structure` - Detailed code organization  
- **Developer Guide**: :doc:`../developer/index` - Contributing to ADARE development