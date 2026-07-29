# CV / OCR debugging — reference

When a playbook step "clicks into the void" or can't find an icon/text, the cause is
usually grounding: the CV server didn't match the icon template, or OCR didn't read
the label. These commands debug that **off a screenshot PNG** — no VM/session needed
— by auto-starting a CV server, running one query, printing coordinates, and
stopping the server.

## Icon matching

```sh
adare cv test-icon --icon <icon.png> --screenshot <shot.png> \
  [--output marked.png] [--threshold 0.6] [--host localhost] [--port 13109] [--mcplog log]
```

Finds the icon template in the screenshot and prints coordinates of all matches.
`--output` writes a copy with the matches marked. Lower `--threshold` (default 0.6)
if a real match is being missed; raise it if you get false hits.

## Text matching

```sh
adare cv test-text "<text>" --screenshot <shot.png> [--format json|csv] [--host …] [--port …]
```

Finds occurrences of the text string and prints their coordinates. Use this to check
whether a `text:` target in a playbook actually resolves — and watch for the two
classic OCR traps: **truncated labels** (a GNOME result may read "LibreOffice Wri…"
— never wait for the full name) and **duplicate on-screen text** (the same label in
two places makes a `text:` target ambiguous).

## Dump all detected text

```sh
adare cv get-all-text --screenshot <shot.png> [--format json|csv]
```

Runs OCR over the whole screenshot and returns every detected string with its
coordinates and confidence. Use it to discover exactly what OCR sees before you
choose a `text:` target.

## Getting a screenshot to test against

Take a screenshot on a live session (e.g. via a one-action screenshot playbook, or
`--debug-screenshots` on a run/session) — the newest PNG lands under
`reporting/screenshots/`. Then point these commands at it.

## Live CV server on a session

```sh
adare dev cv start -s <id> [--debug -o <debug-dir>]   # (re)start with optional debug logging
adare dev cv stop  -s <id>
```

`--debug` writes CV debug screenshots to the given directory so you can see what the
server matched during a live replay.
