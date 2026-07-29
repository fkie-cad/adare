*****************************************
Authoring Experiments with the MCP Server
*****************************************

What This Is
============

``adare dev mcp`` exposes a running dev-session VM as an **MCP server** so an
**external harness** — `OpenCode <https://opencode.ai>`_, `Claude Code
<https://docs.claude.com/en/docs/claude-code>`_, or any MCP client (model-agnostic,
including one driving a local **Ollama** model) — becomes the agentic loop.

ADARE does not try to be the agent here. Rebuilding a robust planning/retry/tool
loop is not ADARE's differentiator and would trail mature harnesses. Instead
ADARE contributes what it is genuinely good at:

- **VM control** over QEMU's host-side QMP engine (no guest agent),
- **CV/OCR grounding** (``find_text`` / ``find_icon``),
- **record → replay determinism** — a recorded session becomes an ordinary
  ADARE playbook (image crops + OCR text + a ``tests:`` block) that replays with
  **no LLM**.

So a natural-language request like *"delete testfile.txt and verify it's gone —
and search what tests exist"* becomes a harness workflow: the harness reads the
screen, clicks, and calls ``list_testfunctions`` + ``add_test`` to attach the
assertion. ADARE grounds and records; the harness reasons.

The Grounding Model (CV-first, VL-record, no GPU)
=================================================

- **During *record*** the harness's own (typically cloud vision) model reads
  each ``screenshot()`` and decides where to click. ADARE performs the click and
  **crops the pre-click screenshot** into an ``image:`` target, plus captures
  OCR text.
- **During *replay*** there is **no LLM**: ADARE re-finds the saved crop with
  template matching (``find_icon``) and text with OCR (``find_text``), driving
  the same clicks deterministically.

There is **no local GPU requirement**. Heavy vision runs in the harness's model
(e.g. Ollama Cloud); ADARE's CV/OCR is CPU-only. A GPU UI-detector
(OmniParser/NVIDIA-class) is a possible future ``find_target`` backend but is out
of scope today.

Prerequisites
=============

A running dev session (the MCP server binds to its VM and CV server):

.. code-block:: bash

   adare dev start -e ubuntu24043
   adare dev list            # note the session id, or rely on auto-detection

Starting the Server
===================

.. code-block:: bash

   # Auto-detects the session when only one is running
   adare dev mcp

   # Or target a session and bind explicitly
   adare dev mcp -s 01K72QABC123 --host 127.0.0.1 --port 13110

The server is long-lived and blocks until you press Ctrl-C. It listens on
streamable HTTP at ``http://<host>:<port>/mcp`` — the same transport as the CV
server, on a **distinct port** (default ``13110``; the CV/OCR server uses
``13109``). Override the defaults with ``ADARE_GUI_MCP_PORT`` /
``ADARE_GUI_MCP_HOST``. Recorded playbooks land in the project directory by
default, or wherever ``--out-dir`` points.

Connecting a Harness
====================

Register the ADARE server as a **remote HTTP MCP server** in your harness. A
vision-capable brain grounds best (it reads ``screenshot()`` directly); a
text-only model can still navigate via ``find_text`` / ``find_icon``.

Claude Code
-----------

.. code-block:: bash

   claude mcp add --transport http adare-gui http://127.0.0.1:13110/mcp

or add it to ``.mcp.json`` in your project:

.. code-block:: json

   {
     "mcpServers": {
       "adare-gui": { "type": "http", "url": "http://127.0.0.1:13110/mcp" }
     }
   }

OpenCode
--------

Add it to ``opencode.json``:

.. code-block:: json

   {
     "$schema": "https://opencode.ai/config.json",
     "mcp": {
       "adare-gui": {
         "type": "remote",
         "url": "http://127.0.0.1:13110/mcp",
         "enabled": true
       }
     }
   }

To drive a local model, point the harness at your Ollama endpoint per its own
configuration — the ADARE MCP registration is identical regardless of the brain.

The Tools
=========

Perception & control (over QMP)
-------------------------------

