Checking that something is absent
=================================

Many findings are absences: a setting was *not* written, a deleted entry is *gone*, a
private-mode session left *no* trace. ADARE has no ``*_absent`` twin for every test
function. Absence is written with the test functions you already use, in one of two ways.

Count zero
----------

Every count function takes ``expected_count``; ``0`` means "none":

.. code-block:: yaml

   tests:
     - name: no_entry_for_example_org
       function: json.value_count
       parameter:
         dst: /home/user/.config/app/store.jsonlz4!
         key_path: entries[*].url
         expected_value: https://example.org/
         expected_count: 0

     - name: token_not_in_cache
       function: text.occurrence_count
       parameter:
         dst: /home/user/.cache/app/data.bin
         content: secret-token
         encodings: [utf-8, utf-16-le]
         expected_count: 0

Count functions: ``json.value_count``, ``plist.value_count``, ``yaml.value_count``,
``toml.value_count``, ``ini.value_count``, ``image.png_text_count``,
``image.exif_value_count``, ``text.occurrence_count``, ``text.line_count``,
``csv.line_count``, ``jsonl.line_count``, ``xml.element_count``, and
``sqlite.query_result`` with ``expected_rows: 0``. Without ``expected_value`` the
structured counts count the values at the key path, so ``0`` means the key is absent.

``expect_to_fail``
------------------

Any presence test can be inverted with ``expect_to_fail: true``:

.. code-block:: yaml

   tests:
     - name: key_was_not_written
       function: ini.contains_key
       parameter:
         dst: /home/user/.config/app/settings.ini
         section: General
         key: lastFile
       expect_to_fail: true

``expect_to_fail`` swaps only SUCCESS and FAILED. Prefer the count form when one exists:
it says what is counted and reads the same in the result.

Why ERROR never becomes a pass
------------------------------

A test reports **FAILED** only when it read the file and the content does not match.
A missing file, a glob that matches no file or several, a corrupt or unreadable file and
bad parameters are **ERROR** — the test never saw the evidence. ``expect_to_fail`` leaves
ERROR as ERROR, and ``expected_count: 0`` on a missing file is ERROR, not "zero found".
Otherwise a typo in a path, a file in an unexpected place or a failed pull in host mode
would pass every absence check. To assert that a *file* is absent, use
``standard.file_does_not_exist``; it is the one test for which a missing path is the
finding.

Proof of the act
----------------

An absence passes just as well when the action that should have caused it never took
effect. Count-zero tests, ``*_does_not_exist`` and ``expect_to_fail`` tests are all
*negative* tests: ADARE reports a passing one as INCONCLUSIVE when an earlier GUI action
failed, and with ``effect_check: prove`` also when one was skipped or showed no effect.
See :doc:`negative-results`.
