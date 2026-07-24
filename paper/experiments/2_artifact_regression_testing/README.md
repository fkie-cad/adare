# Section 5.2 — Artifact Regression Testing

The experiments in this directory back the paper's §5.2 claim that a forensic *expectation*
should be an executable specification rather than prose. One interaction is held constant
and only the distribution/version varies:

> create a document, open it once, and then validate whether `recently-used.xbel` exists and
> whether its access metadata (counts and timestamps) matches the known ground truth.

`recently-used.xbel` is the XDG "recently used files" artifact
(`~/.local/share/recently-used.xbel`), written by GLib's `GBookmarkFile` on behalf of the
application that opened the document. It is XBEL with two freedesktop namespaces, so the
assertions use the `xml.*` test functions rather than a bare existence check.

Every experiment runs the *same* action sequence: wipe the artifact → create the document →
open the file manager → navigate to `Documents` → reset the document's access time →
`save_timestamp` → open the document exactly once → wait for the editor to display the
content → assert.

## The paper's findings at a glance

| experiment directory | distro / version | desktop / file manager | expected outcome |
| --- | --- | --- | --- |
| `open-single-text-file-ubuntu-2004`  | Ubuntu 20.04 LTS  | GNOME / Nautilus | artifact **present**, but `visited` is the **integer −1 defect** (`1969-12-31T23:59:59Z`) and all timestamps are **second-precision only** |
| `open-single-text-file-ubuntu-2204`  | Ubuntu 22.04 LTS  | GNOME / Nautilus | artifact **present and correct**, timestamps **sub-second** |
| `open-single-text-file-ubuntu-2404`  | Ubuntu 24.04 LTS  | GNOME / Nautilus | artifact **present and correct**, timestamps **sub-second** |
| `open-single-text-file-kubuntu-2004` | Kubuntu 20.04 LTS | KDE Plasma / Dolphin | artifact **absent** after the same interaction |
| `open-single-text-file-kubuntu-2204` | Kubuntu 22.04 LTS | KDE Plasma / Dolphin | artifact **absent** after the same interaction |
| `open-single-text-file-kubuntu-2404` | Kubuntu 24.04 LTS | KDE Plasma / Dolphin | artifact **present and correct**, timestamps **sub-second** |

`open-single-text-file-fedora-42/` also lives here — see *Misfiled experiment* below.

The mechanism behind the two Ubuntu findings is the same GLib change: releases before
GLib 2.66 stored bookmark times as `time_t` and serialised the "never visited" sentinel
`-1` as `1969-12-31T23:59:59Z`; from 2.66 onwards `GBookmarkFile` uses `GDateTime` and
writes ISO-8601 with microseconds. Ubuntu 20.04 ships GLib 2.64, Ubuntu 22.04 ships 2.72.

## Which assertion encodes which paper claim

| paper claim | test name | file(s) |
| --- | --- | --- |
| "validate whether `recently-used.xbel` exists" | `xbel_exists` (`standard.file_exists`) | ubuntu-2004/2204/2404, kubuntu-2404 |
| the artifact is created *by the interaction*, not already there | `xbel_absent_before` (`standard.file_does_not_exist`) | all six |
| access metadata — one entry for one opened document | `xbel_bookmark_count` (`xml.element_count`, `//bookmark`, `expected_count: 1`) | ubuntu-2004/2204/2404, kubuntu-2404 |
| access metadata — the entry names the document that was opened | `xbel_bookmark_href` (`xml.element_exists`, `//bookmark[@href="file://…"]`) | ubuntu-2004/2204/2404, kubuntu-2404 |
| access metadata — **counts** ("open it once") | `xbel_visit_count` (`xml.attribute_matches` on `bookmark:application/@count == "1"`) | ubuntu-2004/2204/2404, kubuntu-2404 |
| access metadata — **timestamps** match the access time | `xbel_visited_timestamp`, `xbel_modified_timestamp`, `xbel_added_timestamp` (`xml.attribute_matches` with `tolerance(5, -5)`) | ubuntu-2204/2404, kubuntu-2404 (on 2004 only `modified`/`added`) |
| "Ubuntu 20.04 consistently recorded the `visited` timestamp as `1969-12-31T23:59:59Z` (integer −1)" | `xbel_visited_is_epoch_minus_one` (exact-value `xml.attribute_matches`, **no** tolerance) | ubuntu-2004 |
| "Ubuntu 20.04 stored only second-level precision" | `xbel_modified_second_precision`, `xbel_added_second_precision` (`regex_match`, `^…T\d{2}:\d{2}:\d{2}Z$`) | ubuntu-2004 |
| "later versions provided higher-precision values" | `xbel_visited_subsecond_precision` (`regex_match`, `^…\.\d+Z$`) | ubuntu-2204/2404, kubuntu-2404 |
| "on Kubuntu, the artifact was absent in 20.04 and 22.04" | `xbel_absent_after_open` (`standard.file_does_not_exist`) | kubuntu-2004, kubuntu-2204 |
| the absence is a platform behaviour, not a failed interaction | `text_file_accessed` (`standard.file_timestamps`) plus a `wait_until` on the editor showing the document content | all six |

