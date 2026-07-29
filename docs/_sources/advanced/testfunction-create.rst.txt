********************************************************
Create your own testfunction set
********************************************************

This guide explains how to create custom test functions for ADARE to extend its testing capabilities beyond the built-in test function collections.

Quick Start
============

The fastest way to create a test function is with the ``@testfunction`` decorator:

.. code-block:: python

   # /path/to/your/testfunctions/mycollection/mycollection.py
   from adarelib.testset.api import testfunction
   from adarelib.testset.basictest import HostModeCategory

   @testfunction(
       name='file_contains_word',
       description='tests if file content contains specified word',
       category=HostModeCategory.FILE_BASED,
   )
   def file_contains_word(ctx, dst: str, word: str, case_sensitive: bool = True):
       dst_path, status = ctx.resolve_globfilepath(dst)
       ctx.error_if(not dst_path, f'File {dst} not found ({status})')

       with open(dst_path, 'r', encoding='utf-8') as f:
           content = f.read()

       search_word = word
       if not case_sensitive:
           content = content.lower()
           search_word = word.lower()

       ctx.fail_if(search_word not in content, f'Word "{word}" not found in file')
       return f'Word "{word}" found in file'

That's it. The decorator automatically generates the Parameter class and BasicTest subclass from the function signature. Parameters are extracted from the function arguments (excluding ``ctx``), with type annotations used for validation.

Loading and Using Custom Test Functions
---------------------------------------

Create your test function collection in a directory:

.. code-block:: bash

   mkdir /path/to/your/testfunctions/mycollection
   touch /path/to/your/testfunctions/mycollection/mycollection.py
   touch /path/to/your/testfunctions/mycollection/requirements.txt

.. important::

   The ``.py`` file **must be named exactly like its directory**
   (``mycollection/mycollection.py``). A collection is loaded from
   ``<dir>/<dir>.py``; if the names differ, the directory is skipped on load
   (``adare test validate`` warns about this — see below).

Validate the collection offline first (no VM required):

.. code-block:: bash

   adare test validate /path/to/your/testfunctions/mycollection

Load into ADARE:

.. code-block:: bash

   adare test load /path/to/your/testfunctions/mycollection

Use in a playbook:

.. code-block:: yaml

   tests:
     - name: check_for_keyword
       function: mycollection.file_contains_word
       parameter:
         dst: "/evidence/logfile.txt"
         word: "ERROR"
         case_sensitive: false


Updating a Library
------------------

To change a loaded library, edit its source and re-load it — there is no
separate ``update`` command:

.. code-block:: bash

   # edit /path/to/your/testfunctions/mycollection/mycollection.py
   adare test validate /path/to/your/testfunctions/mycollection
   adare test load     /path/to/your/testfunctions/mycollection

``adare test load`` now **refreshes the loaded copy** and **bumps the version**
whenever the content changed. (Previously this was a silent no-op: the file was
only copied if it did not already exist, so edits to an already-loaded library
never propagated.) A load that finds no changes leaves the version untouched.

Each changed method's version is bumped independently, and the whole collection
(file) gets its own version number too. A method that you remove from the source
is **not deleted** — it is marked *not current* so experiments that referenced it
still resolve; new experiments simply can't bind it anymore. If you later add the
method back under the same name, it is reactivated (same identity, next version).


Versioning and Reproducibility
------------------------------

ADARE treats a testfunction's **identity** (its ``collection.function``
dotnotation, backed by a stable internal id) separately from its **version**:

- **Identity is stable.** Updating a library never changes the identity an
  experiment is bound to, so prior experiments never end up with dangling
  references.
- **Versions are immutable and retained.** Every content change appends a new
  version (``v1``, ``v2``, …) and keeps an on-disk snapshot under
  ``<state>/testfunctions/<name>/versions/v<N>/``. Old versions are **never
  pruned** — snapshots are cheap ``.py`` files and this is a forensic tool.

Inspect the history:

.. code-block:: bash

   adare test versions mycollection                     # file (collection) history
   adare test versions mycollection.file_contains_word  # per-method history

The current version is also shown by ``adare test list`` and ``adare test info``.

**Reproducibility = drift detection.** When an experiment is created, ADARE pins
the collection version + hash and the method version + hash it was built against.
Every run records the file name + file version/hash and method version/hash of
the code that **actually executed**, so a report reads e.g. *"used mycollection
@ v3"*.

