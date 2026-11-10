Proving negative results
========================

A test for an absent artifact cannot by itself separate "the application did not store
it" from "the action that should have produced it never took effect". A click counts as
done once its input is sent, and a ``when:`` that is false skips its step silently. ADARE
therefore checks the effect of every GUI action automatically and records it. With
``effect_check: prove`` it also judges negative tests on that evidence. The default
(``warn``) costs playbook authors nothing and changes no verdict.

.. list-table::
   :widths: 35 20 45
   :header-rows: 1

   * - Layer
     - Written by
     - Proves
   * - Automatic effect check of each GUI action
     - nobody (default)
     - Weak: something changed on screen where the input went
   * - Implicit control for negative tests
     - nobody (verdict logic)
     - Every earlier GUI action ran and passed its ``verify:``; under ``prove`` also
       was not skipped and showed an effect
   * - ``verify:`` on an action (generated when recording)
     - the recorder, or the author
     - Medium: the expected screen state appeared
   * - ``controls:`` on a test
     - the author (optional)
     - Strong: the effect itself, observed outside the application

Automatic effect check
----------------------

After each ``click``, ``keyboard``, ``drag``, ``scroll`` and ``goto`` ADARE compares the
screen before and after the action, **only in a region around it**, so a taskbar clock or
an animation elsewhere does not count:

- click, goto, drag: a box (a quarter of the screen) around the input point(s)
- scroll: the box of the last pointer action
- keyboard: the full screen without its edges (panels, clock), since keys go wherever the
  focus is and shortcuts open and close dialogs away from the last click

Change is polled for up to one second (``ADARE_EFFECT_TIMEOUT`` overrides it), so a slow
redraw is not missed. The frame target resolution already took is reused as the "before"
frame; the check adds one screenshot and a pixel diff per poll, no OCR. The result is
stored in the action's event data and the forensic log as ``effect: changed``,
``unchanged`` or ``unknown``. For ``unchanged`` a WebP screenshot
(``reporting/screenshots/effect_unchanged_*.webp``) is kept as evidence.

.. code-block:: yaml

   settings:
     effect_check: warn   # off | warn (default) | prove | strict

- ``warn``: record the effect, keep the evidence and count ``unchanged`` actions in the run
  summary ("N GUI action(s) showed no screen change"). No verdict changes.
- ``prove``: also hold ``unchanged`` and ``when:``-skipped actions against later negative
  tests (see below).
- ``strict``: ``prove``, and an ``unchanged`` action fails its step.

Mark an action that is expected to change nothing with ``effect: none`` before switching a
playbook to ``prove`` or ``strict``. Real playbooks have many: on three T2F playbooks
(Firefox, LibreOffice, Chrome) 7-29 % of GUI actions rightly changed nothing, all of them
idempotent steps such as a wake key, a focus click on a focused window, ``ctrl+a`` on text
that is already selected, ``ctrl+l`` into a focused address bar, or expanding a node that is
already open. That is why ``warn`` is the default.

The check is weak on purpose: a hover highlight or a blinking caret near the input also
counts as a change. It catches the clear failures (a click on empty desktop, a key sent to
a window that ignores it), not a wrong but visible effect.

INCONCLUSIVE negative tests
---------------------------

These tests are *negative*:

- ``*_does_not_exist`` (e.g. ``standard.file_does_not_exist``)
- ``visual.not_exists``
- ``visual.count_max`` with ``max: 0``
- any test with ``expect_to_fail: true``
- any testfunction declared with ``@testfunction(..., negative=True)``

A negative test that passes is reported **INCONCLUSIVE** (status 15) instead of SUCCESS
when any GUI action before it in the run

- failed, or failed its ``verify:``,
- (``prove``/``strict`` only) was skipped by a ``when:`` condition (an action or a block),
- (``prove``/``strict`` only) reported ``effect: unchanged`` (and is not marked
  ``effect: none``),

or when one of its ``controls:`` did not pass before it.

The result details list the actions and controls responsible. Positive tests are never
affected by the implicit check. INCONCLUSIVE does not stop the run. The run verdict takes
FAILED first, then INCONCLUSIVE, then TEST_MISSING, then WARNING or SUCCESS. The server
and both web UIs show it as its own badge.

Explicit controls
-----------------

``controls:`` names tests that must have passed earlier in the run for a test's result to
count. Use it for proof outside the UI, for example that the file existed before the GUI
deleted it:

.. code-block:: yaml

   tests:
     - name: file_present_before
       function: standard.file_exists
       parameter: {dst: "{{ file_path }}"}
     - name: file_is_deleted
       function: standard.file_does_not_exist
       parameter: {dst: "{{ file_path }}"}
       controls: [file_present_before]

   actions:
     - test: file_present_before
     # ... GUI actions that delete the file ...
     - test: file_is_deleted

``adare exp playbook validate`` reports a control that is not defined, never runs, runs
after the test it controls, or forms a cycle. On a positive test, ``controls:`` counts too
(only the controls, not the implicit action check). See
``templates/idioms/delete_file_and_verify.play.yaml`` for a complete example.

Generated checks when recording
-------------------------------

When a playbook is recorded (``adare dev agent``, ``adare dev mcp``), the recorder compares
the screen before each click or keyboard step with the screen after it. The region that
changed (if it is large enough, away from the screen edges, and settled) is saved as an
image and emitted as ``verify: {exists: {image: step_NNN_effect.png}}`` on the step. With
``--plan``, each verified sub-goal also ends in a ``wait_until`` on the screen state it
reached, described by the planner's "done when ..." statement.

Host-mode file reads
--------------------

When tests read guest files through the QEMU guest agent (``--gui-mode host``) or a disk
image (``--backend hostside``), only a real "no such file" answer counts as absent. Any
other failure (guest agent unreachable, timeout, permission) makes the test ERROR, so an
absence test can no longer pass on a transport error.
