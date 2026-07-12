********************
Windows Icon Library
********************

ADARE drives a target machine by matching reference icons on-screen and clicking
them. Historically those references were loose PNGs shipped inside each
experiment (``<experiment>/img/*.png``). That has two problems:

* **Redistribution.** Windows system and application icons are Microsoft's
  copyrighted assets, so bundling them in experiments/repositories is legally
  questionable.
* **Version drift.** The same icon lives at a different DLL/index across Windows
  versions, so a hand-picked PNG breaks across a fleet.

The **icon library** solves both. A playbook refers to an icon by a
**friendly name** (for example ``windows_explorer``); ADARE extracts the
*version-correct* icon **from the target machine at runtime**, caches it, and
feeds it to the existing image matcher. No Microsoft bitmaps are ever shipped —
only code plus a small, version-independent name → *resolver spec* map.

.. contents:: On this page
   :local:
   :depth: 2

Quick start
===========

There are two ways to use an icon-library name. Both accept any term from the
registry (see `Discovering available names`_).

**1. As a click/drag target** (``target.icon``) — works in every action that
takes a ``target``:

.. code-block:: yaml

   actions:
     - click:
         target:
           icon: windows_explorer
     - click:
         target:
           icon: recycle_bin
           strategy: !TopLeft

**2. As a visual test** (``icon=``) — works in ``visual.exists``,
``visual.not_exists``, ``visual.count_equals``, ``visual.count_min`` and
``visual.count_max``:

.. code-block:: yaml

   tests:
     - name: recycle_bin_visible
       function: visual.exists
       parameter:
         icon: recycle_bin

That is the whole authoring experience — a name instead of a PNG path. Icons
are otherwise matched exactly like ``image:`` targets, so strategies
(``!BestConfidence``, ``!TopLeft``, …) and everything else behave identically.

Discovering available names
===========================

List every term shipped in the registry together with the strategy used to
resolve it:

.. code-block:: console

   $ adare icons list

The registry ships ~100 names covering shell/stock icons (``folder``,
``recycle_bin``, ``drive_fixed``, ``shield`` …), Windows executables
(``windows_explorer``, ``notepad``, ``control_panel`` …), third-party apps
(``chrome``, ``firefox``, ``msedge`` …), and file-type associations
(``pdf_file``, ``docx_file``, ``zip_archive`` …).

If you request a name that does not exist, the error suggests the closest
matches, so a typo like ``recycl_bin`` points you at ``recycle_bin``.

How it works
============

.. code-block:: text

   name  ──►  resolver spec  ──►  target's own Win32 APIs  ──►  256px PNG  ──►  cache  ──►  find_icon
   (windows_explorer)  ({exe: explorer.exe})  (ExtractIconEx)          (extracted on target)

#. The name is looked up in ``icon-library.yml`` to get a **resolver spec**
   (version-independent).
#. On a **cache miss**, ADARE asks the target's ``adarevm`` agent to resolve the
   spec through documented Windows shell APIs and return the largest icon
   variant as a PNG. Windows itself picks the version-correct DLL/index — ADARE
   maintains **no** per-version icon table.
#. The PNG is written to the local cache and matched by the existing CV
   ``find_icon`` cascade (template → SIFT → ORB), which is already
   scale-invariant.
#. On a **cache hit**, the cached PNG is reused with no round-trip to the target.

The cache lives under the ADARE app-data directory, keyed by target OS so an OS
upgrade re-extracts instead of reusing a stale bitmap::

   <appdata>/icons/<os_key>/<name>.png      # e.g. ~/.adare/icons/windows11/recycle_bin.png

Resolver strategies
===================

Each registry entry uses exactly one strategy. You rarely need to know these to
*use* a name, but they matter when `Adding a new icon`_.

.. list-table::
   :header-rows: 1
   :widths: 18 34 48

   * - Strategy
     - Example spec
     - Windows call
   * - ``stock``
     - ``{stock: SIID_FOLDER}``
     - ``SHGetStockIconInfo`` — the ``SHSTOCKICONID`` enum is fixed across
       Windows versions
   * - ``exe``
     - ``{exe: "%SystemRoot%\\explorer.exe"}``
     - Icon 0 of an executable (``ExtractIconEx`` / ``PrivateExtractIcons``)
   * - ``app``
     - ``{app: chrome.exe}``
     - ``App Paths`` registry lookup → executable → icon 0
   * - ``fileassoc``
     - ``{fileassoc: .pdf}``
     - ``SHGetFileInfo`` with ``SHGFI_USEFILEATTRIBUTES`` (icon of the
       registered handler)
   * - ``dll``
     - ``{dll: imageres.dll, index: 3}``
     - Explicit fallback — only for the rare icon with no stock ID and no
       owning executable

Adding a new icon
=================

Add a line to ``adare/appdata/icon-library.yml`` under ``icons:`` with a
lowercase, snake_case name and a single-strategy spec:

.. code-block:: yaml

   icons:
     my_app:      {app: myapp.exe}
     config_file: {fileassoc: .ini}
     folder:      {stock: SIID_FOLDER}

Prefer, in order: ``stock`` (most version-stable) → ``exe`` / ``app`` /
``fileassoc`` → ``dll`` (last resort). No code change is required; the same name
resolves correctly on every Windows version because the target does the
resolution.

Verifying coverage (debug dump)
===============================

Against a connected target you can resolve **every** registry term at once and
produce PNGs plus an HTML contact sheet — handy for eyeballing coverage and
confirming version-independence across Win10/Win11:

.. code-block:: console

   $ adare icons dump-all --host <target-ip> --os-key windows11
   ...
   Dumped 101/103 icons for os_key='windows11'
   Contact sheet: ~/.adare/icons/windows11/index.html

Open ``index.html`` to see each name, its rendered icon, its resolver spec, and
success/failure. Use ``--force`` to re-extract even when cached. Running the
same command against a Win10 target writes to a separate ``windows10`` cache
directory with no code change.

Requirements & caveats
=======================

* **Windows targets only.** Extraction uses Win32 shell APIs. The
  ``fileassoc``/``app`` strategies additionally depend on the relevant
  association or ``App Paths`` entry existing on that machine (e.g. ``chrome``
  resolves only if Chrome is installed).
* **Agent mode.** Extraction goes over the ``adarevm`` WebSocket agent, so the
  agent must be running on the target. (Pure host-mode/QGA runs do not extract
  icons.)
* **First use hits the target.** The first reference of a name extracts and
  caches it; subsequent runs are served from cache. Delete the cache directory
  (or use ``--force`` with ``dump-all``) to force re-extraction.
* **Installation.** ``icon-library.yml`` ships in ``appdata/`` and is installed
  alongside the OS profiles; when running from a source checkout it is picked up
  automatically.

See also
========

* :doc:`../reference/cli` — the ``adare icons`` commands
* :doc:`../architecture/cv-server` — the matcher the resolved PNG flows into
