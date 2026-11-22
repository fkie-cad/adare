log_entry_exists
================

.. role:: status-dev
   :class: status-dev

:Status: :status-dev:`● Development`
:Category: Linux System (file content, works in host mode)
:Function Name: ``log_entry_exists``

**Tests if one of the last lines of a text log contains a string or matches a regex.**

Reads the last ``max_lines`` lines of a plain-text log (syslog, ``auth.log``, application
logs) and passes when at least one line matches ``content``. It is a file-content test: the
file is read directly (no ``grep``), so it also runs in host mode against a mounted disk
image, and a rotated, compressed log is read through the archive separator. The binary
systemd journal is not a text log; use a ``journalctl`` export instead.

To count entries, or to search the whole file instead of its tail, use
:doc:`../text/line_count`.

.. note::

   Renamed parameters: ``log_file`` is now ``dst`` and ``pattern`` is now ``content``.
   A playbook that still uses the old names is rejected with a "was renamed" message.
   ``content`` is a regex by default (``regex_match: true``, Python ``re.search``), no
   longer a ``grep`` pattern.

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``dst``
     - string
     - **Required.** Path of the log. A glob must match exactly one file;
       ``archive!member`` reads a rotated, compressed log (``/var/log/syslog.2.gz!``).
       A missing file is an ERROR. The encoding is detected (BOM, UTF-16, else UTF-8);
       undecodable bytes are replaced, so binary garbage does not stop the search.
   * - ``content``
     - string
     - **Required.** With ``regex_match`` (default) a Python regex searched in each line
       (``re.search``, case-sensitive; ``(?i)`` for case-insensitive); an invalid regex is
       an ERROR. Otherwise a substring a line must contain.
   * - ``regex_match``
     - boolean
     - **Optional.** ``true`` (default): ``content`` is a regex; ``false``: a plain substring.
   * - ``max_lines``
     - integer
     - **Optional.** How many trailing lines to search. Default: ``1000``; must be positive.

Usage Example
-------------

Basic Log Search
~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: session_opened_logged
       function: linux.log_entry_exists
       parameter:
         dst: /var/log/auth.log
         content: 'session opened for user alice'
       description: "The login left a trace in auth.log"

Plain Substring
~~~~~~~~~~~~~~~

Characters such as ``.``, ``(`` or ``[`` are regex syntax; switch the regex off to search
them literally:

.. code-block:: yaml

   tests:
     - name: file_name_logged
       function: linux.log_entry_exists
       parameter:
         dst: /home/user/.local/share/app/app.log
         content: 'opened report (final).odt'
         regex_match: false
         max_lines: 500

Regex and Rotated Logs
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: ssh_login_in_rotated_log
       function: linux.log_entry_exists
       parameter:
         dst: /var/log/auth.log.2.gz!
         content: 'sshd\[\d+\]: Accepted password for \w+'
         max_lines: 5000

     - name: app_error_case_insensitive
       function: linux.log_entry_exists
       parameter:
         dst: /var/log/app/app.log
         content: '(?i)authentication failed'

Absence
~~~~~~~

``expect_to_fail: true`` asserts that no recent line matches. A missing log is still an
ERROR, never a pass. For "no line in the whole file" use ``text.line_count`` with
``expected_count: 0``.

.. code-block:: yaml

   tests:
     - name: no_crash_logged
       function: linux.log_entry_exists
       expect_to_fail: true
       parameter:
         dst: /var/log/app/app.log
         content: 'Segmentation fault'

Common Use Cases
----------------

**System Event Validation**
  Verify that an action left a trace in a system log (logins, sudo, package installs)

**Application Logging**
  Check that an application logged an opened file, an error or a sync

**Rotated Logs**
  Search a compressed, rotated log through ``archive!member``

Return Values
-------------

**Success**
  At least one of the last ``max_lines`` lines matches ``content``.

**Failure**
  No line among the searched lines matches.

**Error**
  The log does not exist, a glob matches none or several files, ``dst`` is a directory,
  ``content`` is an invalid regex, ``max_lines`` is not positive, or the file cannot be read.

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success
   details:
     - "found 2 log entries matching 'session opened for user alice' in /var/log/auth.log"
     - "first: Nov  2 10:14:03 host sshd[811]: pam_unix(sshd:session): session opened for user alice"

   # Failure case
   result: failed
   details:
     - "no log entry matching 'Segmentation fault' in the last 1000 line(s) of /var/log/app/app.log"

   # Error case - file not found
   result: error
   details:
     - "log file /var/log/missing.log does not exist"

See Also
--------

* :doc:`../text/line_count` - count matching lines in the whole file
* :doc:`../text/occurrence_count` - occurrences in any file, binary included
* :doc:`../standard/file_content_matches_regex` - a regex anywhere in a file
* :doc:`/guide/archives` - files inside archives and compressed files
