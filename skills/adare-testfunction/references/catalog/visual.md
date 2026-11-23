# Visual (`visual.*`)

<!-- Generated; do not edit by hand. -->

What the guest's screen shows: a text, an icon from the icon library or a template image is visible, not visible, or visible a given number of times. The checks run on the host: they take one fresh screenshot of the running guest and search it with the CV server (OCR for text, template and feature matching for icons and images). They see only the screen; state that is not shown (a file on disk, a saved setting) needs a file, registry or system test.

## `visual.count_equals`

Check if text or image appears exactly N times on screen

Pass when the text, icon or image is found exactly `n` times on the screenshot.

**Use for:** counting visible items (e.g. 3 files on the desktop). Icon/image matches are capped at 10 by the CV call, so counts above 10 cannot be observed.

asserts: ui, count, absent · formats: screen · runs: host, against the live VM screen; not hostside; no dry-run · os: any

**Supports:** Negative tests (absence) (`negative`)

**Does not support:**
- Counts with a comparison (`count_comparison`): Takes `n` (exact); there is no `expected_count` / `comparison_type`: use visual.count_min or visual.count_max for bounds.

**Not for:**
- how many files are in a folder → `standard.file_count`
- at least or at most a number of matches → `visual.count_min`

| parameter | type | default | description |
|---|---|---|---|
| text | `str` | `None` | OCR search string: case-insensitive substring of a single OCR text box (a phrase split across boxes may not match). Wins over `icon` and `image`. |
| image | `str` | `None` | Template PNG on the HOST, relative to the playbook directory (or absolute); matched with the CV server's icon pipeline. A missing file is an execution error. |
| icon | `str` | `None` | Name from the icon library (`appdata/icon-library.yml`, e.g. `recycle_bin`, `folder`), extracted from the target on first use; needs a connected agent. Used when `text` is empty; wins over `image`. |
| window | `str` | `None` | Capture only the first window whose title matches this search string (Linux guests; Windows currently captures the full screen). `None` = full screen; no matching window is an execution error. |
| n | `int` | `None` | Required exact number of matches (`None` -> error). |

**Outcomes:**
- PASSED: the text, icon or image is found exactly `n` times (`n: 0`: not at all; a negative test, INCONCLUSIVE without proof of the act)
- FAILED: the screenshot was searched and the number of matches differs
- ERROR: none of `text`, `icon`, `image` is given, or `n` is missing
- ERROR: the `image` file does not exist on the host; the `icon` name is unknown or cannot be extracted
- ERROR: no window matches `window`; the screenshot or the CV server fails

**Limits:**
- `n: 0` is a negative test: a pass only means "not visible now" and is INCONCLUSIVE when a GUI action before it failed or failed its `verify:` (under `effect_check: prove` also a skipped or unchanged one), or when a `controls:` test did not pass. Prove the act with an earlier visual.exists as a control (see visual.not_exists). With `expect_to_fail` it asserts presence and is not negative.
- Icon and image matches are capped at 10, so a count above 10 cannot be observed (`n: 11` never passes).
- Text counts OCR text boxes that contain the string: two occurrences in one box count once, and OCR may merge neighbouring words into one box.
- Overlapping icon matches are merged, but a similar-looking icon nearby can add a match: prefer a small `window` or a distinctive template.
- Text, icon, image, precedence and `window` as in visual.exists; the hostside backend cannot run it.

**Use cases:**
- Visible items: Three file icons on the desktop after a copy.

**Examples:**

*three document icons* → PASSED

```yaml
tests:
- name: three_document_icons
  function: visual.count_equals
  parameter:
    image: icons/odt_file.png
    n: 3
```

*one tab with a title* → PASSED

```yaml
tests:
- name: one_tab_with_a_title
  function: visual.count_equals
  parameter:
    text: Untitled
    n: 1
```

*none left, as a negative test* → PASSED. Pair it with a control (`controls:`) that proves the file icon was there before the delete.

```yaml
tests:
- name: none_left_as_a_negative_test
  function: visual.count_equals
  parameter:
    image: icons/odt_file.png
    n: 0
```

*without n it is an error* → ERROR

```yaml
tests:
- name: without_n_it_is_an_error
  function: visual.count_equals
  parameter:
    icon: folder
```

**Related:**
- `visual.not_exists`: the same as `n: 0`, and clearer

