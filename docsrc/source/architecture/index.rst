************
Architecture
************

ADARE is composed of three Python packages and one external server process that
work together to automate GUI-based forensic experiments inside virtual machines.

.. contents:: On this page
   :local:
   :depth: 2


System Overview
===============

The framework follows a host-guest split. The **host client** orchestrates
everything from the researcher's machine -- project setup, VM lifecycle,
experiment execution, and result collection. The **guest agent** runs inside
the virtual machine, receiving commands over WebSocket to perform GUI
actions, execute shell commands, and run test functions. A **shared library**
provides the common protocol, data models, and test infrastructure used by
both sides. An **external CV server** handles all computer-vision work
(screenshot analysis, icon detection, OCR) so that heavy OpenCV and
PaddleOCR dependencies stay out of the VM.

::

   Researcher
       |
       v
   +-----------+      WebSocket       +------------+
   |   adare   | ------------------> |  adarevm   |
   |  (host)   | <------------------ | (guest VM) |
   +-----------+                      +------------+
       |   |
       |   +--- MCP (HTTP) ---> adare-cv-server
       |
       +--- libvirt / QEMU / VBoxManage ---> Hypervisor


Host Client (adare)
===================

The host client is a CLI application built with a layered architecture:

**CLI** (``adare.cli``)
   Click-based command groups: ``project``, ``environment``, ``experiment``,
   ``vm``, ``testfunction``, ``dev``, and others. Each CLI module delegates
   to the API layer.

**API** (``adare.api``)
   Facade classes (``DevModeAPI``, ``ExperimentAPI``, ``ProjectAPI``, etc.)
   that provide a unified interface for both CLI and web frontends. All API
   methods return ``Result[T]`` objects for consistent error handling.

**Services** (``adare.services``)
   Business logic layer. Each service (``experiment_service``,
   ``vm_service``, ``project_service``, etc.) coordinates backend commands
   and database operations.

**Backend** (``adare.backend``)
   Domain-specific modules organised by entity: ``project``, ``environment``,
   ``experiment``, ``vm``, ``testfunction``, and ``devmode``. The experiment
   backend is the largest, containing the action executor, step runner,
   playbook controller, WebSocket client, agent installer, and
   forensic reporter.

**Hypervisor Abstraction** (``adare.hypervisor``)
   A factory-and-strategy pattern that decouples the rest of the system from
   any specific virtualisation backend. See :doc:`hypervisors` for details.

**Database** (``adare.database``)
   SQLite-backed storage using Peewee models. Separate global and
   per-project databases track VMs, environments, experiments, runs, stages,
   playbook items, test results, and events.


Guest Agent (adarevm)
=====================

A lightweight WebSocket server that runs inside the VM. It receives
``TOOL_CALL`` messages from the host, dispatches them to tool mixins
(GUI, test, system, file), and returns ``TOOL_RESULT`` messages with the
outcome. PyAutoGUI drives mouse and keyboard; PaddleOCR and OpenCV stay on
the host side. See :doc:`guest-agent` for the full architecture.


Shared Library (adarelib)
=========================

``adarelib`` is installed on both host and guest. It contains:

- **WebSocket protocol** (``adarelib.websocket.protocol``) -- message types
  (``TOOL_CALL``, ``TOOL_RESULT``, ``EVENT``, ``STATUS``, ``CONNECT``),
  dataclass definitions, parsing helpers, and the ``ToolRegistry``.
- **Event model** (``adarelib.event``) -- ``Event`` and ``TestResult``
  dataclasses used for action and test result tracking.
- **Test infrastructure** (``adarelib.testset``) -- ``BasicTest`` base class,
  testfunction discovery, YAML custom loader for test sets, and the
  ``VariableRegistry``.
- **Common utilities** -- variable resolution, YAML helpers, regex helpers,
  module import utilities, and shared constants (``StatusEnum``,
  timestamp formats).


CV Server (adare-cv-server)
===========================

A standalone MCP (Model Context Protocol) server built on FastMCP. It
exposes three tools -- ``find_icon``, ``find_text``, and ``get_all_text`` --
over a streamable HTTP transport. The host starts it as a subprocess
before experiment execution and communicates via the MCP client. See
:doc:`cv-server` for detection methods and integration details.


Subsystem Documentation
=======================

.. toctree::
   :maxdepth: 1

   hypervisors
   file-sharing
   guest-agent
   cv-server
