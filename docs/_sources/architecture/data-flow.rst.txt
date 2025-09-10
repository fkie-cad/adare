*********
Data Flow
*********

Understanding how data flows through ADARE helps with troubleshooting, optimization, and extending the framework. This section details the complete data flow from experiment creation to result analysis.

.. contents:: Quick Navigation
   :local:
   :depth: 2

Experiment Lifecycle Data Flow
******************************

Overview
========

.. code-block:: text

   User Input → Playbook → VM Execution → Artifact Collection → Results Storage
       │             │           │               │                    │
       │             │           │               │                    │
   [CLI/Web]    [YAML Files]  [Screenshots]  [Forensic Data]    [Database]
                                   │               │                    │
                                   │               │                    │
                              [MCP Server]    [Test Results]      [File System]

Detailed Flow Stages
====================

**Stage 1: Experiment Definition**
  User creates playbook and test definitions

**Stage 2: Environment Preparation**  
  VM is started and configured for experiment

**Stage 3: Playbook Execution**
  Actions are performed and screenshots captured

**Stage 4: Test Validation**
  Forensic tests verify expected artifacts

**Stage 5: Result Collection**
  All data is gathered and stored for analysis

Stage 1: Experiment Definition
*******************************

Input Sources
=============

**User-Created Files**

.. code-block:: text

   experiments/<name>/
   ├── playbook.yml         # User-defined automation sequence
   ├── metadata.yml         # Experiment configuration  
   └── img/                 # Reference images for GUI automation

**Configuration Data**

.. code-block:: yaml

   # Example playbook data structure
   settings:
     idle: 1.0
     timeout: 300
     
   variables:
     username: "forensics"
     test_file: "/evidence/test.txt"
     
   tests:
     - name: file_exists
       function: file_exists
       parameter:
         dst: '{{test_file}}'
   
   actions:
     - click: {target: {image: "icon.png"}}
     - test: file_exists

Data Validation
===============

Before execution, ADARE validates:

- YAML syntax correctness
- Required fields presence  
- Variable reference validity
- Test function availability
- Image file accessibility

**Validation Flow**

.. code-block:: text

   playbook.yml → Parser → Validator → Error Check → Execution Queue
                     │         │           │              │
                     │         │           │              │
              [Syntax Tree] [Validation] [Error List] [Ready State]

Stage 2: Environment Preparation  
*********************************

VM State Management
===================

**VM Lifecycle Data**

.. code-block:: text

   Environment Config → VM Import → Snapshot Creation → Agent Start
         │                 │             │                │
         │                 │             │                │
   [YAML Config]      [VirtualBox]  [VM Snapshots]  [WebSocket]

**Data Structures**

.. code-block:: python

   # VM State Information
   vm_state = {
       "vm_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
       "name": "forensics-win11-001", 
       "status": "running",
       "snapshots": ["base", "experiment-start"],
       "network": {"type": "NAT", "isolated": true},
       "resources": {"memory": 8192, "cpus": 4}
   }

Agent Initialization
====================

**Communication Establishment**

.. code-block:: text

   Host → WebSocket Connection → VM Agent → Ready Signal → Host
    │            │                  │           │          │
    │            │                  │           │          │
   [Start]   [Connection]      [Agent Boot]  [Handshake] [Proceed]

**Agent State Data**

.. code-block:: json

   {
     "agent_id": "vm-agent-001",
     "platform": "windows",
     "version": "1.0.0",
     "capabilities": ["gui", "filesystem", "registry"],
     "screen_resolution": "1920x1080",
     "ready": true
   }

Stage 3: Playbook Execution
****************************

Action Processing Pipeline
==========================

**Action Execution Flow**

.. code-block:: text

   Action → Preprocessing → Target Resolution → Execution → Result Capture
      │          │               │                │             │
      │          │               │                │             │
   [YAML]   [Variable Sub]  [Coordinates]    [System Call]  [Screenshot]

**Data Transformation**

.. code-block:: python

   # Action data transformation example
   
   # Original YAML
   action = {
       "click": {
           "target": {"text": "{{button_name}}"},
           "description": "Click the {{button_name}} button"
       }
   }
   
   # After variable substitution
   processed_action = {
       "click": {
           "target": {"text": "Save"},  
           "description": "Click the Save button"
       }
   }
   
   # After target resolution (from MCP server)
   resolved_action = {
       "click": {
           "coordinates": [150, 300],
           "confidence": 0.95,
           "description": "Click the Save button"
       }
   }

Screenshot Processing
=====================

**Screenshot Data Flow**

.. code-block:: text

   VM Screen → Screenshot → Compression → MCP Server → Analysis → Coordinates
       │           │            │            │           │           │
       │           │            │            │           │           │
   [Display]   [Raw PNG]   [Optimized]   [HTTP POST]  [CV Process] [X,Y Coords]

**Image Analysis Pipeline**

