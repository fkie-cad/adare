**********************
Environment Management
**********************

Environments in ADARE define virtual machine configurations and contain the experiments that run on those VMs. They represent specific testing scenarios like "Windows 11 with Office 365" or "Ubuntu 22.04 Server."

Understanding Environments
**************************

What is an Environment?
=======================

An environment consists of:

- **Virtual Machine Configuration**: OS, software, and settings
- **Experiment Collection**: All tests that run on this VM setup
- **Shared Context**: Common variables and resources for experiments
- **Execution History**: Results and logs from experiment runs

Environment vs. VM
==================

**Environment** (Logical)
  The configuration, experiments, and metadata

**Virtual Machine** (Physical)  
  The actual VM instance running the environment

One environment can have multiple VM instances (snapshots, parallel runs, etc.).


Creating Environments
*********************

Environment Configuration File
==============================

Environments are defined using YAML configuration files:

.. code-block:: yaml
   :caption: windows11-forensics.yml

   name: win11-forensics
   description: "Windows 11 with forensic analysis tools"
   vm: "/vms/Windows11-Forensics.ova"
   
   os:
     os: "Windows"
     platform: "windows"
     distribution: "Pro"
     version: "11 22H2"
     language: "English"
     architecture: "x64"
   
   hardware:
     memory: "8192"        # MB
     cpus: 4
     disk_space: "100"     # GB
     
   network:
     type: "NAT"           # or "Bridged", "Host-only"
     isolated: true        # Block internet access
     
   software:
     - name: "Autopsy"
       version: "4.19.3"
     - name: "Volatility"  
       version: "3.0"
     - name: "YARA"
       version: "4.2"
       
   credentials:
     username: "forensics"
     # Note: passwords should be managed securely
     
   tags:
     - windows
     - forensics
     - gui-automation
     - artifact-analysis
     
   settings:
     auto_login: true
     disable_updates: true
     disable_defender: false  # Keep for realistic testing

Required Fields
===============

**Minimal Configuration**

.. code-block:: yaml

   name: my-environment
   vm: "/path/to/vm.ova"
   os:
     platform: "windows"  # or "linux"

**Complete Configuration**

All optional fields with descriptions:

.. code-block:: yaml

   name: environment-name              # Required: unique identifier
   description: "Environment purpose"  # Optional: human description
   vm: "/path/to/vm.ova"              # Required: VM image path
   
   os:                                # Required: OS information
     os: "Windows"                    # OS name (display)
     platform: "windows"             # Required: "windows" or "linux"  
     distribution: "Pro"              # Edition/distribution
     version: "11"                    # Version number
     language: "English"              # UI language
     architecture: "x64"              # CPU architecture
     
   hardware:                          # Optional: VM resources
     memory: "4096"                   # RAM in MB
     cpus: 2                          # CPU cores
     disk_space: "50"                 # Disk in GB
     
   network:                           # Optional: network config
     type: "NAT"                      # Network adapter type
     isolated: false                  # Block internet access
     
   software: []                       # Optional: installed software list
   credentials:                       # Optional: login info
     username: "user"
   tags: []                          # Optional: categorization tags
   settings: {}                      # Optional: environment-specific settings

Loading Environments
====================

Create the environment in ADARE:

.. code-block:: bash

   # Load environment from config file
   adare environment load windows11-forensics.yml
   
   # Load with specific project
   adare environment load config.yml --project forensics-research
   
   # Force update existing environment
   adare environment load config.yml --force

VM Image Sources
================

**Pre-built Images**
  Download from `ADARE Web <https://adare.seclab-bonn.de/>`_

**Export from VirtualBox**
  
.. code-block:: bash

   # Export existing VM as OVA
   VBoxManage export "MyVM" --output "/path/to/MyVM.ova"

**Convert from Other Formats**

.. code-block:: bash

   # Convert VMware VMDK to OVA
   # (requires additional tools like ovftool)
   ovftool source.vmx output.ova

VM Image Preparation
====================

Before using a VM image:

1. **Clean Installation**: Fresh, minimal OS install
2. **Updates**: Apply security patches
3. **Software**: Install required tools and applications  
4. **Configuration**: Disable auto-updates, configure users
5. **Snapshot**: Create clean baseline snapshot
6. **Export**: Export as OVA for ADARE

Managing Environments
*********************

Listing Environments
====================

View all environments in current project:

.. code-block:: bash

   # List environments
   adare environment list
   
   # Example output:
   # Environments in project 'forensics-research':
   # ├── win11-forensics     [Windows 11 Pro]     4 experiments
   # ├── ubuntu-22-desktop  [Ubuntu 22.04]       2 experiments  
   # └── macos-monterey     [macOS Monterey]     1 experiment

Environment Information
=======================

Get detailed environment information:

.. code-block:: bash

   # Show environment details
   adare environment info win11-forensics
   
   # Show with dotnotation (project.environment)
   adare environment info forensics-research.win11-forensics

Updating Environments
=====================

Modify environment configuration:

.. code-block:: bash

   # Update environment from new config
   adare environment load updated-config.yml --force
   
   # This will:
   # - Update metadata and settings
   # - Preserve existing experiments
   # - Update VM configuration if needed

Deleting Environments
=====================

Remove environments you no longer need:

.. code-block:: bash

   # Delete environment (prompts for confirmation)
   adare environment delete win11-forensics
   
   # Delete by ULID
   adare environment delete 01ARZ3NDEKTSV4RRFFQ69G5FAV --force