## `visual.count_max`

Check if text or image appears at most N times on screen

Pass when the text, icon or image is found at most `max` times on the screenshot.

**Use for:** "no more than N items visible"; `max: 0` behaves like visual.not_exists. Icon/image matches are capped at 10 by the CV call, so counts above 10 cannot be observed.

asserts: ui, count, absent · formats: screen · runs: host, against the live VM screen; not hostside; no dry-run · os: any

**Supports:** Negative tests (absence) (`negative`)

**Does not support:**
- Counts with a comparison (`count_comparison`): Takes `max` (inclusive); there is no `expected_count` / `comparison_type`.

**Not for:**
- a file count stays below a limit → `standard.file_count`

| parameter | type | default | description |
|---|---|---|---|
| text | `str` | `None` | OCR search string: case-insensitive substring of a single OCR text box (a phrase split across boxes may not match). Wins over `icon` and `image`. |
| image | `str` | `None` | Template PNG on the HOST, relative to the playbook directory (or absolute); matched with the CV server's icon pipeline. A missing file is an execution error. |
| icon | `str` | `None` | Name from the icon library (`appdata/icon-library.yml`, e.g. `recycle_bin`, `folder`), extracted from the target on first use; needs a connected agent. Used when `text` is empty; wins over `image`. |
| window | `str` | `None` | Capture only the first window whose title matches this search string (Linux guests; Windows currently captures the full screen). `None` = full screen; no matching window is an execution error. |
| max | `int` | `None` | Allowed maximum number of matches, inclusive (`None` -> error). |

**Outcomes:**
- PASSED: the text, icon or image is found at most `max` times (`max: 0`: not at all)
- FAILED: the screenshot was searched and more than `max` matches are found
- ERROR: none of `text`, `icon`, `image` is given, or `max` is missing
- ERROR: the `image` file does not exist on the host; the `icon` name is unknown or cannot be extracted
- ERROR: no window matches `window`; the screenshot or the CV server fails

**Limits:**
- Icon and image matches are capped at 10: with `max` 10 or more the test cannot fail for them.
- `max: 0` is a negative test: INCONCLUSIVE when a GUI action before it failed, and a pass only means "not visible now" (see visual.not_exists).
- Text counts OCR text boxes, as in visual.count_equals.
- Text, icon, image, precedence and `window` as in visual.exists; the hostside backend cannot run it.

**Use cases:**
- No duplicates shown: At most one notification or one copy of an icon after repeating an action.

**Examples:**

*at most five folders* → PASSED

```yaml
tests:
- name: at_most_five_folders
  function: visual.count_max
  parameter:
    icon: folder
    max: 5
```

*a single notification* → PASSED

```yaml
tests:
- name: a_single_notification
  function: visual.count_max
  parameter:
    text: Download complete
    max: 1
```

*none left, as a negative test* → PASSED

```yaml
tests:
- name: none_left_as_a_negative_test
  function: visual.count_max
  parameter:
    icon: recycle_bin_full
    max: 0
```

**Related:**
- `visual.not_exists`: the same as `max: 0`, and clearer

## `visual.count_min`

Check if text or image appears at least N times on screen

Pass when the text, icon or image is found at least `min` times on the screenshot.

**Use for:** "at least N items visible". Icon/image matches are capped at 10 by the CV call, so counts above 10 cannot be observed.

asserts: ui, count · formats: screen · runs: host, against the live VM screen; not hostside; no dry-run · os: any

**Does not support:**
- Counts with a comparison (`count_comparison`): Takes `min` (inclusive); there is no `expected_count` / `comparison_type`.

**Not for:**
- an element is shown at all → `visual.exists`
- how many files match a glob → `standard.file_count`

| parameter | type | default | description |
|---|---|---|---|
| text | `str` | `None` | OCR search string: case-insensitive substring of a single OCR text box (a phrase split across boxes may not match). Wins over `icon` and `image`. |
| image | `str` | `None` | Template PNG on the HOST, relative to the playbook directory (or absolute); matched with the CV server's icon pipeline. A missing file is an execution error. |
| icon | `str` | `None` | Name from the icon library (`appdata/icon-library.yml`, e.g. `recycle_bin`, `folder`), extracted from the target on first use; needs a connected agent. Used when `text` is empty; wins over `image`. |
| window | `str` | `None` | Capture only the first window whose title matches this search string (Linux guests; Windows currently captures the full screen). `None` = full screen; no matching window is an execution error. |
| min | `int` | `None` | Required minimum number of matches, inclusive (`None` -> error). |