.. important::

   ADARE **always executes the current code**. It does **not** re-run an old
   version. If the current code has drifted from the version an experiment was
   created against, the run emits a loud warning naming the pinned vs current
   versions and stamps the executed version/hash onto the run — but it still
   runs and reports with the current code. Re-running historical code is out of
   scope (the retained snapshots make it a possible future addition).


Core Concepts
==============

TestContext (ctx)
-----------------

Every decorated test function receives ``ctx`` as its first argument. This is a ``TestContext`` instance that provides:

**Assertion methods:**

- ``ctx.fail_if(condition, message)`` — Fail the test if condition is truthy
- ``ctx.error_if(condition, message)`` — Error the test if a precondition/setup fails

**File resolution:**

- ``ctx.resolve_globfilepath(path, match_mode="single", return_list=False)`` — Resolve glob patterns to file paths

**Placeholder/variable support:**

- ``ctx.has_placeholders(text)`` — Check if text contains ``{{PLACEHOLDER}}`` variables
- ``ctx.get_placeholders(text)`` — Extract placeholder names from text
- ``ctx.resolve_variables(text)`` — Resolve placeholder variables in text
- ``ctx.compare_with_placeholder(name, actual)`` — Compare actual value against placeholder (supports regex, timestamp tolerance)
- ``ctx.handle_placeholders_comparison(actual, template)`` — Full template comparison with multiple placeholders

**Metadata:**

- ``ctx.variable_metadata`` — Access the variable metadata dict
- ``ctx.get_placeholder_metadata(name)`` — Get metadata for a specific placeholder
- ``ctx.has_tolerance_metadata(name)`` — Check if placeholder has tolerance settings

Return Values
-------------

Test functions can return values in several ways:

.. code-block:: python

   # Return None → TestResult.success([])
   def my_test(ctx, dst: str):
       pass

   # Return a string → TestResult.success([string])
   def my_test(ctx, dst: str):
       return 'file found'

   # Return a list → TestResult.success(list)
   def my_test(ctx, dst: str):
       return ['found 3 files', 'all valid']

   # Return TestResult directly → passed through
   def my_test(ctx, dst: str):
       return TestResult.success(['custom result'])

   # Pass, but flag something noteworthy → reported as WARNING, not FAILED
   def my_test(ctx, dst: str):
       return TestResult.warning(['passed, but the file was nearly empty'])

``TestResult.warning([...])`` is a *pass-with-warning*: it does not fail the
experiment verdict, but is reported distinctly from a plain success (and never
counted as a failure).

Use ``ctx.fail_if()`` and ``ctx.error_if()`` for failure/error conditions — they raise exceptions that the decorator catches and converts to the appropriate ``TestResult``.

Uncaught exceptions are automatically converted to ``TestResult.execution_error()``.

Parameters
----------

Parameters are derived from the function signature:

.. code-block:: python

   @testfunction(name='my_test', description='example')
   def my_test(ctx, path: str, count: int = 5, regex: bool = False):
       ...

This generates a parameter class with fields: ``path`` (required str), ``count`` (optional int, default 5), ``regex`` (optional bool, default False).

Type annotations are used for cattrs structuring from YAML playbooks. Always annotate your parameters.

Category
--------

The ``category`` argument to ``@testfunction`` indicates where the test executes:

- ``HostModeCategory.FILE_BASED`` — Tests files on the analyzed system
- ``HostModeCategory.FILE_CONTENT`` — Tests file contents
- ``HostModeCategory.QGA_PROBE`` — Tests via QEMU Guest Agent
- ``HostModeCategory.AGENT_ONLY`` — Tests that run only in the agent (default)
- ``HostModeCategory.HOST_NATIVE`` — Tests that execute on the host machine


Host-Based Tests
=================

Some tests execute on the host machine rather than the analyzed system — for example, visual tests that take screenshots and perform image recognition. These use ``async def`` and access host services through ``ctx.host``.

