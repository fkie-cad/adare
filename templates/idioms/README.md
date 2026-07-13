# ADARE GUI-automation idioms

A small library of **reusable, parameterizable** GUI-automation patterns. Each
`*.play.yaml` is an ordinary ADARE playbook (`settings` + `variables` +
`actions` + `tests`) — so a recurring "idea" ("delete a file and verify it",
"open an app and confirm it started") becomes one playbook you replay across
environments with **no LLM**.

## How they're grounded

Idioms lean on **OCR text targets** (`target: {text: ...}`) rather than image
crops, because text labels generalize across machines while a cropped icon is
environment-specific. When you need pixel-robust targets, don't hand-edit an
idiom — **re-record it** against a live VM with `adare dev mcp` (an external
harness drives; ADARE crops each click into an `image:` target). Replay then
uses CV (`find_icon`) + OCR (`find_text`) deterministically.

## Parameterized replay

The changing bits live in `variables:` and are referenced as `{{ name }}` in
targets, keyboard text, and test parameters. Override them per environment
instead of editing the actions:

```yaml
variables:
  file_manager: Files
  file_name: testfile.txt
  file_path: /root/testfile.txt
```

Replay a copy in a dev session:

```bash
adare dev playbook -s <session> -f templates/idioms/delete_file_and_verify.play.yaml
```

Or run it as a host-mode experiment (deterministic CV/OCR replay + tests):

```bash
adare experiment run <experiment> -e <environment> --gui-mode host
```

## Adapting an idiom

1. Copy it next to your experiment.
2. Edit `variables:` for your target paths/names/labels.
3. Adjust the OCR `text:` targets to your desktop's labels (GNOME/KDE/XFCE
   differ), **or** re-record with `adare dev mcp` for image crops.
4. Point each `tests:` entry's `function:` at a real testfunction from your
   project (`adare dev mcp` → `list_testfunctions`, or `adare show
   testfunctions`). The dotnotations here (`filesystem.file_does_not_exist`,
   `visual.text_on_screen`) are placeholders — swap in yours.

## Files

- `delete_file_and_verify.play.yaml` — delete a file via the file manager, then
  assert it no longer exists.
- `open_app_and_verify.play.yaml` — launch an app from the app search, then
  assert a window label is visible.
