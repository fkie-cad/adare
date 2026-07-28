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

The *user action* is what is held constant, not the exact input events: the GNOME variants open
the document with a double click and the KDE ones select it and press Enter, because a
QMP-synthesised double click does not reach Qt item views (measured — see *Click mode* below).
Either way the document is opened exactly once, which is what the claims below depend on.

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

The Kubuntu boundary is a **different** mechanism, and GLib is not the variable. Package
versions read off the three live guests on 2026-07-28:

| environment | Plasma | KIO / KDE Frameworks | GLib |
| --- | --- | --- | --- |
| `kubuntu-2004-r2` | 5.18.8 | 5.68.0 | 2.64.6 |
| `kubuntu-2204` | 5.24.7 | 5.92.0 | 2.72.4 |
| `kubuntu-2404` | 5.27.12 | 5.115.0 | 2.80.0 |

GLib 2.72 on Kubuntu 22.04 is already past the 2.66 cut-off, yet 22.04 writes no artifact at
all — so what changes across the Kubuntu boundary is the **KDE** stack, not GLib. The 24.04
artifact names its writer, and it is a KDE application rather than GLib acting for a GTK one:

```xml
<bookmark:application name="org.kde.kate" exec="kate -b %U %u" count="1"/>
```

The boundary falls between Frameworks 5.92 and 5.115. Upstream, `KRecentDocument` gained
XBEL/`recently-used.xbel` support in **KF5 5.93**, which sits exactly inside that gap and is
the obvious candidate; that attribution comes from upstream history and is **not** verified in
this repository — the measured facts are the three version triples above and the presence or
absence of the file. Contrast Fedora 42 (GNOME), where the writer is the GTK side as expected:
`name="org.gnome.Nautilus" exec="'gnome-text-editor %U'"`.

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

## Verification status

**The KDE half of the version matrix, plus Fedora, is verified against live VMs as of
2026-07-28** (aarch64, QEMU/HVF on macOS, project `Tproj1`, `--production`). The three
`ubuntu-*` variants have still never completed a run.

| Playbook | Environment | Result | Run ULID |
| --- | --- | --- | --- |
| `open-single-text-file-kubuntu-2404` | `kubuntu-2404` | **green — 11/11** | `01KYMGZ0PNSCGGP2D1PNBG9J3N` |
| `open-single-text-file-kubuntu-2204` | `kubuntu-2204` | **green — 4/4** (artifact absent) | `01KYMN171371VTG256G96ECEVV` |
| `open-single-text-file-kubuntu-2004` | `kubuntu-2004-r2` | **green — 4/4** (artifact absent) | `01KYMMW3CT7DN6JASP6388PD8A` |
| `open-single-text-file-fedora-42` | `fedora-42` | **green — 1/1** | `01KYMJH375W6PKR3H49MHMFXXH` |

The Kubuntu version boundary the section claims therefore **reproduces**: the identical
interaction leaves no `recently-used.xbel` on 20.04 and 22.04 and writes a correct one on
24.04, and on all three releases `text_file_accessed` passes, so the absences are platform
behaviour rather than a missed interaction. The 24.04 artifact carries microsecond timestamps
(`visited="2026-07-28T14:12:02.429000Z"`), one bookmark, and `count="1"`.

Three assertions retain their original wording but were verified for the first time here:
`xbel_visit_count` really is 1 (see the click-mode note below), and `text_file_accessed` —
flagged in this README as never having run and "suspect-the-test" on first use — passed on all
four environments without modification.

Two caveats on the run methodology:

* **Runs must be serialised.** The CV/OCR server port is hardcoded to 13109 with no
  negotiation (`backend/experiment/run_setup.py` constructs `MCPServerManager()` with its
  default, and `playbook_controller` / `target_resolver` default to
  `http://localhost:13109/mcp`), so a second concurrent `adare experiment run` gets no CV
  server and every target silently fails to resolve. An `adare dev` session holds the port
  too. Two runs in this campaign failed for that reason alone and went green unchanged when
  re-run in isolation. Before believing any CV miss, check that `<run>/logs/mcp_gui.log`
  contains POSTs beyond the startup banner.