- ``screenshot()`` — capture the VM screen (base64 PNG + pixel dimensions). Read
  this to decide where to act; it is cached so the next ``click`` can crop a
  robust target around your point.
- ``click(x, y, button)`` / ``double_click(x, y)`` — click at absolute pixels.
- ``type(text)`` — type literal text into the focused field.
- ``key(combo)`` — press a key or hotkey (e.g. ``enter``, ``ctrl+s``).
- ``scroll(direction, amount)`` — scroll up/down.
- ``wait(seconds)`` — let the UI settle (recorded as an ``idle`` action).

Grounding aids
--------------

- ``find_text(text)`` — OCR-locate on-screen text; returns ``x, y, confidence``.
- ``find_icon(image_name)`` — template-match a saved crop; returns coordinates.

These are aids: primary record-time grounding is the harness model's own
coordinates from ``screenshot()``.

Discovery
---------

- ``list_testfunctions()`` — search the project's testfunctions (name,
  dotnotation, description, parameters, category). This is the "search the
  tests" capability.

Authoring
---------

- ``start_recording(goal, path)`` / ``stop_recording()`` — while recording,
  ``click`` / ``type`` / ``key`` / ``scroll`` auto-append to the playbook, and
  each ``click`` auto-crops the cached screenshot into an ``image:`` target.
- ``add_test(name, function, parameters, description)`` — attach an assertion,
  **validated against the catalog** (unknown functions are rejected). It defines
  the test in the ``tests:`` block and runs it at the current point.
- ``add_variable(name, value)`` — register a ``variables:`` entry so the
  playbook is parameterizable.
- ``save_playbook(path)`` — write the playbook (GUI actions + ``tests:`` block)
  and return its path.

Replay
------

- ``run_playbook(path)`` — replay a playbook deterministically (CV/OCR, no LLM).

Walkthrough: "delete a file and verify it's gone"
=================================================

Drive the harness in natural language; it calls the ADARE tools. A typical
sequence the harness performs:

1. ``start_recording(goal="delete testfile.txt and verify it is gone")``
2. ``screenshot()`` → open the file manager, navigate to the file (``click`` /
   ``type`` / ``key`` — each click crops a target).
3. ``list_testfunctions()`` → find an assertion, e.g.
   ``filesystem.file_does_not_exist``.
4. ``add_test(name="verify_gone", function="filesystem.file_does_not_exist",
   parameters={"path": "/root/testfile.txt"})`` → adds a ``tests:`` entry **and**
   a ``- test:`` action.
5. ``save_playbook("experiments/delete_file.play.yaml")``.

The saved playbook has the GUI delete steps, an image crop per click, and the
``file_does_not_exist`` assertion. Replay it with **no LLM**:

.. code-block:: bash

   adare dev playbook -s <session> -f experiments/delete_file.play.yaml
   # or as a full host-mode experiment (deterministic CV/OCR + tests)
   adare experiment run <experiment> -e <environment> --gui-mode host

Reuse: Variables and Idioms
===========================

Recorded playbooks use ``variables:`` for the changing bits (paths, names), so
one playbook covers the same idea across environments — replay it with different
variable values, no LLM. A small library of common patterns ships under
``templates/idioms/`` (e.g. *delete a file and verify*, *open an app and
verify*); copy one, edit its ``variables:``, and replay. See that directory's
``README.md`` for parameterized-replay details.

Fallback: The Embedded Agent
============================

For fully unattended authoring without an external harness, ADARE keeps a
self-contained vision-LLM agent (``adare dev agent``) that drives the same VM
toward a goal using a configured vLLM endpoint (``ADARE_VLLM_*``; works with
Ollama Cloud). Prefer the MCP path when you want a mature harness to reason and
author tests; use the embedded agent for hands-off install automation. See
:doc:`/guide/vm-image-creation`.

.. seealso::

   :doc:`/guide/dev-mode`
      Dev sessions, checkpoints, and interactive playbook development

   :doc:`/reference/actions`
      Available playbook actions

   :doc:`/guide/test-driven-analysis`
      Testfunctions and assertions
