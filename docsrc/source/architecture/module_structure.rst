************************
Module Structure
************************

ADARE is organized into a well-defined module hierarchy that separates concerns and promotes maintainability. This document provides a comprehensive overview of the codebase organization and architectural decisions.

Overview
========

The ADARE framework consists of two main packages:

- **adare**: Core framework with CLI, backend, database, and frontend components
- **adarevm**: VM-based execution environment with WebSocket communication

Package Architecture
====================

Core Package (adare)
---------------------

The main ``adare`` package is organized into the following top-level modules:

.. code-block:: text

   adare/
   ├── backend/          # Business logic and operations
   ├── cli/              # Command-line interface
   ├── database/         # Data persistence layer
   ├── frontend/         # User interface components
   ├── types/            # Core type definitions
   ├── helperfunctions/  # Utility functions
   ├── config/           # Configuration management
   ├── customyaml/       # YAML processing extensions
   └── integration/      # External system integrations

Backend Module Organization
===========================

The backend is organized by functional domain:

Experiment Management
---------------------

.. code-block:: text

   backend/experiment/
   ├── commands.py              # Main operations (create, load, run, sync)
   ├── runner.py                # Modern async experiment runner
   ├── action_controller.py     # Action execution control
   ├── websocket_action_controller.py  # WebSocket-based actions
   ├── websocket_client.py      # VM communication client
   ├── database.py              # Database operations
   ├── directory.py             # Directory management
   ├── exceptions.py            # Domain-specific exceptions
   └── ...

**Key Classes:**
- ``ExperimentConfig``: Configuration for experiment execution
- ``ExperimentRunContext``: Runtime context for experiments
- ``ExperimentDirectory``: File system operations
- ``WebSocketClient``: VM communication

Environment Management
-----------------------

.. code-block:: text

   backend/environment/
   ├── commands.py      # Environment operations
   ├── database.py      # Database operations
   └── exceptions.py    # Domain exceptions

**Key Functions:**
- Environment creation and loading
- VM integration and validation
- Configuration management

Project Management
------------------

.. code-block:: text

   backend/project/
   ├── commands.py      # Project operations
   ├── database.py      # Database operations
   ├── directory.py     # Directory management
   └── exceptions.py    # Domain exceptions

**Key Classes:**
- ``ProjectDirectory``: Project file system operations
- Project lifecycle management functions

TestFunction Management
-----------------------

.. code-block:: text

   backend/testfunction/
   ├── commands.py      # TestFunction operations
   ├── database.py      # Database operations
   ├── directory.py     # Directory management
   └── exceptions.py    # Domain exceptions

CLI Module Organization
=======================

Command Interface
-----------------

.. code-block:: text

   cli/
   ├── experiment.py    # Experiment commands
   ├── environment.py   # Environment commands
   ├── project.py       # Project commands
   ├── vm.py           # VM management commands
   ├── show.py         # List/display commands
   ├── web.py          # Web interface commands
   └── ...

**Architecture Pattern:**
Each CLI module follows the pattern:

.. code-block:: python

   def exec_<command>_<action>(arguments):
       """Execute command with argument validation."""
       if project_directory := determine_projectdirectory(arguments.project):
           backend_function(project_directory, arguments.param)
       else:
           raise NoProjectFoundError()

Database Module Organization
============================

Data Access Layer
-----------------

.. code-block:: text

   database/
   ├── api/             # Database access layer
   │   ├── base.py      # Base database functionality
   │   ├── experiment.py # Experiment database operations
   │   ├── environment.py # Environment database operations
   │   ├── vm.py        # VM database operations
   │   └── ...
   ├── models/          # SQLAlchemy ORM models
   │   ├── experiment.py # Experiment-related models
   │   ├── login.py     # Authentication models
   │   └── vm.py        # VM-related models
   ├── events/          # Database event handling
   └── fixtures.py      # Test data and initialization

**Key Patterns:**
- Repository pattern for data access
- ORM models separate from business logic
- Event-driven architecture for database changes

Type System Architecture
========================

Core Types
----------

.. code-block:: text

   types/
   ├── experiment.py    # Experiment type definitions
   ├── websocket.py     # WebSocket communication types
   ├── testset.py       # TestSet configuration types
   ├── stage.py         # Execution stage types
   ├── backend.py       # Backend operation types
   ├── environment.py   # Environment configuration types
   ├── event.py         # Event system types
   ├── playbook.py      # YAML automation types
   └── ws.py           # WebSocket protocol types

**Design Principles:**
- Dataclasses for immutable configuration
- Protocol classes for interface definitions
- Enum types for controlled vocabularies
- Type hints throughout for static analysis

Helper Functions Organization
=============================

Utility Categories
------------------

.. code-block:: text

   helperfunctions/
   ├── file/            # File operations
   │   ├── safe_deletion.py
   │   └── file_progress.py
   ├── text/            # Text processing
   │   ├── string.py
   │   ├── regex.py
   │   └── strings/
   ├── data/            # Data processing
   │   ├── csv/
   │   ├── dict/
   │   ├── yaml.py
   │   └── hash.py
   ├── system/          # System integration
   │   ├── subprocess/
   │   ├── web/
   │   ├── workingdirectory/
   │   └── port.py
   ├── analysis/        # Code analysis
   │   └── pyfileanalyze/
   ├── user_experience/ # UX enhancements
   │   ├── project_suggestions.py
   │   ├── vm_suggestions.py
   │   └── file_error_suggestions.py
   └── templates/       # Template processing
       └── jinja/