.. code-block:: python

   # Screenshot analysis data
   screenshot_analysis = {
       "timestamp": "2025-09-10T10:30:00Z",
       "resolution": "1920x1080", 
       "file_size": 2048576,
       "analysis_results": {
           "text_matches": [
               {"text": "Save", "confidence": 0.98, "coords": [150, 300]},
               {"text": "Cancel", "confidence": 0.92, "coords": [250, 300]}
           ],
           "image_matches": [
               {"template": "button.png", "confidence": 0.85, "coords": [150, 300]}
           ]
       }
   }

Stage 4: Test Validation
*************************

Test Execution Data
===================

**Test Processing Pipeline**

.. code-block:: text

   Test Def → Parameter Resolution → Function Execution → Result Validation
      │             │                      │                    │
      │             │                      │                    │
   [YAML]      [Variables]          [System Query]        [Pass/Fail]

**Test Data Structures**

.. code-block:: python

   # Test execution data
   test_execution = {
       "test_name": "file_exists_check",
       "function": "file_exists",
       "parameters": {"dst": "/evidence/test.txt"},
       "timestamp": "2025-09-10T10:30:15Z",
       "duration": 0.25,  # seconds
       "result": {
           "status": "PASS",
           "value": True,
           "message": "File exists at /evidence/test.txt",
           "evidence": {
               "file_stats": {
                   "size": 1024,
                   "created": "2025-09-10T10:29:45Z",
                   "modified": "2025-09-10T10:29:45Z"
               }
           }
       }
   }

Artifact Collection  
===================

**Forensic Data Gathering**

.. code-block:: text

   System State → Artifact Scanner → Evidence Collector → Data Storage
        │              │                   │                 │
        │              │                   │                 │
   [File System]   [Registry]         [Hash Values]      [Database]
   [Registry]      [Metadata]         [Timestamps]       [File System]
   [Memory]        [Hashes]           [Signatures]

**Artifact Data Format**

.. code-block:: python

   # Collected artifact data
   artifact_collection = {
       "collection_timestamp": "2025-09-10T10:30:20Z",
       "artifacts": {
           "filesystem": {
               "files_created": ["/evidence/test.txt"],
               "files_modified": [],
               "files_deleted": ["/tmp/original.txt"]
           },
           "registry": {  # Windows only
               "keys_created": ["HKCU\\Software\\TestApp"],
               "values_modified": [
                   {"key": "HKCU\\Software\\TestApp", "name": "Version", "value": "1.0"}
               ]
           },
           "processes": {
               "started": ["notepad.exe"],
               "terminated": []
           }
       },
       "evidence_hashes": {
           "/evidence/test.txt": "sha256:abc123...",
           "registry_export.reg": "sha256:def456..."
       }
   }

Stage 5: Result Collection
***************************

Result Aggregation
==================

**Data Consolidation**

.. code-block:: text

   Screenshots → Test Results → Artifacts → Logs → Final Report
       │             │            │          │          │
       │             │            │          │          │
   [Image Files] [JSON Data]  [Evidence]  [Text]  [Database]
                                                      │
                                                      │
                                                [File System]

**Result Data Structure**

.. code-block:: python

   # Complete experiment result
   experiment_result = {
       "run_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
       "experiment": "file-deletion-analysis",
       "environment": "win11-forensics", 
       "start_time": "2025-09-10T10:30:00Z",
       "end_time": "2025-09-10T10:35:30Z",
       "duration": 330,  # seconds
       "status": "COMPLETED",
       
       "execution_summary": {
           "total_actions": 15,
           "successful_actions": 15,
           "failed_actions": 0,
           "total_tests": 8,
           "passed_tests": 8,
           "failed_tests": 0
       },
       
       "artifacts_collected": 47,
       "screenshots_captured": 15,
       "log_entries": 234
   }

Storage and Indexing
====================

**Database Schema**

.. code-block:: sql

   -- Core experiment tracking
   CREATE TABLE experiment_runs (
       id TEXT PRIMARY KEY,
       experiment_name TEXT,
       environment_name TEXT,
       start_time TIMESTAMP,
       end_time TIMESTAMP,
       status TEXT,
       result_summary JSON
   );
   
   -- Test execution results  
   CREATE TABLE test_results (
       id TEXT PRIMARY KEY,
       run_id TEXT,
       test_name TEXT,
       status TEXT,
       execution_time REAL,
       result_data JSON,
       FOREIGN KEY (run_id) REFERENCES experiment_runs(id)
   );
   
   -- Artifact tracking
   CREATE TABLE artifacts (
       id TEXT PRIMARY KEY,
       run_id TEXT,
       artifact_type TEXT,
       file_path TEXT,
       hash_value TEXT,
       metadata JSON,
       FOREIGN KEY (run_id) REFERENCES experiment_runs(id)
   );

**File System Organization**

