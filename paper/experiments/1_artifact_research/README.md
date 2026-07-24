# Case Study 5.1 — Explorative Artifact Research: Linux Trash Can

## Hypothesis under test

> "Deleting a file via Nautilus (GNOME), Dolphin (KDE), or command-line tools (`gio trash`,
> `kioclient5`, `trash-put`) within the user's home directory and its subdirectories produces
> identical Trash can artifacts."

The point of the case study is *not* that one deletion method works. It is that six different
user actions across two desktop environments and six distributions all converge on the same
on-disk artifacts — and can therefore be evaluated by one unchanged set of assertions.

## Playbooks

Seven playbooks, one per simulated user action:

| Playbook | Deletion method | Desktop | Environments |
|---|---|---|---|
| `deletefile_nautilus_by_click` | Nautilus context menu → *Move to Trash* | GNOME | `ubuntu-1804`, `ubuntu-2004`, `ubuntu-2204`, `ubuntu-2404` |
| `deletefile_nautilus_by_keypress` | Select in Nautilus + <kbd>Delete</kbd> | GNOME | `ubuntu-1804`, `ubuntu-2004`, `ubuntu-2204`, `ubuntu-2404` |
| `deletefile_dolphin_by_click` | Dolphin context menu → *Move to Trash* | KDE | `fedora-41`, `fedora-42` |
| `deletefile_dolphin_by_keypress` | Select in Dolphin + <kbd>Delete</kbd> | KDE | `fedora-41`, `fedora-42` |
| `deletefile_gio_trash` | `gio trash <path>` | both (CLI) | `ubuntu-1804`, `ubuntu-2004`, `ubuntu-2204`, `ubuntu-2404`, `fedora-41`, `fedora-42` |
| `deletefile_kioclient5` | `kioclient5 move <path> trash:/` | KDE (CLI) | `fedora-41`, `fedora-42` |
| `deletefile_trashput` | `trash-put <path>` (trash-cli) | both (CLI) | `ubuntu-1804`, `ubuntu-2004`, `ubuntu-2204`, `ubuntu-2404`, `fedora-41`, `fedora-42` |

Environment assignment follows applicability, not preference: Dolphin and `kioclient5` ship with
KDE, so those three playbooks are pinned to the Fedora KDE environments. `gio trash` (GLib) and
`trash-put` (trash-cli) are desktop-agnostic and run on all six.

## Why one test block covers GNOME *and* KDE

Every playbook carries the *same five tests*, byte-for-byte identical:

1. `testfile_created` — `file_exists` on the target path (pre-condition)
2. `testfile_deleted` — `file_does_not_exist` on the target path
3. `trashbin_check_file` — `file_exists` on `<trash>/files/testfile.txt`
4. `trahsbin_check_info_file` — `file_exists` on `<trash>/info/testfile.txt.trashinfo`
   (the misspelled test name is preserved deliberately, so the block stays literally identical
   across all seven playbooks)
5. `trashbin_check_info_date` — `file_content_equals` on the `.trashinfo`, comparing the
   `[Trash Info]` stanza including `DeletionDate` against the recorded timestamp with a
   ±5 s tolerance

This transfers unchanged because both desktops implement the *freedesktop.org Trash
specification*: user-level trash lives at `$XDG_DATA_HOME/Trash`, i.e.
`~/.local/share/Trash`, split into `files/` and `info/`, with one `<name>.trashinfo`
per trashed item containing `Path=` and `DeletionDate=` in local time. Nautilus, Dolphin,
GIO, KIO and trash-cli are all clients of that one spec. The playbooks therefore only differ
in their `actions:` block — the observable-artifact contract is shared, which is exactly the
paper's claim.

The `trashbin_path` variable is `{{ adare_user_home }}/.local/share/Trash` in all seven
playbooks; nothing about it is desktop-specific.

## FRED *Repeat* phase — three home subdirectories

To satisfy the Repeat phase, the whole create → delete → assert sequence is wrapped in a loop
over three directories inside the home directory:

```yaml
- loop:
    items: ["Documents", "Downloads", "Desktop"]
    item_var: target_dir
```

Each iteration rebuilds the target path with `save_variable`:

```yaml
- save_variable:
    name: filepath
    value: "{{ adare_user_home }}/{{ target_dir }}/{{ filename }}"
```

`filepath` remains declared in `variables:` with its `{{ adare_user_documents }}/{{ filename }}`
default — that is both the sane single-shot value and required for validation, since
`save_variable` does not register a variable definition with the playbook validator.

In the two Dolphin playbooks the file-manager navigation click uses the loop item as well
(`target: { text: "{{ target_dir }}" }`), so the GUI path varies together with the filesystem
path rather than being hard-coded to *Documents*.

The Dolphin playbooks open the file manager **once**, before the loop, and only re-navigate
inside it per iteration — opening it three times would leave three windows stacked on the
desktop and break the icon match on later iterations.

### Trash reset between iterations

Each loop iteration begins with

```yaml
- command:
    command: "rm -rf {{ trashbin_path }}/files/* {{ trashbin_path }}/info/*"
    allow_failure: true
```

This is required for the *identical* test block to remain valid across iterations. The XDG spec
mandates unique names inside `files/`, so a second `testfile.txt` would be stored as
`testfile.2.txt` with a matching `testfile.2.txt.trashinfo`, and iterations 2 and 3 would fail
tests 3–5 for a reason that has nothing to do with the hypothesis. Emptying the trash first
keeps every iteration an independent, identically-asserted repetition. `allow_failure` covers
the case where the trash directories do not exist yet on a fresh VM.

Note this only removes guest state, it never adds any.

## Breeze Dolphin icon — needs re-taking

`deletefile_dolphin_by_click/img/dolphin_taskbar.png` and
`deletefile_dolphin_by_keypress/img/dolphin_taskbar.png` are **48×48 PNG rasterizations of
upstream KDE Breeze art**, not crops from a live VM screenshot:

* Source: `https://raw.githubusercontent.com/KDE/breeze-icons/master/icons/apps/48/system-file-manager.svg`
  (KDE Breeze icons, LGPL — redistributable)
* Rasterized with `rsvg-convert -w 48 -h 48`

**Caveat:** because it comes from upstream SVG rather than from the actual Fedora KDE panel,
the template may not match pixel-for-pixel what the CV matcher sees at runtime — the panel
renders the icon at the panel's own size, with its own antialiasing, background contrast and
possible theme variant (Breeze Dark). If `click: { target: { image: ... } }` fails to locate the
launcher, **re-take the crop from a live Fedora KDE VM screenshot** and replace both copies.
The Nautilus counterparts in this case study were cropped from live screenshots (46×42), which
is the approach to follow.

## Prerequisites / not shipped

These playbooks are complete but **cannot be executed as-is today**: three of the six
environments named in the paper have no OS profile in `adare/appdata/os-profiles/`.

Missing, and needed to actually run the full matrix:

* `ubuntu1804`
* `ubuntu2004`
* `fedora42`

Present today: `fedora41`, `kubuntu2404`, `ubuntu2204`, `ubuntu2404`, `ubuntu2510`,
`ubuntu2604`, `windows10`, `windows11`, plus the `arm64` variants of several of these.

Building those base VMs and environments is out of scope for this directory. Until they exist,
the runnable subset is: GNOME playbooks on `ubuntu-2204` / `ubuntu-2404`, and the KDE playbooks
on `fedora-41`.

Two further runtime prerequisites for the CLI playbooks:

* `trash-put` comes from the `trash-cli` package and is **not** installed by default on either
  Ubuntu or Fedora — the environment must provide it.
* `kioclient5` is the KDE Frameworks 5 binary. On a KF6-only Fedora KDE image the command is
  `kioclient` instead; the paper's wording (`kioclient5`) is kept here, so adjust the command if
  the target environment ships KF6 only.