.. warning::
   Deleting an environment removes all associated experiments, results, and VM data!

Working with VMs
****************

VM Lifecycle
============

Understanding the VM lifecycle helps with troubleshooting:

1. **Import**: VM image imported into VirtualBox
2. **Configure**: Hardware and network settings applied  
3. **Start**: VM boots for experiment execution
4. **Snapshot**: System state captured at key points
5. **Reset**: VM restored to clean snapshot
6. **Stop**: VM shut down after experiment

VM Status and Control
=====================

Monitor and control VMs:

.. code-block:: bash

   # List all VMs
   adare vm list
   
   # Get VM information  
   adare vm info <vm-id>
   
   # Delete specific VM
   adare vm delete <vm-id>
   
   # Clean up all VMs for environment
   adare vm clear environment <env-id> --force

VM Resource Management
======================

**Memory Allocation**

.. code-block:: yaml

   hardware:
     memory: "8192"  # 8GB RAM
     
   # Consider:
   # - Host system RAM
   # - Other running VMs
   # - VM OS requirements

**CPU Allocation**

.. code-block:: yaml

   hardware:
     cpus: 4
     
   # Guidelines:
   # - Don't exceed host CPU cores
   # - More CPUs = faster GUI automation
   # - Balance with other VMs

**Disk Space**

.. code-block:: yaml

   hardware:
     disk_space: "100"  # 100GB
     
   # Plan for:
   # - OS and software requirements
   # - Experiment artifacts
   # - VM snapshots (can be large)

Snapshots and State Management
==============================

**Base Snapshots**
  Clean system state for consistent experiment starts

**Checkpoint Snapshots**  
  Save points during long experiments

**Evidence Snapshots**
  Preserve system state for forensic analysis

.. code-block:: bash

   # List VM snapshots
   adare vm info <vm-id> --snapshots
   
   # Delete old snapshots
   adare vm delete-snapshot <vm-id> <snapshot-name>

Network Configuration
*********************

Network Types
=============

**NAT (Network Address Translation)**
  - VM can access internet through host
  - VM not directly accessible from network
  - Good for: downloading updates, web browsing tests

**Host-Only**
  - VM can communicate with host only  
  - No internet access
  - Good for: isolated forensic analysis

**Bridged**
  - VM gets IP on same network as host
  - Direct network access
  - Good for: network forensic tests

**Internal Network**
  - VMs communicate only with each other
  - No host or internet access
  - Good for: multi-VM scenarios

Security Considerations
=======================

**Isolation for Forensic Work**

.. code-block:: yaml

   network:
     type: "Host-only"     # Isolate from internet
     isolated: true        # Block all network access

**Controlled Internet Access**

.. code-block:: yaml

   network:
     type: "NAT"
     isolated: false       # Allow internet
     # Use firewall rules for fine-grained control

Advanced Configuration
**********************

Environment Variables
=====================

Define environment-wide variables:

.. code-block:: yaml

   variables:
     forensics_tools_path: "C:\\Tools\\Forensics"
     case_directory: "C:\\Cases"
     analyst_name: "{{username}}"
     
   # Available in all experiments as {{forensics_tools_path}}

Custom Scripts
==============

Run setup scripts when environment loads:

.. code-block:: yaml

   scripts:
     setup:
       - path: "/project/programs/setup-forensic-tools.sh"
         description: "Install and configure forensic tools"
         run_as: "admin"
         
     teardown:
       - path: "/project/programs/cleanup.sh" 
         description: "Clean up temporary files"

Software Management
===================

Document installed software for reproducibility:

.. code-block:: yaml

   software:
     - name: "Autopsy"
       version: "4.19.3"
       source: "https://autopsy.com/download/"
       license: "Apache 2.0"
       
     - name: "Volatility"
       version: "3.0.1"
       source: "pip install volatility3"
       notes: "Installed in Python virtual environment"

Environment Templates
*********************

Creating Templates
==================

Save successful environment configurations as templates:

.. code-block:: bash

   # Export environment as template
   adare environment template create --from win11-forensics --name "Windows 11 Forensics"

**Template Structure**

.. code-block:: text

   templates/
   └── windows-11-forensics/
       ├── environment.yml     # Environment configuration  
       ├── setup-scripts/      # Automated setup scripts
       ├── software-lists/     # Required software
       └── documentation/      # Setup instructions

Using Templates
===============

Create new environments from templates:

.. code-block:: bash

   # List available templates
   adare environment template list
   
   # Create from template
   adare environment create win11-case-analysis --from-template "Windows 11 Forensics"

Best Practices
**************

VM Image Management
===================

**Version Control**
  Track VM image versions and changes

**Documentation**
  Document software installed and configuration changes

**Security**
  Use clean, trusted VM images

**Storage**
  Compress and archive old VM images

Resource Planning
=================

**System Resources**
  Plan VM resources based on host capabilities

**Parallel Execution**
  Consider resource requirements for concurrent experiments

**Storage Growth**
  Monitor disk usage for VMs, snapshots, and results

**Network Bandwidth**
  Account for VM network usage in planning

Organization
============

**Naming Conventions**
  Use consistent, descriptive environment names

**Tagging System**
  Apply consistent tags for easy filtering

**Environment Separation**
  Separate environments for different use cases

**Regular Maintenance**
  Periodically update and clean environments


Next Steps
**********

With environments configured, move on to:

- **Writing Playbooks**: :doc:`playbooks` - Automate GUI interactions  
- **CLI Reference**: :doc:`../cli-reference/index` - Complete command documentation