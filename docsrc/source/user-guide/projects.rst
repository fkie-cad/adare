******************
Project Management
******************

Projects are the top-level organizational unit in ADARE. They group related environments, experiments, and shared resources for specific research areas or use cases.

Understanding Projects
**********************

What is a Project?
==================

A project in ADARE is:

- **A directory structure** that organizes your forensic research
- **A logical grouping** of related environments and experiments  
- **A shared workspace** for tools, templates, and resources
- **A unit of collaboration** that can be shared with others


Project Structure
*****************

Directory Layout
================

When you create a project, ADARE generates this structure:

.. code-block:: text

   my-project/
   ├── environments/              # Virtual machine environments
   │   ├── windows-10/           # Environment-specific directories
   │   └── ubuntu-22/            
   ├── programs/                 # Shared tools and utilities
   │   ├── custom-tools/         # Your forensic tools
   │   └── third-party/          # External utilities
   ├── tessdata/                 # OCR language data
   │   ├── eng.traineddata       # English language model
   │   └── deu.traineddata       # German language model (example)
   └── .adare-project            # Project metadata (hidden)

Shared Resources
================

Projects provide shared resources accessible to all environments:

**programs/**
  Custom forensic tools, scripts, and utilities used across experiments

**tessdata/**  
  Tesseract OCR language models for text recognition in different languages

**Templates**
  Reusable playbook templates and configuration files

**Documentation**
  Project-specific guides, procedures, and findings

Creating Projects
*****************

Basic Project Creation
======================

Create a new project:

.. code-block:: bash

   # Create project in current directory
   adare project create forensics-research
   
   # Create project with description
   adare project create mobile-analysis --description "iOS and Android artifact analysis"
   
   # Create project in specific location
   cd /research/projects
   adare project create windows-registry-study

Project Naming Best Practices
==============================

**Use Descriptive Names**
  - ``browser-forensics`` ✓
  - ``project1`` ✗

**Include Context**
  - ``2024-thesis-malware-analysis`` ✓
  - ``malware`` ✗ (too generic)

**Use Consistent Convention**
  - ``forensics-browser-chrome``
  - ``forensics-registry-hive``  
  - ``forensics-mobile-ios``

**Avoid Special Characters**
  - ``network-analysis`` ✓
  - ``network & analysis`` ✗

Project Directory Navigation
============================

After creating a project, navigate to it:

.. code-block:: bash

   # Move into project directory
   cd forensics-research
   
   # Verify you're in a project
   adare project list
   
   # View project structure
   ls -la

Managing Projects
*****************

Listing Projects
================

View all projects in your system:

.. code-block:: bash

   # List all projects
   adare project list
   
   # Output example:
   # Projects:
   # ├── forensics-research        /home/user/forensics-research
   # ├── mobile-analysis          /home/user/research/mobile-analysis
   # └── registry-study           /home/user/projects/registry-study

Project Information
===================

Get detailed project information:

.. code-block:: bash

   # Show current project info (run from project directory)
   adare project info
   
   # Show specific project info
   adare project info forensics-research

Removing Projects
=================

Remove projects you no longer need:

.. code-block:: bash

   # Remove project (will prompt for confirmation)
   adare project remove old-research
   
   # Force removal without confirmation
   adare project remove old-research --force

.. warning::
   Removing a project deletes all environments, experiments, and results. This action cannot be undone!

Working with Shared Resources
*****************************

Programs Directory
==================

The ``programs/`` directory stores tools used across all environments in the project.

**Adding Custom Tools**

.. code-block:: bash

   # Add your forensic analysis script
   cp ~/my-forensic-tool.py programs/custom-tools/
   
   # Make it executable
   chmod +x programs/custom-tools/my-forensic-tool.py

**Organizing Tools**

.. code-block:: text

   programs/
   ├── custom-tools/
   │   ├── registry-parser.py
   │   ├── timeline-analyzer.sh
   │   └── artifact-extractor.py
   ├── third-party/
   │   ├── volatility/
   │   ├── autopsy-plugins/
   │   └── yara-rules/
   └── templates/
       ├── playbook-templates/
       └── config-templates/

**Using Tools in Experiments**

Reference shared tools in your playbooks:

.. code-block:: yaml

   actions:
     - command:
         name: "Run Custom Registry Parser"
         command: "python3 /project/programs/custom-tools/registry-parser.py"
         shell: true

OCR Language Data
=================

The ``tessdata/`` directory contains language models for optical character recognition.

**Adding Languages**

.. code-block:: bash

   # Download German language data
   wget https://github.com/tesseract-ocr/tessdata/raw/main/deu.traineddata
   mv deu.traineddata tessdata/
   
   # Download French language data
   wget https://github.com/tesseract-ocr/tessdata/raw/main/fra.traineddata
   mv fra.traineddata tessdata/

**Using Different Languages**

Configure OCR language in playbooks:

.. code-block:: yaml

   settings:
     ocr:
       language: "deu"  # Use German OCR
       
   actions:
     - click:
         target:
           text: "Datei"      # German for "File"
           ocr_language: "deu"

Project Configuration
*********************

Project Metadata
=================

Project settings are stored in ``.adare-project``:

.. code-block:: json

   {
     "name": "forensics-research",
     "description": "Digital forensics research project",
     "created": "2025-09-10T10:00:00Z",
     "version": "1.0",
     "settings": {
       "default_timeout": 300,
       "screenshot_quality": 95,
       "ocr_languages": ["eng", "deu"]
     }
   }

Environment Defaults
====================

Set project-wide defaults for all environments:

.. code-block:: yaml
   :caption: .adare-defaults.yml

   # Default settings for all environments
   vm:
     memory: "4096"
     cpus: 2
     
   playbook:
     idle: 1.5
     timeout: 600
     screenshot:
       format: "png"
       quality: 95
       
   ocr:
     languages: ["eng"]
     confidence: 0.8

Git Integration
===============

Projects work well with version control:

.. code-block:: bash

   # Initialize git repository
   cd forensics-research
   git init
   
   # Create .gitignore for ADARE
   cat > .gitignore << EOF
   # VM files and results
   environments/*/results/
   environments/*/logs/
   environments/*/run/
   *.vdi
   *.vmdk
   *.vbox
   
   # Temporary files
   .tmp/
   *.log
   
   # OS-specific files
   .DS_Store
   Thumbs.db
   EOF
   
   # Add and commit project structure
   git add .
   git commit -m "Initial project structure"

