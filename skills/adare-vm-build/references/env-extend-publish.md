# Environments: create, extend, verify, publish — reference

## Create

```sh
adare env create <name> [-p project] [--with-vm /path/to.ova]
```

Creates an environment descriptor. `--with-vm` loads a VM file (OVA) automatically
during creation. To register an existing environment file, use `adare env load`
(covered in `adare-experiment`).

## Extend

```sh
adare env extend <source> -n <new-name> [options]
```

`<source>` is an environment name, environment ULID, or VM name. Two modes:

### Declarative (default)

```sh
adare env extend ubuntu2404 -n ubuntu2404-libre \
  --install "libreoffice:apt-get install -y libreoffice" \
  --install "gimp:apt-get install -y gimp" --shell
```

| Flag | Meaning |
| --- | --- |
| `-i, --install TEXT` | Post-setup install as `"name:command"` (repeatable). |
| `--from-file PATH` | YAML file listing post-setup installs to add. |
| `--shell` | Run `--install` commands through a shell. |
| `--cwd TEXT` | Working directory for `--install` commands. |

The new env is a **strict superset** of the source and **shares the same underlying
base disk** — no new VM is created. This is the reproducible, version-controllable
way to add software.

### Interactive (QEMU only)

```sh
adare env extend ubuntu2404 -n ubuntu2404-custom --interactive [--console] \
  [--ram 8192] [--cpus 4] [--disk-name …]
```

Boots a throwaway overlay of the base disk in a GUI window so you install software by
hand. Default is a GUI-only window; `--console` also opens a terminal REPL that
**records typed commands as reproducible installs**. On shutdown you choose to store
(overlay is flattened into a new standalone disk, registered as a NEW base VM + env)
or discard. May be combined with `--install`.

Shared flags: `-d/--description`, `-t/--tag` (repeatable), `-f/--force`, `-p/--project`,
`--allow-emulation` (interactive mode; needed when the base disk's guest arch differs
from the host — without it `resolve_accel` refuses to boot).

**Prefer declarative** — it's reproducible and disk-sharing. Use interactive only
when the software has no scriptable install (GUI-only setup wizard). Either way, keep
the guest minimal — no logs/markers left behind (no-VM-remnants rule).

### Not the right tool for a *recipe* environment

`env extend --interactive` produces a **baked** disk: whatever you install by hand is
frozen into an image that has to be shipped as bytes and whose provenance is a human's
memory. For a recipe environment, declare the work as `recipe.provision` instead — it
runs at build time over the QEMU guest agent, is reproducible from the YAML alone, and
logs every command's exit code and output to
`~/.adare/qemu/build-logs/provision-<hash>.log`. See `create-recipes.md`.

The Autopsy case study is the worked example: two ~110-line recipe YAMLs replaced ~97
GB of interactively-built, unshippable disk.

## Verify

```sh
adare env verify <name> [-p project]
```

Idempotently registers the shipped `verify_vm` example experiment, attaches the
environment, and runs it in the foreground with live progress. **Verify before you
rely on or publish an environment.**

## Publish a recipe environment

A recipe ships as text, so "publishing" means making its **ISO** obtainable. Which
form is required depends on the platform:

| Profile platform | Required form |
| --- | --- |
| Linux | `recipe.iso` = an `http(s)` URL + `recipe.iso_sha256`. Linux ISOs are freely redistributable, so a published URL is required. |
| Windows | Either a URL, or the BYO form: `recipe.iso_name` (bare filename) + `recipe.iso_sha256` + optional plain-text `recipe.iso_notes`. Microsoft media cannot lawfully be rehosted. |

```sh
adare env recipe-byo <name> [--iso-name Win11_25H2_English_Arm64_v2.iso] [--iso-notes "..."]
```

Rewrites a local-ISO-path recipe into the BYO form. **Hash-neutral** — how a consumer
obtained the ISO is not a build input, so an already-built disk stays a cache hit.
Only the descriptor changes.

`iso_sha256` is required in both forms (it is the integrity boundary) and must be
**canonical lowercase**: the server stores it verbatim and other clients compare it
case-sensitively, so an uppercase digest publishes an environment nobody can build.
The declared `os.platform` must also match what the profile actually builds, in both
directions.

Consumers supply a BYO ISO via `~/.adare/isos/`, `$ADARE_ISO_DIR`, or
`adare env load <env>.yml --iso <path-or-dir>`.

## Publish a baked environment (local disk → URL + sha256)

```sh
adare env publish-prepare <name> --vm-url <https-url> [--vm-format qcow2|ova|vmdk|vdi|img|raw] [--verify-url]
```

Hashes the local disk referenced by the env's `vm:` field, then rewrites the
descriptor to reference `--vm-url` with `vm_type=url`, the disk format, and the
computed `vm_sha256`. Consumers re-verify that hash after downloading.

- **`--vm-url` is required** and may point at any host, including
  owncloud/Nextcloud share links.
- **`--vm-format`** is inferred from the local disk extension when omitted; pass it
  if neither the local disk nor the URL names a recognized format.
- **`--verify-url`** downloads the hosted URL and confirms its bytes hash-match the
  local disk — catches a wrong/HTML share link or a changed upload. Use it whenever
  the disk is already hosted.

The **sha256 is mandatory** and enforced at multiple layers plus a client pre-flight
— the whole point is that a shared environment is YAML + an external disk URL whose
integrity is verifiable. Never distribute a descriptor without it.

To push the descriptor to the shared repo afterward, see `adare web submit
environment` in the `adare-experiment` sharing reference (external send — confirm
first).