**Design Philosophy:**
- Single responsibility per module
- Pure functions where possible
- Comprehensive error handling
- Extensive documentation

Integration Module Architecture
===============================

External System Integration
---------------------------

.. code-block:: text

   integrations/
   ├── virtualbox/      # VirtualBox API integration
   │   └── api.py
   ├── vagrant/         # Vagrant integration (legacy)
   │   ├── vagrantbox.py
   │   ├── vagrantfile.py
   │   └── vagrantutils.py
   ├── web/             # Web application integration
   │   ├── login.py
   │   └── exceptions.py
   ├── webappaccess/    # Web service access
   │   ├── download.py
   │   ├── upload.py
   │   ├── login.py
   │   └── experiment.py
   └── networkdrive/    # Network drive integration
       ├── networkdrive.py
       └── exceptions.py

Configuration Architecture
==========================

Configuration Management
------------------------

.. code-block:: text

   config/
   ├── __init__.py          # Core configuration constants
   ├── configdirectory.py   # Directory configuration
   ├── database.py          # Database configuration
   ├── breakpoints.py       # Debugging configuration
   ├── gui.py              # GUI configuration
   ├── server.py           # Server configuration
   └── exceptions.py        # Configuration exceptions

**Key Features:**
- Environment-based configuration
- Default value management
- Validation and type checking
- Path resolution and normalization

Frontend Architecture
=====================

Terminal Interface
------------------

.. code-block:: text

   frontend/terminal/
   ├── console.py           # Console management
   ├── experiment.py        # Experiment UI
   ├── experiment_list.py   # Experiment list view
   ├── environment.py       # Environment UI
   ├── environment_list.py  # Environment list view
   ├── project_list.py      # Project list view
   ├── run.py              # Run execution display
   ├── run_list.py         # Run list view
   └── textualize/         # Advanced UI components
       ├── experiment_flow_console_widget.py
       └── experiment_interactive.py

**UI Framework:**
- Built on Textual framework
- Rich console output
- Interactive components
- Real-time updates

Architectural Patterns
======================

Domain-Driven Design
--------------------

The codebase follows domain-driven design principles:

- **Bounded Contexts**: Each domain (experiment, environment, project) is self-contained
- **Aggregates**: Related entities are grouped together
- **Repositories**: Data access is abstracted through repository pattern
- **Domain Events**: Changes trigger events for loose coupling

Command Pattern
---------------

CLI commands follow the command pattern:

.. code-block:: python

   def exec_command(arguments):
       """Command execution with validation and error handling."""
       # 1. Validate arguments
       # 2. Determine context (project directory)
       # 3. Execute business logic
       # 4. Handle errors appropriately

Repository Pattern
------------------

Database access uses repository pattern:

.. code-block:: python

   class ExperimentApi(BaseDbApi):
       """Repository for experiment data operations."""
       
       def get_experiment_by_name(self, name: str, project_ulid: str):
           """Retrieve experiment by name within project."""
           pass

Event-Driven Architecture
-------------------------

Database changes trigger events:

.. code-block:: python

   # Event listeners automatically handle database changes
   import adare.database.events.stage  # Activates event listeners

Dependency Injection
--------------------

Components are loosely coupled through dependency injection:

.. code-block:: python

   def experiment_run(project_dir: Path, experiment: str, environment: str):
       """Business logic receives dependencies as parameters."""
       api = ExperimentApi()  # Dependency can be injected
       # ...

Testing Architecture Integration
================================

The module structure supports comprehensive testing:

**Test Organization:**
- Each module has corresponding test file
- Mock-friendly interfaces
- Isolated test databases
- Async test support

**Test Categories:**
- Unit tests for individual modules
- Integration tests for workflows
- End-to-end tests for CLI commands
- Database tests with temporary databases

Module Dependencies
===================

Dependency Flow
---------------

.. code-block:: text

   CLI Layer
      ↓
   Backend Layer
      ↓
   Database Layer
      ↓
   Models/Types Layer

**Rules:**
- Higher layers can depend on lower layers
- Lower layers cannot depend on higher layers
- Cross-domain dependencies are minimized
- External dependencies are isolated

Circular Dependency Prevention
------------------------------

- Import statements are carefully managed
- Interface segregation prevents tight coupling
- Dependency injection breaks circular references
- Event-driven communication reduces direct dependencies

Future Architecture Considerations
==================================

Planned Improvements
--------------------

1. **Microservice Architecture**: Consider splitting into microservices
2. **Plugin System**: Extensible plugin architecture
3. **API Layer**: RESTful API for external integration
4. **Event Sourcing**: Consider event sourcing for audit trails
5. **CQRS Pattern**: Separate read/write models for complex queries

Scalability Considerations
--------------------------

- Database sharding strategies
- Async/await for I/O bound operations
- WebSocket for real-time communication
- Message queues for background processing

This module structure provides a solid foundation for the ADARE framework while maintaining flexibility for future enhancements and scalability requirements.