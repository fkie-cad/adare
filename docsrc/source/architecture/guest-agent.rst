***********
Guest Agent
***********

The guest agent (``adarevm``) is a Python process that runs inside the
virtual machine. It receives commands from the host over a WebSocket
connection, executes them, and streams results and events back.

.. contents:: On this page
   :local:
   :depth: 2


Architecture
============

The core of the agent is ``AdareVMServer``
(``adarevm.core.server.AdareVMServer``), a WebSocket server built on the
``websockets`` library. The server class is assembled from four tool mixins
via multiple inheritance:

.. code-block:: python

   class AdareVMServer(
       GUIToolsMixin,      # screenshot, click, keyboard, scroll, drag, goto, idle
       TestToolsMixin,     # upload testfunctions, set variables, run test
       SystemToolsMixin,   # shell execution, system info, dependency install
       FileToolsMixin,     # chunked file pull, filesystem snapshot, timestamp
   ): ...

Each mixin provides a group of related tool methods that are registered in a
tool dictionary at init time. When a ``TOOL_CALL`` message arrives, the server
looks up the tool name in this dictionary and dispatches to the corresponding
method.

Tool methods run as **background asyncio tasks** so that long-running
operations (such as dependency installation or test execution) do not block
the WebSocket message loop. The server tracks running tasks per client and
cancels them automatically when a client disconnects.


Communication
=============

The agent communicates with the host using a custom WebSocket protocol
defined in ``adarelib.websocket.protocol``. The host runs an
``AdareVMClient`` (``adare.backend.experiment.websocket_client``) that
connects to the agent's WebSocket server (default port 18765).

::

   Host (adare)                          Guest VM (adarevm)
   +-------------------+                 +-------------------+
   | AdareVMClient     |   WebSocket     | AdareVMServer     |
   |                   | --------------> |                   |
   |  send TOOL_CALL   |                 |  dispatch to tool |
   |                   | <-------------- |                   |
   |  receive          |   TOOL_RESULT   |  return result    |
   |  TOOL_RESULT      |   or EVENT      |  or stream events |
   +-------------------+                 +-------------------+

The connection uses ``max_size=None`` (no message size limit) and disables
automatic WebSocket ping/pong on the client side. The host-side client
maintains a dictionary of pending calls keyed by message ID, using
``asyncio.Future`` objects to correlate results with requests.


Message Types
=============

All messages are JSON-serialised dataclasses defined in
``adarelib.websocket.protocol``.

.. list-table::
   :header-rows: 1
   :widths: 20 15 50

   * - Message Type
     - Direction
     - Purpose
   * - ``TOOL_CALL``
     - Host to Guest
     - Invoke a tool on the agent. Contains ``id``, ``tool`` name, and
       ``params`` dictionary.
   * - ``TOOL_RESULT``
     - Guest to Host
     - Response to a tool call. Contains ``id`` (matching the call),
       ``success`` flag, ``result`` dictionary, and optional ``error``
       string.
   * - ``EVENT``
     - Guest to Host
     - Real-time streaming event. Contains ``event_type`` and ``data``.
       Used for progress updates, GUI action notifications, and log
       messages.
   * - ``STATUS``
     - Guest to Host
     - Status update with a ``status`` string and ``data`` dictionary.
   * - ``CONNECT``
     - Either
     - Connection establishment with ``client_info``.
   * - ``PING`` / ``PONG``
     - Either
     - Connection keep-alive.

Event types include: ``TEST_START``, ``TEST_COMPLETE``, ``TEST_FAILED``,
``GUI_CLICK``, ``GUI_FIND``, ``GUI_KEYPRESS``, ``GUI_IDLE``, ``GUI_DRAG``,
``COMMAND_START``, ``COMMAND_COMPLETE``, ``LOG``, ``ERROR``, and
``PROGRESS``.


Tool Categories
===============

GUI Tools (``GUIToolsMixin``)
-----------------------------

Automate mouse and keyboard input inside the VM using PyAutoGUI. GUI imports
are lazy-loaded to avoid initialisation failures on Wayland or when running
in host-GUI mode (``ADARE_GUI_MODE=host``).

- ``screenshot`` -- capture the full screen or a region; returns base64
  PNG.
- ``click``, ``right_click``, ``double_click`` -- mouse clicks at
  coordinates.
- ``drag`` -- click-and-drag between two points.
- ``keyboard`` -- type text or press key combinations.
- ``scroll`` -- mouse wheel scrolling.
- ``goto`` -- move the mouse cursor to coordinates.
- ``idle`` -- wait for a specified duration.
- ``screenshot_window`` -- capture a specific window.

Test Tools (``TestToolsMixin``)
-------------------------------

Manage test functions inside the VM.

- ``upload_testfunctions`` -- receive a base64-encoded archive of test
  function Python files, extract them into a temporary directory, and make
  them available for execution.
- ``install_dependencies`` -- install Python dependencies required by test
  functions.
- ``set_variables`` -- update the variable dictionary available to tests.
- ``run_test`` -- execute a single test function by name with parameters.
  Uses an instance-level cache (``_testfunction_cache``) to avoid
  re-discovering test functions on every call.

System Tools (``SystemToolsMixin``)
-----------------------------------

Shell execution and system management.

- ``execute_shell`` -- run a shell command and return stdout, stderr, and
  return code.
- ``collect_system_info`` -- gather OS version, hostname, installed
  packages, and other system metadata.
- ``get_status`` -- report agent health and available tools.
- ``set_screenshot_method`` -- switch between screenshot backends.
- ``chain_commands`` -- execute a sequence of shell commands in order.

File Tools (``FileToolsMixin``)
-------------------------------

File transfer and filesystem operations.

- ``pull_file_chunk`` -- read a chunk of a guest file and return it as
  base64. Used for host-initiated file downloads when shared directories
  are not available.
- ``get_filesystem_snapshot`` -- enumerate files and metadata in a
  directory tree. Used for forensic diff analysis.
- ``get_timestamp`` -- return the current guest system time.


Agent Lifecycle
===============

1. **Wheel installation** -- during experiment setup, the host installs
   ``adarevm`` and ``adarelib`` wheels inside the guest via pip. Version
   detection avoids redundant reinstalls (see ``agent_installer.py``). The
   wheels are placed in the ``/adare/vm`` shared directory by the file
   transfer strategy (see :doc:`file-sharing`).

2. **Startup** -- the host launches ``adarevm`` inside the guest (either
   via QGA command execution or a scheduled task on Windows). The
   ``adarevm.main.run()`` entry point loads ``config.json`` from the run
   directory, configures logging, resolves tool and data paths, and starts
   the ``AdareVMServer`` on ``0.0.0.0:18765``.

3. **Connection** -- the host's ``AdareVMClient`` connects to the agent's
   WebSocket server through the forwarded port. The agent sends a welcome
   event listing available tools.

4. **Operation** -- the host sends ``TOOL_CALL`` messages as dictated by
   the playbook. Each tool runs as a background task; the agent streams
   ``EVENT`` messages for progress and returns a ``TOOL_RESULT`` when done.

5. **Shutdown** -- when the experiment finishes, the host disconnects.
   The agent cancels any remaining tasks for that client and continues
   listening (it may serve additional connections in dev mode). The VM is
   eventually stopped by the host lifecycle manager.