* **`kubuntu-2204` needs a readiness gate.** On a freshly-restored base snapshot the Plasma
  session is not up when the playbook starts — two runs died on the first
  `echo … > $text_file` with exit 1 because `~/Documents` did not exist yet (the XDG user
  directories are created on first graphical login) while every screenshot was black, ~2.9
  minutes after VM start. That playbook now blocks on `pgrep -x plasmashell` first.

The crop debt below was **re-confirmed by hash** on 2026-07-27, not merely assumed:
`filemanager-app.png` is byte-identical (`eaf1b9d1…`, 10 513 B) across all three Ubuntu
variants, and `dolphin_taskbar.png` is byte-identical (`a046199e…`, 1 443 B, 48×48 RGBA)
across all three Kubuntu variants. The Kubuntu crop turned out **not** to need re-taking on
24.04 (see below).

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
  `icons/apps/48/system-file-manager.svg` (LGPL) — **not** a crop from a live VM screenshot.
  Measured 2026-07-28, it needs **no** replacement on Kubuntu 24.04: it matched the live
  Plasma panel launcher at **0.915** confidence, selected `(175, 1056)` of a 1920×1080 screen,
  and Dolphin opened. On **Kubuntu 20.04 it is unusable, but not because of the crop** — that
  image's panel contains no Dolphin launcher at all to match
  (`~/.config/plasma-org.kde.plasma.desktop-appletsrc` has no `launchers` entry), so the best
  score was 0.752 on empty desktop. The 20.04 playbook now opens Dolphin through the
  Application Launcher (Super → type `dolphin` → Down → Enter) and keeps the unused
  `icon_filemanager_taskbar` variable so it stays diffable against the other two.
* `open-single-text-file-ubuntu-2404/img/org.gnome.Nautilus.png` is unused by that playbook
  (the Fedora playbook uses the icon of the same name).

### Click mode and how the document is opened (settled 2026-07-28)

The anticipated KDE caveat was that Plasma might be set to open files on a **single** click,
making a `type: "double"` click open the document twice so `xbel_visit_count` reports `2`.
**That is not what these images do.** On `kubuntu-2404`, `kreadconfig5 --file kdeglobals
--group KDE --key SingleClick` is unset and a lone left click on the document left the pinned
access time (2000-01-01) untouched and started nothing; on `kubuntu-2004-r2` a lone click on
the `Documents` folder label only selected it (Dolphin stayed in Home, status bar
`Documents (folder)`). Both are in **double-click** mode, and `xbel_visit_count` == 1 held on
24.04 without changing the assertion.

The real obstacle was the opposite one: **a QMP-synthesised double click never reaches a Qt
item view as a double click.** Verified three ways on `kubuntu-2404`, each with the access time
pinned to 2000-01-01 first:

1. run `01KYM8ZT5DW75R6TAFCYHJDW8Z` (`type: double`, host/QMP GUI mode) — item selected, no
   editor started, access time unchanged, no artifact;
2. the same interaction replayed step by step in a dev session — same outcome;
3. three hand-rolled double clicks sent straight down the QMP monitor socket (ADARE's exact
   press/release timings; the same without re-sending the pointer position between the two
   clicks; and the whole down/up/down/up inside a single `input-send-event`) — all three
   selected the item, none activated it.

The same `type: double` works on GTK: Ubuntu 24.04 run `01KYDKKQ3CNVJGWQNREN1` and Fedora 42
run `01KYMJH375W6PKR3H49MHMFXXH` both opened the document and wrote the artifact. So this is a
Qt-side limitation of QMP-synthesised clicks, not a playbook defect. `--gui-mode agent`
(in-guest PyAutoGUI/XTEST) would give a real double click but aborts on Kubuntu: its
`xhost +SI:localuser:root` setup step fails with `unable to open display ":0"` because root
holds no `XAUTHORITY` for the SDDM session.

The three Kubuntu playbooks therefore open the document as **select, then Enter**. Enter
activates the selected item exactly once, which is what "open it once" means, and the assertion
set is untouched — 24.04 still produces one bookmark with `count="1"` and microsecond
timestamps. The Ubuntu and Fedora variants keep `type: "double"` because it works there. Each
Kubuntu playbook records this in a header comment with the run IDs above.