Collaboration Workflows
***********************

Sharing Projects
================

**Via Git Repository**

.. code-block:: bash

   # Push to shared repository
   git remote add origin https://github.com/team/forensics-research.git
   git push -u origin main
   
   # Others can clone the project
   git clone https://github.com/team/forensics-research.git
   cd forensics-research

**Via ADARE Web Platform**

.. code-block:: bash

   # Login to ADARE Web
   adare web login
   
   # Publish project structure (without VM files)
   adare web publish --project-template

   # Others can download the template
   adare web download project forensics-research

Team Workflows
==============

**Role-Based Access**

- **Project Lead**: Creates structure, manages environments
- **Researchers**: Create experiments, analyze results  
- **IT Support**: Manages VMs and infrastructure
- **Reviewers**: Access results and reports

**Branch-Based Development**

.. code-block:: bash

   # Create feature branch for new experiment
   git checkout -b experiment/browser-history-analysis
   
   # Develop experiment
   adare experiment create browser-history-analysis
   # ... work on experiment ...
   
   # Commit and merge
   git add .
   git commit -m "Add browser history analysis experiment"
   git checkout main
   git merge experiment/browser-history-analysis

Project Templates
*****************

Creating Templates
==================

Save successful project structures as templates:

.. code-block:: bash

   # Create template from existing project
   adare project template create --from forensics-research --name "Digital Forensics Template"

**Template Structure**

.. code-block:: text

   forensics-template/
   ├── environments/
   │   └── template-configs/
   │       ├── windows-10.yml
   │       ├── windows-11.yml
   │       └── ubuntu-22.yml
   ├── experiments/
   │   └── example-experiments/
   │       ├── file-deletion-analysis/
   │       └── registry-modification/
   ├── programs/
   │   └── common-tools/
   └── documentation/
       ├── setup-guide.md
       └── best-practices.md

Using Templates
===============

Start new projects from templates:

.. code-block:: bash

   # Create project from template
   adare project create my-new-research --from-template "Digital Forensics Template"
   
   # List available templates
   adare project template list

Best Practices
**************

Organization
============

**Clear Naming Conventions**
  Establish and follow consistent naming patterns

**Logical Grouping**
  Group related work in the same project

**Regular Cleanup**
  Remove old experiments and unused resources

**Documentation**
  Document project purpose, setup, and procedures

Resource Management
===================

**Shared Tools**
  Place commonly-used tools in ``programs/`` directory

**Template Reuse**
  Create templates for repeated project patterns

**Version Control**
  Track changes to experiments and configurations

**Backup Strategy**
  Regular backups of project data and results

Security
========

**Access Control**
  Limit project access to authorized team members

**Sensitive Data**
  Keep real case data in separate, secured projects

**VM Security**
  Ensure VM images are clean and from trusted sources

**Network Isolation**
  Isolate test VMs from production networks

Troubleshooting
***************

Common Issues
=============

**"Not in a project directory"**
  Navigate to a project directory or create one

**"Project already exists"**  
  Choose a different name or remove the existing project

**"Permission denied"**
  Check file permissions and disk space

**"Cannot find programs"**
  Verify shared tools are in the correct ``programs/`` subdirectory

Performance Issues
==================

**Large Projects**
  - Split large projects into smaller, focused ones
  - Regular cleanup of old results and logs
  - Use ``.gitignore`` to exclude large binary files

**Storage Problems**
  - Monitor disk usage: ``df -h``
  - Clean up old VM snapshots
  - Compress or archive old experiment results

Next Steps
**********

With projects mastered, continue to:

- **Environment Setup**: :doc:`environments` - Configure virtual machines
- **Experiment Creation**: :doc:`experiments` - Design forensic tests
- **Advanced Organization**: :doc:`../advanced/index` - Complex project structures