**Outcomes:**
- PASSED: the text, icon or image is found at least `min` times
- FAILED: the screenshot was searched and fewer than `min` matches are found
- ERROR: none of `text`, `icon`, `image` is given, or `min` is missing
- ERROR: the `image` file does not exist on the host; the `icon` name is unknown or cannot be extracted
- ERROR: no window matches `window`; the screenshot or the CV server fails

**Limits:**
- Icon and image matches are capped at 10: `min` above 10 never passes for them.
- Text counts OCR text boxes, as in visual.count_equals.
- Text, icon, image, precedence and `window` as in visual.exists; the hostside backend cannot run it.

**Use cases:**
- At least N items visible: Two new documents open, several entries in a list.

**Examples:**

*two untitled documents* → PASSED

```yaml
tests:
- name: two_untitled_documents
  function: visual.count_min
  parameter:
    text: Untitled
    min: 2
```

*at least one folder icon* → PASSED

```yaml
tests:
- name: at_least_one_folder_icon
  function: visual.count_min
  parameter:
    icon: folder
    min: 1
```

## `visual.exists`

Check if text or image is visible on screen

Pass when the given text, icon or image is found on a fresh screenshot of the guest.

**Use for:** confirming a GUI state (dialog shown, file icon on the desktop). Runs on the host via the CV server. At least one of `text`/`icon`/`image` is required (none -> error). Opposite: visual.not_exists.

asserts: ui, exists · formats: screen · runs: host, against the live VM screen; not hostside; no dry-run · os: any

**Not for:**
- a file was written or saved → `standard.file_exists`
- a text was written into a file → `standard.file_content_contains`
- a setting was stored in the Windows registry → `windows.registry_value_matches`
- a program is running, also without a window → `linux.process_running`
- an element is not shown (any more) → `visual.not_exists`

| parameter | type | default | description |
|---|---|---|---|
| text | `str` | `None` | OCR search string: case-insensitive substring of a single OCR text box (a phrase split across boxes may not match). Wins over `icon` and `image`. |
| image | `str` | `None` | Template PNG on the HOST, relative to the playbook directory (or absolute); matched with the CV server's icon pipeline. A missing file is an execution error. |
| icon | `str` | `None` | Name from the icon library (`appdata/icon-library.yml`, e.g. `recycle_bin`, `folder`), extracted from the target on first use; needs a connected agent. Used when `text` is empty; wins over `image`. |
| window | `str` | `None` | Capture only the first window whose title matches this search string (Linux guests; Windows currently captures the full screen). `None` = full screen; no matching window is an execution error. |

**Outcomes:**
- PASSED: the text, icon or image is found at least once on the screenshot
- FAILED: the screenshot was searched and nothing matches
- ERROR: none of `text`, `icon`, `image` is given
- ERROR: the `image` file does not exist on the host; the `icon` name is unknown or cannot be extracted (no connected agent, no Windows target)
- ERROR: no window matches `window`; the screenshot or the CV server fails

**Limits:**
- One screenshot at the moment of the test, no waiting or retry: an element that appears a moment later fails. Put a `wait_until` action before the test when the UI needs time.
- Only what is on screen counts: a minimised or covered window, content scrolled out of view and state that is never displayed are invisible to it.
- `text` is a case-insensitive substring of ONE OCR text box: a phrase split across boxes may not match, and OCR misreads (`l` / `I`, dropped punctuation) make it fail.
- `icon` and `image` use the CV icon pipeline with a relaxed match threshold (0.5): it tolerates scale and some theme change, but a differently drawn icon (another version, another icon set) may not match, and a similar-looking icon may.
- `icon` names come from `icon-library.yml`; they are extracted from Windows targets only, through the guest agent. On other guests use `image` with a template PNG.
- Precedence when several are given: `text`, then `icon`, then `image`; the others are ignored.
- `window` captures the first window whose title matches (Linux guests); on Windows the full screen is searched.
- It needs a running guest screen: the hostside backend evaluates tests after the guest shut down, so screen checks cannot run there.

**Use cases:**
- A dialog or message appeared: A confirmation, an error message or a status text after an action.
- An icon on the desktop or in a folder view: A new file icon, a recycle bin icon that shows it is full.
- Check a step before relying on it: As a control test (`controls:`) for a negative test that follows.