.. code-block:: python

   from adarelib.testset.api import testfunction
   from adarelib.testset.basictest import HostModeCategory

   @testfunction(
       name='visual.exists',
       description='Check if text or image is visible on screen',
       category=HostModeCategory.HOST_NATIVE,
       execute_on_host=True,
   )
   async def visual_exists(ctx, text: str = None, image: str = None, window: str = None):
       ctx.error_if(not text and not image, "Either text or image parameter required")

       screenshot = await ctx.host.screenshot.take(window=window)

       if text:
           locations = await ctx.host.cv.find_text(text, screenshot)
       else:
           image_path = Path(image)
           locations = await ctx.host.cv.find_icon(image_path, screenshot)

       ctx.fail_if(not locations, f'target not found on screen')

Key differences from regular tests:

- Use ``async def`` for the test function
- Set ``execute_on_host=True`` in the decorator
- Access host services via ``ctx.host`` (provides ``screenshot``, ``cv``, ``playbook_dir``, ``vm_file``)
- The decorator auto-detects async functions and generates the appropriate ``async def test()`` method


Advanced
=========

Module-Level Helper Functions
-----------------------------

For shared logic across multiple test functions, extract helpers as module-level functions:

.. code-block:: python

   def _parse_xml(filepath):
       """Parse XML file and return root element."""
       tree = ET.parse(filepath)
       return tree.getroot()

   def _compare_values(ctx, actual, expected, regex_match=False):
       """Compare values with placeholder/regex support."""
       if ctx.has_placeholders(str(expected)):
           placeholders = ctx.get_placeholders(str(expected))
           return ctx.compare_with_placeholder(placeholders[0], str(actual))
       elif regex_match:
           pattern = re.compile(expected)
           return pattern.search(str(actual)) is not None, f'regex {"matched" if match else "no match"}'
       else:
           return actual == expected, f'{"matched" if actual == expected else "mismatch"}'

   @testfunction(name='element_exists', description='...', category=HostModeCategory.FILE_CONTENT)
   def element_exists(ctx, dst: str, xpath: str):
       root = _parse_xml(dst)
       ...

   @testfunction(name='element_text', description='...', category=HostModeCategory.FILE_CONTENT)
   def element_text(ctx, dst: str, xpath: str, expected: str, regex_match: bool = False):
       root = _parse_xml(dst)
       ...
       is_match, message = _compare_values(ctx, actual_text, expected, regex_match)
       ...

Helpers that need placeholder/variable support receive ``ctx`` as their first argument. Pure computation helpers (parsing, formatting) don't need ``ctx``.

Placeholder and Variable Support
---------------------------------

ADARE supports dynamic values through the placeholder system. Placeholders like ``{{TIMESTAMP}}`` in expected values are resolved using variable metadata:

.. code-block:: python

   @testfunction(name='check_value', description='...', category=HostModeCategory.FILE_CONTENT)
   def check_value(ctx, dst: str, expected: str):
       actual = read_value_from_file(dst)

       if ctx.has_placeholders(expected):
           placeholders = ctx.get_placeholders(expected)
           if len(placeholders) == 1:
               success, message = ctx.compare_with_placeholder(placeholders[0], actual)
               ctx.fail_if(not success, message)
           else:
               success, message = ctx.handle_placeholders_comparison(actual, expected)
               ctx.fail_if(not success, message)
       else:
           ctx.fail_if(actual != expected, f'Expected "{expected}", got "{actual}"')

Legacy Class-Based Approach
----------------------------

For advanced use cases, you can still create test functions using the traditional class-based pattern:

.. code-block:: python

   import attrs
   from typing import ClassVar, Optional

   from adarelib.testset.basictest import BasicTest, Parameter
   from adarelib.event.event import TestResult

   @attrs.define
   class MyTestParameter(Parameter):
       input_field: str
       optional_field: Optional[int] = None

   @attrs.define
   class MyTest(BasicTest):
       testname: ClassVar[str] = 'my_test'
       testdescription: ClassVar[str] = 'Description of what this test does'

       name: str
       parameter: MyTestParameter
       description: Optional[str] = ''
       variable_metadata: Optional[dict] = None

       def test(self):
           # self.parameter.input_field, self.resolve_globfilepath(), etc.
           return TestResult.success()

The decorator approach is preferred for new test functions as it eliminates boilerplate while providing the same capabilities.


Module Organization
====================

Directory Structure
-------------------

.. code-block::

   /path/to/your/testfunctions/
   ├── mycollection/
   │   ├── mycollection.py      # Test functions
   │   └── requirements.txt     # Python dependencies
   └── anothercollection/
       ├── anothercollection.py
       └── requirements.txt