Fedora 42 needed one further step: its base snapshot still has GNOME's first-run welcome
dialog pending, and it is modal — the Nautilus launcher was located correctly in the dash
(0.942 confidence) but the modal swallowed the click. `pkill -x gnome-tour` does nothing (since
GNOME 41 the dialog is drawn by gnome-shell itself; gnome-tour only starts on "Take Tour") and
OCR cannot find the "Skip" button (small light-on-dark text). **Escape** dismisses it and is
what the playbook now does, leaving no state behind in the guest.

## Prerequisites / not shipped

Running these experiments needs six environments — `ubuntu-2004`, `ubuntu-2204`,
`ubuntu-2404`, `kubuntu-2004`, `kubuntu-2204`, `kubuntu-2404`. This paragraph used to say that
**none** of them existed in this checkout and that three could not even be built for want of an
OS profile. Both statements are now out of date: as of 2026-07-28 `~/.adare/os-profiles/` ships
`kubuntu2004`, `kubuntu2204`, `kubuntu2404`, `ubuntu2004`, `ubuntu2204`, `ubuntu2404`,
`fedora41` and `fedora42` each with an `arm64` variant, plus `fedora41kdearm64` /
`fedora42kdearm64` (aarch64 only), and aarch64 images exist for every environment in the table
above.

The Kubuntu profiles are still `install_mode: gui-auto` with no bundled ISO, so rebuilding them
needs a user-supplied ISO and a GUI-automated install. Two image-level rough edges are worth
knowing before reusing these environments (both are described with their evidence under
*Verification status*): `kubuntu-2004-r2`'s Plasma panel carries no application launchers at
all, and `kubuntu-2204` takes longer than the playbook's first action to bring up its graphical
session.

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
now `{{ adare_user_documents }}` / `{{ adare_user_home }}`. A third fix was needed to make it
run at all — the Escape keypress that dismisses GNOME's modal first-run dialog, described under
*Click mode* above.

It is now the one experiment here with a **green run against a live VM on both possible
readings** of where it belongs (`01KYMJH375W6PKR3H49MHMFXXH`), and the artifact it pulled is
worth keeping in view when the decision is made, because it shows the same GTK writer the
Ubuntu variants rely on:

```xml
<bookmark:application name="org.gnome.Nautilus" exec="'gnome-text-editor %U'" count="1"/>
```

with microsecond timestamps (`added="2026-07-28T14:38:51.074225Z"`). An earlier note here that
`fedora41` was the only Fedora OS profile shipped is out of date: `fedora42`, `fedora42arm64`
and `fedora42kdearm64` all exist, and `fedora-42` is a working environment.

## Verifying offline

The playbooks need the VMs, but the assertion contracts can be checked without them, against a
hand-written sample artifact — still the fastest way to review an assertion change:

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

### `text_file_accessed` has now run (2026-07-28)

Every `xml.*` assertion above was executed against hand-written 20.04-shaped and
24.04-shaped sample artifacts, each with a negative control, and the tolerance-placeholder
path was driven end-to-end with synthesised `variable_metadata`.

`text_file_accessed` (`standard.file_timestamps`) used to be the exception: it is `QGA_PROBE`,
so it needs a live guest, *and* its `expected_time` parameter is union-typed, so it also trips
the dry-run bug above. Being doubly un-dry-runnable, it had been verified **by source reading
only** — `_get_file_timestamp` accepts `timestamp_type: accessed`, and `comparison_type:
within_last` with `within_duration` needs no `expected_time` at all, which is why that
comparison was chosen over `after` — and this section warned that a first-run failure should be
read as suspect-the-test.

It has now run on live guests and passed unmodified on all four verified environments
(`kubuntu-2404`, `kubuntu-2204`, `kubuntu-2004-r2`, `fedora-42`), reporting *"accessed timestamp
is within last 30m"*. It also demonstrably discriminates rather than passing vacuously: the same
assertion's underlying signal is what showed that the QMP double click never opened the document
— with the access time pinned to `2000-01-01`, the failing runs left it pinned. The
suspect-the-test warning no longer applies.