**Examples:**

*a status message is shown* → PASSED

```yaml
tests:
- name: a_status_message_is_shown
  function: visual.exists
  parameter:
    text: Document saved
```

*an icon from the icon library* → PASSED

```yaml
tests:
- name: an_icon_from_the_icon_library
  function: visual.exists
  parameter:
    icon: recycle_bin
```

*a template image in one window* → PASSED. The PNG lies next to the playbook; only the first window whose title contains `Files` is searched (Linux guests).

```yaml
tests:
- name: a_template_image_in_one_window
  function: visual.exists
  parameter:
    image: img/new_folder.png
    window: Files
```

*text wins over icon* → PASSED. With both given only the text is searched; the icon is ignored.

```yaml
tests:
- name: text_wins_over_icon
  function: visual.exists
  parameter:
    text: Recycle Bin
    icon: recycle_bin
```

*nothing to look for is an error* → ERROR

```yaml
tests:
- name: nothing_to_look_for_is_an_error
  function: visual.exists
  parameter:
    window: Files
```

**Related:**
- `visual.count_min`: the same check with a minimum number of matches

## `visual.not_exists`

Check if text or image is NOT visible on screen

Pass when the given text, icon or image is NOT found on a fresh screenshot of the guest.

**Use for:** confirming a dialog closed or an item disappeared. Opposite: visual.exists. At least one of `text`/`icon`/`image` is required (none -> error).

asserts: ui, absent · formats: screen · runs: host, against the live VM screen; not hostside; no dry-run · os: any

**Supports:** Negative tests (absence) (`negative`)

**Not for:**
- a file was deleted → `standard.file_does_not_exist`
- a value or entry was removed from a file → `text.occurrence_count`
- an element is shown → `visual.exists`

| parameter | type | default | description |
|---|---|---|---|
| text | `str` | `None` | OCR search string: case-insensitive substring of a single OCR text box (a phrase split across boxes may not match). Wins over `icon` and `image`. |
| image | `str` | `None` | Template PNG on the HOST, relative to the playbook directory (or absolute); matched with the CV server's icon pipeline. A missing file is an execution error. |
| icon | `str` | `None` | Name from the icon library (`appdata/icon-library.yml`, e.g. `recycle_bin`, `folder`), extracted from the target on first use; needs a connected agent. Used when `text` is empty; wins over `image`. |
| window | `str` | `None` | Capture only the first window whose title matches this search string (Linux guests; Windows currently captures the full screen). `None` = full screen; no matching window is an execution error. |

**Outcomes:**
- PASSED: the screenshot was searched and the text, icon or image is not found
- FAILED: the element is found at least once
- ERROR: none of `text`, `icon`, `image` is given
- ERROR: the `image` file does not exist on the host; the `icon` name is unknown or cannot be extracted
- ERROR: no window matches `window`; the screenshot or the CV server fails (an error, never a pass)

**Limits:**
- A pass only says the element is not visible now: a closed dialog, a minimised window, content scrolled away and an element not rendered yet all look the same. Prove the act with an earlier visual.exists as a control (`controls:`).
- As a negative test it is INCONCLUSIVE when a GUI action before it failed or failed its `verify:`.
- OCR misreads and a differently drawn icon also make the element "absent": a pass is weaker evidence than a fail.
- Text, icon, image, precedence and `window` as in visual.exists; the hostside backend cannot run it.

**Use cases:**
- A dialog closed: The confirmation is gone after clicking OK.
- An item disappeared from view: A deleted file's icon on the desktop, an emptied recycle bin.

**Examples:**

*the recycle bin is not full* → PASSED

```yaml
tests:
- name: the_recycle_bin_is_not_full
  function: visual.not_exists
  parameter:
    icon: recycle_bin_full
```

*the error message is gone* → PASSED

```yaml
tests:
- name: the_error_message_is_gone
  function: visual.not_exists
  parameter:
    text: Could not save the document
```

*absence in one window only* → PASSED. Other windows may still show the text (Linux guests).

```yaml
tests:
- name: absence_in_one_window_only
  function: visual.not_exists
  parameter:
    text: report.odt
    window: Files
```

**Related:**
- `visual.count_max`: `max: 0` is the same check; a higher `max` allows a few
