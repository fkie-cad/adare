Web UI
======

``adare ui start`` serves a local web UI (default http://127.0.0.1:8089) for the
whole workflow: projects, environments, experiments and their runs, the VM
workbench (live VM view, single actions, checkpoints, the vision agent), and the
**System** page with host resources and run capacity (:doc:`host-resources`).

Terminal and Claude
-------------------

A terminal panel docks along the bottom of every page. Open it with
*Terminal & Claude* in the sidebar or :kbd:`Ctrl+\``. Each tab is a session on
the host, started in the project chosen in the panel:

Claude
   Claude Code, started through your login shell exactly as in your own terminal
   (your ``claude`` command, PATH and settings). With the ADARE skills installed
   (``adare skills install``) it can create experiments, write and validate playbooks,
   start runs and debug them; when Claude exits, the tab drops to the shell.

Shell
   Your login shell, e.g. to run ``adare`` commands next to the page showing their
   effect.

Pages start Claude with a task already set:

- **Experiments → Build with Claude**: asks what forensic question to answer,
  then builds the experiment, playbook and tests.
- **Experiment → Work on it with Claude**: reads and validates the experiment's
  playbook and tests, then asks what to change.
- **Run → Debug with Claude**: inspects the run, finds the first failing action
  or test and proposes a playbook fix, without starting new runs on its own.

Sessions belong to the web server, not the browser tab: hiding the panel,
switching pages or reloading reattaches to them, replaying recent output. They
end when their process exits, when the tab is closed, or when the web server
stops (at most eight run at once). Terminals need a macOS or Linux host.

.. warning::

   A terminal can run anything your user can. The web server therefore only
   accepts terminal requests from this machine: the connection must come from
   loopback, the ``Host`` header must name ``localhost``/``127.0.0.1``/``::1``
   (which defeats DNS rebinding), and a browser ``Origin`` must be local as well
   (which keeps other websites from opening a terminal). Keep the web UI bound to
   ``127.0.0.1`` (the default); terminals stay unavailable from other machines
   even when it is not.
