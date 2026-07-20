# ADARE UI-action Playbook Schema (compact)

This is the **complete vocabulary** an authoring model may emit for a
**UI-action playbook**. It is extracted faithfully from
`adare/types/playbook.py` and `adare/types/actions.py`. The playbook YAML is
parsed by `parse_playbook()` with `forbid_extra_keys = True` — **any field not
listed here is rejected**. Emit ONLY the keys documented below.

A UI-action playbook has this top-level shape (NO `tests:` — see FLOW.md):

```yaml
settings:            # optional; a small idle + a timeout
  idle: 1.0
  timeout: 1800
actions:             # required: the ordered list of actions
  - <action>
  - <action>
```

---

## Targets

A `Target` says *what on screen* an action refers to. Fields:

| field        | type            | meaning |
|--------------|-----------------|---------|
| `text`       | str             | OCR text to find on screen (**preferred**) |
| `image`      | str             | filename of an image crop to template-match (recorder-only; the author has no crops, so avoid) |
| `position`   | `[x, y]`        | absolute pixel coordinate (fragile; last resort) |
| `text_match` | TextMatchConfig | how `text` is matched (see below) |
| `strategy`   | strategy object | which match to pick when several are found |
| `offset`     | Offset          | shift the click off the matched point |
| `use_cache`  | bool            | reuse the previously matched location (skip re-search) |

**Author rule:** prefer `text:` targets. Do not invent `image:` filenames — you
have no crops to reference.

### TextMatchConfig (`text_match:`)
```yaml
text_match:
  mode: substring        # substring (default) | regex | fuzzy | regex_fuzzy
  case_sensitive: false
  min_similarity: 0.8    # fuzzy only, 0.0-1.0
  allow_missing_chars: true   # fuzzy: true | "." | [".", ","]
  max_missing: 2         # fuzzy: cap on missing chars
  flags: [IGNORECASE]    # regex: IGNORECASE|MULTILINE|DOTALL|VERBOSE
```

### Offset (`offset:`)
```yaml
offset: { x: 0, y: 20, base: center }
```
`base` ∈ `center, top-left, top-right, bottom-left, bottom-right,
center-left, center-right, top-center, bottom-center`.

### Strategies (`strategy:`) — pick ONE match among many
Each is a single-key mapping. Real names (do not abbreviate):
```yaml
strategy: { BestConfidenceStrategy: {} }   # highest match score
strategy: { TopLeftStrategy: {} }          # topmost-leftmost
strategy: { TopRightStrategy: {} }
strategy: { BottomLeftStrategy: {} }
strategy: { BottomRightStrategy: {} }
strategy: { LargestStrategy: {} }          # biggest bounding box
strategy: { SmallestStrategy: {} }
strategy: { SweepStrategy: { index: 1 } }  # nth match, 1-based, L->R T->B
strategy: { ClosestToStrategy: { text: "File", max_distance: 300 } }
# ClosestToStrategy: exactly ONE of {x,y} | text | image; optional max_distance (px)
```

---

## Actions

Each list item is a single-key mapping whose key names the action.

### click
```yaml
- click:
    target: { text: "File" }
    type: left          # left (default) | right | double
    description: open the File menu
```

### keyboard  (exactly one of key | text | combination)
```yaml
- keyboard: { text: "hello world", description: type into the document }
- keyboard: { key: "enter", description: confirm }        # single key -> press()
- keyboard: { combination: [ctrl, s], description: save } # hotkey()
```
`keyboard` also accepts a `when:` guard (list of exists/not_exists conditions);
it only fires if every condition holds:
```yaml
- keyboard:
    key: esc
    when:
      - exists: { text: "Tip of the Day" }
```

### drag
```yaml
- drag:
    src: { text: "Sheet1" }
    dst: { position: [900, 400] }
    description: drag sheet tab
```

### scroll
```yaml
- scroll: { direction: down, amount: 3, description: scroll the page }
```

### wait_until  (the synchronization primitive — use before every click)
The `condition:` is a `WaitCondition`: exactly one of `exists` / `not_exists` /
`all` / `any` / `not`. Leaves take a **Target**.
```yaml
- wait_until:
    condition: { exists: { text: "Untitled 1" } }
    timeout: 60.0          # default 60
    check_interval: 3.0    # default 3
    initial_delay: 5.0     # default 5
    description: wait for the document window
# boolean composition:
- wait_until:
    condition:
      all:
        - exists: { text: "Save" }
        - not_exists: { text: "Loading" }
- wait_until:
    condition:
      any:
        - exists: { text: "Welcome" }
        - exists: { text: "Tip of the Day" }
- wait_until:
    condition:
      not:
        exists: { text: "Splash" }
```

### block  (conditional group — wrap optional/first-run dialogs)
`when:` is a list of `exists` / `not_exists` conditions; the block runs only if
they all hold. `actions:` is a nested list.
```yaml
- block:
    when:
      - exists: { text: "Tip of the Day" }
    actions:
      - keyboard: { key: esc, description: dismiss first-run tip }
    description: dismiss first-run dialog if present
    # optional: delay: 1.0
```

### loop  (repeat; exactly one of times | items)
```yaml
- loop:
    times: 3
    actions:
      - keyboard: { key: tab }
# or iterate a list (item var defaults to 'item'):
- loop:
    items: ["a.txt", "b.txt"]
    item_var: fname
    actions:
      - keyboard: { text: "{{ fname }}" }
```
Inside a loop the vars `index` (0-based), `total`, and the item var are available.

### idle  (fixed pause — DISCOURAGED for sync; use wait_until instead)
```yaml
- idle: { duration: 2.0, description: let the save flush }
```

---

## Conditions cheat-sheet (used by `when:` and `wait_until`)
```yaml
exists:     { text: "..." }      # or { image: "..." }
not_exists: { text: "..." }
```
`ExistsCondition` / `NotExistsCondition` accept `text` or `image` (author: use `text`).

---

## `adare_*` variables (interpolated with `{{ }}`)
ADARE injects reserved forensic/environment variables you may reference in
`text`, `command`, filenames, etc. Common ones seen in real playbooks:

- `{{ adare_user_documents }}` — the guest user's Documents folder.

Use them for anything path- or user-dependent instead of hard-coding, e.g.
`text: "{{ adare_user_documents }}/report.odt"`.

---

## Actions NOT to emit when authoring UI-action playbooks
`test` / `command` / `pull` / `screenshot` / `save_variable` / `save_timestamp`
/ `snapshot_filesystem` / `pull_changed_files` / `stop` / `continue` / `goto` /
`pause` exist in the schema but are **out of scope** for a pure UI-action
playbook. Emit only: `click`, `keyboard`, `drag`, `scroll`, `wait_until`,
`block`, `loop`, and (sparingly) `idle`.