`xbel_visited_is_epoch_minus_one` is a **defect pin**: it passes on Ubuntu 20.04 and fails
on any release that fixed the bug. The same is true in reverse for
`xbel_*_second_precision` versus `xbel_visited_subsecond_precision`. That mutual
exclusivity is the regression signal the paper argues for — a green Ubuntu 20.04 run and a
green Ubuntu 22.04 run assert contradictory things about the same artifact, and the
contradiction is machine-checkable instead of being buried in a results table.

### Why the absence tests are not trivial

`standard.file_does_not_exist` on a never-touched system passes for the wrong reason, so the
Kubuntu 20.04/22.04 playbooks run the complete interaction first and then prove the document
was really opened:

* the document's access time is reset to `2000-01-01` (`touch -a -t 200001010000`) *after*
  navigating to the folder, so file-manager previewing/thumbnailing cannot be mistaken for
  the opening read;
* `text_file_accessed` then requires a recent access time, which can only come from the
  document being read after the click;
* a `wait_until` waits for the editor to display the document's content on screen, so a
  failed open surfaces as a failed action rather than as a silently-passing absence claim.

`expect_to_fail: true` (on `Test` in `adarelib/adarelib/testset/type.py`) would also express
absence, but a positive `file_does_not_exist` states the expectation directly and keeps the
run's pass/fail semantics readable.

## UTC, not localtime

The xbel time attributes are UTC with a trailing `Z`. The timestamp assertions therefore use

```yaml
expected_value: "{{ open_timestamp | format('%Y-%m-%dT%H:%M:%S.%fZ') | tolerance(5, -5) }}"
```

with the literal `Z` in the format string and **without** the `| localtime` filter that
§5.1's `deletefile_*` playbooks use. That is deliberate: `| localtime` is correct for
`.trashinfo`, whose `DeletionDate` is local wall time, but wrong here.

`adarelib/adarelib/testset/basictest.py:_parse_timestamp_with_format` treats a naive guest
value as **local** wall time when `localtime` is set, and as **UTC** otherwise. With
`| localtime`, a second-precision UTC value such as `2026-07-24T20:58:27Z` parses through
`strptime` into a naive datetime that is then labelled local — shifting the comparison by
the host's UTC offset. Measured on this machine (UTC+2) the same artifact compares as
`7198s` outside a ±5s tolerance with `| localtime` and `−2.0s` inside it without. The
Ubuntu 20.04 playbook uses `format('%Y-%m-%dT%H:%M:%SZ')` (no fractional part) and the
later releases use `format('%Y-%m-%dT%H:%M:%S.%fZ')`, so the format string doubles as
documentation of the observed precision; a value whose precision does not match the format
still parses correctly through the `dateutil` fallback.

Note that GLib omits the fractional part when the microsecond field happens to be exactly
`0`. That is a ~1-in-10⁶ flake for `xbel_visited_subsecond_precision`; if it is ever
observed, re-run rather than loosening the regex.

## GUI crop caveat

**None of the `img/*.png` template crops in this directory have been verified against a live
VM of the release they target.** They must be re-taken before the results are trusted:

* `open-single-text-file-ubuntu-2004/img/filemanager-app.png` and
  `open-single-text-file-ubuntu-2204/img/filemanager-app.png` are copies of the Ubuntu 24.04
  crop. The Yaru icon theme changed between 20.04, 22.04 and 24.04, so template matching may
  miss.
* `open-single-text-file-kubuntu-*/img/dolphin_taskbar.png` is reused from §5.1's
  `paper/experiments/1_artifact_research/playbooks/deletefile_dolphin_by_click/img/`. It is a
  48×48 `rsvg-convert` rasterization of upstream KDE Breeze
  `icons/apps/48/system-file-manager.svg` (LGPL) — **not** a crop from a live VM screenshot,
  so it will not match a Breeze Dark taskbar or a scaled panel. See §5.1's README section
  "Breeze Dolphin icon — needs re-taking"; both directories need the same replacement.