Dependencies
------------

List additional Python packages in ``requirements.txt``:

.. code-block:: text

   # requirements.txt
   lxml>=4.9.0
   requests>=2.28.0

When you run ``adare test load``, a non-empty ``requirements.txt`` is installed
into ADARE's interpreter (via ``uv pip install``, falling back to ``pip``). If
installation fails, ``load`` stops with an actionable error listing the exact
command to run manually — dependencies are resolved **at load time**, not
silently deferred to run time.

Validating and Dry-Running
---------------------------

Two commands let you check a collection offline before wiring it into an
experiment:

.. code-block:: bash

   # Report every authoring-contract violation (missing ctx, unannotated params,
   # duplicate testnames, filename≠dirname, import/dependency errors):
   adare test validate /path/to/testfunctions/mycollection

   # Execute one test against a local sample file (no VM):
   adare test dry-run mycollection.file_contains_word \
       --path /path/to/testfunctions/mycollection \
       --file ./sample.txt --param word=ERROR

``dry-run`` structures ``--param key=value`` pairs through the same cattrs path
used for playbooks, sets ``--file`` as the ``dst`` parameter, runs the test, and
prints the resulting ``TestResult``. It supports ``FILE_BASED`` / ``FILE_CONTENT``
tests only — host/async and QGA tests need a live ``ctx.host`` / guest and are
out of scope for the offline harness.

A copyable starter collection lives at ``examples/testfunctions/example/`` —
copy it (the built-in collections under ``appdata/testfunctions/`` are
integrity-protected and not meant to be edited in place), rename the directory
**and** its ``.py`` file to match, then ``validate`` and ``load``.


Real-World Example
===================

Here's a complete example testing a JSON API response:

.. code-block:: python

   # /path/to/your/testfunctions/api/api.py
   import requests
   import json
   from adarelib.testset.api import testfunction
   from adarelib.testset.basictest import HostModeCategory
   from adarelib.event.event import TestResult

   @testfunction(
       name='api_response',
       description='tests API endpoint response and JSON content',
       category=HostModeCategory.AGENT_ONLY,
   )
   def api_response(ctx, url: str, expected_status: int = 200,
                    expected_json_key: str = None, expected_json_value: str = None,
                    timeout_seconds: int = 30):
       try:
           response = requests.get(url, timeout=timeout_seconds)
       except requests.RequestException as e:
           return TestResult.execution_error(e, f"HTTP request failed for {url}")

       ctx.fail_if(
           response.status_code != expected_status,
           f'HTTP status mismatch. Expected: {expected_status}, Got: {response.status_code}'
       )

       if expected_json_key:
           try:
               json_data = response.json()
           except json.JSONDecodeError as e:
               return TestResult.execution_error(e, "Response is not valid JSON")

           ctx.fail_if(
               expected_json_key not in json_data,
               f'JSON key "{expected_json_key}" not found'
           )

           if expected_json_value:
               actual = str(json_data[expected_json_key])
               if ctx.has_placeholders(expected_json_value):
                   success, message = ctx.handle_placeholders_comparison(actual, expected_json_value)
                   ctx.fail_if(not success, f'JSON value comparison failed: {message}')
               else:
                   ctx.fail_if(actual != expected_json_value,
                               f'JSON value mismatch. Expected: {expected_json_value}, Got: {actual}')

       return [f'API response valid: HTTP {response.status_code}',
               f'Response size: {len(response.content)} bytes']

Usage in playbook:

.. code-block:: yaml

   tests:
     - name: check_api_status
       function: api.api_response
       parameter:
         url: "https://api.example.com/status"
         expected_status: 200
         expected_json_key: "status"
         expected_json_value: "healthy"
         timeout_seconds: 10


Best Practices
===============

- **Use** ``ctx.fail_if()`` **and** ``ctx.error_if()`` for clean assertion-style logic
- **Always use** ``ctx.resolve_globfilepath()`` for file paths
- **Consider placeholder support** for values that may be dynamic
- **Keep test functions focused** — one test, one purpose
- **Use module-level helpers** for shared logic across tests
- **Handle platform differences** gracefully with ``platform.system()`` checks
- **Set reasonable timeouts** for network operations
- **Use structured logging** via ``logging.getLogger(__name__)``
