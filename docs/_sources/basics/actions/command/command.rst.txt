command
=======

Execute shell commands on the guest VM with support for output capture, elevated privileges, and variable substitution.

Usage Examples
--------------

**Simple Command**

.. code-block:: yaml

   actions:
     - command:
         command: "mkdir -p /evidence/case_001"
         shell: true
         description: "Create evidence directory"

**Capture Output**

.. code-block:: yaml

   actions:
     - command:
         command: "whoami"
         capture:
           variable: current_user
         description: "Get current username"

     - command:
         command: "echo '{{ current_user }}'"
         description: "Use captured variable"

**Parse Output**

.. code-block:: yaml

   actions:
     - command:
         command: "echo '42'"
         capture:
           variable: count
           parser: "int(output.strip())"
         description: "Capture and parse integer"

**Elevated Privileges**

.. code-block:: yaml

   actions:
     - command:
         command: "msi /i Tool.msi /quiet"
         admin: true
         description: "Install with administrator rights"

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``command``
     - string
     - Shell command to execute (required)
   * - ``shell``
     - boolean
     - Execute in shell context (default: false)
   * - ``capture``
     - CaptureSpec
     - Capture command output to variable
   * - ``admin``
     - boolean
     - Run with elevated privileges (default: false)
   * - ``cwd``
     - string
     - Working directory for command execution
   * - ``env``
     - dict
     - Environment variables
   * - ``timeout``
     - float
     - Command timeout in seconds
   * - ``allow_failure``
     - boolean
     - Continue on non-zero exit code (default: false)
   * - ``description``
     - string
     - Human-readable description (optional)

Capture Specification
----------------------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``variable``
     - string
     - Variable name to store output (required)
   * - ``source``
     - string
     - Output source: ``stdout`` (default), ``stderr``, ``returncode``, ``all``
   * - ``parser``
     - string
     - Python expression to parse output (e.g., ``int(output)``, ``json.loads(output)``)

Notes
-----

- Commands support Jinja2 variable substitution
- Parser expressions have access to: ``output``, ``json``, ``re``, ``str``, ``int``, ``float``
- Use ``shell: true`` for commands with pipes, redirects, or wildcards
- Captured variables available in subsequent actions and flow control

See Also
--------

- :doc:`../variable/save_variable` for storing computed values
- :doc:`../flow/stop` for conditional execution based on command output
- :doc:`../flow/continue` for skipping iterations based on output