* `open-single-text-file-ubuntu-2404/img/org.gnome.Nautilus.png` is unused by that playbook
  (the Fedora playbook uses the icon of the same name).

There is a second, KDE-specific caveat on the Kubuntu playbooks: Plasma can be configured to
open files on a **single** click. Under that setting the `type: "double"` click opens the
document twice and `xbel_visit_count` reports `2`. The playbooks keep the double click so
that the interaction stays identical to the Ubuntu variants (the paper's "the same
interaction"), and flag the issue in a header comment — a failing `xbel_visit_count` is the
intended signal, not a reason to loosen the assertion.

## Prerequisites / not shipped

Running these experiments needs six environments — `ubuntu-2004`, `ubuntu-2204`,
`ubuntu-2404`, `kubuntu-2004`, `kubuntu-2204`, `kubuntu-2404`. **None of them exist in this
checkout** (`adare env list` shows only `ubuntu2510*`, `win11*` environments), and three of
them cannot even be built yet because the OS profile is missing:

| OS profile needed | present in `adare/appdata/os-profiles/`? |
| --- | --- |
| `ubuntu2004` | **missing** |
| `kubuntu2004` | **missing** |
| `kubuntu2204` | **missing** |
| `ubuntu2204` | yes (`ubuntu2204.yml`, `ubuntu2204arm64.yml`) |
| `ubuntu2404` | yes (`ubuntu2404.yml`, `ubuntu2404arm64.yml`) |
| `kubuntu2404` | yes (`kubuntu2404.yml`) |

Profiles currently shipped: `fedora41`, `kubuntu2404`, `ubuntu2204`, `ubuntu2404`,
`ubuntu2510`, `ubuntu2604`, `windows10`, `windows11`, plus the `*arm64` variants.

Building the missing VMs is out of scope for this directory. Note also that `kubuntu2404` is
`install_mode: gui-auto` with no bundled ISO, so the Kubuntu profiles need a user-supplied
ISO and a GUI-automated install.

## Misfiled experiment: `open-single-text-file-fedora-42`

`open-single-text-file-fedora-42/` sits in this directory, but §5.2 never mentions Fedora —
its distro/version pair belongs to §5.1's "Fedora KDE Edition 41 and 42" claim. It has been
left in place on purpose; this is a note for the paper's authors, who should pick one of:

1. move the directory under `paper/experiments/1_artifact_research/`, or
2. extend the §5.2 text to include Fedora 42 in the version matrix.

Until that is decided the Fedora playbook keeps its original single `file_exists` assertion
and has **not** been extended with the `xml.*` assertion set, so it is not part of the table
above. Two bugs in it were fixed regardless: an illegal `pull: name:` key (`PullAction` has
no `name` field — the correct key is `description`) and hard-coded `/home/adare/...` paths,
now `{{ adare_user_documents }}` / `{{ adare_user_home }}`. Note that `fedora41` is the only
Fedora OS profile shipped, so `fedora-42` has no profile either.

## Verifying offline

The playbooks cannot be executed without the VMs, but the assertion contracts can be checked
against a hand-written sample artifact:

```bash
# schema (the command takes one FILE at a time)
for f in paper/experiments/2_artifact_regression_testing/*/playbook.yml; do
    adare experiment playbook validate "$f"
done

# a single assertion against a local sample (see 'adare testfunction dry-run --help')
adare testfunction dry-run xml.element_count -f sample.xbel -P 'xpath=//bookmark' -P expected_count=1
adare testfunction dry-run xml.attribute_matches -f sample.xbel -P 'xpath=//bookmark' \
    -P attribute=visited -P 'expected_value=1969-12-31T23:59:59Z'
```

Two limits are worth knowing. `adare experiment playbook validate` does **not** reject
unknown keys inside nested action bodies (`_validate_attrs_class` builds a converter without
the strict per-class hooks), which is why the illegal `pull: name:` above passed validation
for so long — action keys still have to be reviewed against
`adare/adare/types/playbook.py`. And `adare testfunction dry-run` coerces `-P` values to
scalars only, so the namespaced `bookmark:application/@count` assertion (which needs a
`namespaces` dict) cannot be exercised from the CLI; it has to be driven from Python via
`cattrs.structure` the way the CLI does internally.