.. code-block:: text

   results/<run_id>/
   ├── metadata.json           # Experiment metadata
   ├── execution_log.txt       # Detailed execution log
   ├── test_results.json       # All test results
   ├── artifacts/              # Collected forensic artifacts
   │   ├── filesystem/         # File system evidence
   │   ├── registry/           # Registry exports (Windows)
   │   └── memory/             # Memory dumps (if collected)
   ├── screenshots/            # All captured screenshots
   │   ├── 001_action_start.png
   │   ├── 002_click_button.png
   │   └── ...
   └── reports/                # Generated reports
       ├── summary.html        # Human-readable summary
       ├── timeline.csv        # Forensic timeline
       └── evidence.json       # Machine-readable evidence

Communication Protocols
***********************

WebSocket Protocol
==================

**Message Format**

.. code-block:: json

   {
     "type": "action_request",
     "id": "req_001", 
     "timestamp": "2025-09-10T10:30:00Z",
     "data": {
       "action": "click",
       "target": {"text": "Save"},
       "options": {"timeout": 10}
     }
   }
   
   {
     "type": "action_response",
     "id": "req_001",
     "timestamp": "2025-09-10T10:30:05Z", 
     "status": "success",
     "data": {
       "coordinates": [150, 300],
       "execution_time": 0.5
     }
   }

**Protocol Flow**

.. code-block:: text

   Host                    VM Agent
    │                         │
    ├── Connection Request ──→│
    │←── Connection Accept ───┤
    │                         │
    ├── Playbook Data ──────→│
    │←── Acknowledge ─────────┤
    │                         │
    ├── Action Request ─────→│
    │←── Screenshot ──────────┤
    │←── Action Complete ─────┤
    │                         │
    ├── Test Request ───────→│ 
    │←── Test Results ────────┤

HTTP API Protocol
=================

**MCP Server API**

.. code-block:: http

   POST /api/v1/analyze_image
   Content-Type: application/json
   
   {
     "image": "base64_encoded_screenshot",
     "targets": [
       {"type": "text", "value": "Save", "confidence": 0.8},
       {"type": "image", "template": "button_template.png"}
     ]
   }

**Response Format**

.. code-block:: json

   {
     "analysis_id": "analysis_001",
     "timestamp": "2025-09-10T10:30:00Z",
     "results": [
       {
         "target_type": "text",
         "target_value": "Save",
         "matches": [
           {"coordinates": [150, 300], "confidence": 0.95}
         ]
       }
     ],
     "processing_time": 0.125
   }

Data Persistence Strategy
**************************

Local Storage
=============

**SQLite Database**
  - Experiment metadata and results
  - Test execution history
  - Performance metrics
  - Index data for fast queries

**File System**
  - Screenshots and images  
  - Forensic artifacts
  - Log files
  - Generated reports

Remote Storage Integration
==========================

**ADARE Web Platform**

.. code-block:: python

   # Upload data structure
   web_upload = {
       "experiment_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
       "metadata": {...},          # Experiment info
       "results_summary": {...},   # High-level results
       "artifacts": [...],         # Evidence files
       "privacy_level": "public",  # Sharing settings
       "tags": ["forensics", "registry"]
   }

**Synchronization Flow**

.. code-block:: text

   Local Results → Privacy Filter → Upload Queue → Web Platform
        │              │               │              │
        │              │               │              │
   [Full Data]   [Public Only]    [Batch Upload]  [Shared DB]

Performance Optimization
************************

Data Flow Optimization
======================

**Streaming vs. Batch Processing**

.. code-block:: text

   # Real-time streaming (low latency)
   Screenshot → Immediate Analysis → Quick Action
   
   # Batch processing (high throughput)  
   Multiple Screenshots → Batch Analysis → Bulk Actions

**Compression and Caching**

.. code-block:: python

   # Screenshot optimization
   optimization_pipeline = {
       "capture": {"format": "PNG", "quality": 95},
       "compression": {"algorithm": "zlib", "level": 6},
       "caching": {"enabled": True, "ttl": 300},
       "transmission": {"chunk_size": 8192}
   }

Memory Management
=================

**Data Lifecycle Management**

.. code-block:: text

   Capture → Process → Store → Archive → Cleanup
      │         │        │        │         │
      │         │        │        │         │
   [Memory]  [Memory]   [Disk]   [Archive] [Delete]

**Resource Monitoring**

.. code-block:: python

   # Resource usage tracking
   resource_metrics = {
       "memory_usage": {
           "host_client": "256 MB",
           "vm_agent": "128 MB", 
           "mcp_server": "512 MB"
       },
       "disk_usage": {
           "screenshots": "2.1 GB",
           "artifacts": "450 MB",
           "logs": "125 MB"
       },
       "network_bandwidth": {
           "websocket_traffic": "1.2 MB/s",
           "http_api_traffic": "3.4 MB/s"
       }
   }

Next Steps
**********

Understanding ADARE's data flow helps with:

- **Advanced Topics**: :doc:`../advanced/index` - Performance tuning and optimization
- **Troubleshooting**: :doc:`../troubleshooting/index` - Debug data flow issues
- **CLI Reference**: :doc:`../cli-reference/index` - Command documentation for data operations