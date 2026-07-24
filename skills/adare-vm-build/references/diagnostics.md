# VM diagnostics & housekeeping — reference

## Doctors

```sh
adare vm doctor
```

Reports host-level availability of: `qemu-system`/`qemu-img`, OVMF firmware, `swtpm`,
the libvirt Python binding, and (on Apple Silicon) the `wimlib`/`7z`/`xorriso` trio
used for the Win11-ARM64 legacy-boot workaround. **Detect-and-report only — never
installs anything, always exits 0.** Run it before any `vm create`.

```sh
adare vm gui-doctor
```

Preflights the vision-LLM used for GUI automation (`ADARE_VLLM_*`): confirms the
endpoint (e.g. Ollama Cloud) is reachable and detects which coordinate convention the
model returns, recommending `ADARE_VLLM_COORD_SPACE`. Needed only for GUI-automated
installs / `dev agent`.

## Inspect

```sh
adare vm list                 # all VMs (aliases: l)
adare vm info <VM_ID>          # detail for one VM
adare vm usage                # instance usage statistics
adare vm snapshot list        # all snapshots (aliases: l)
```

## Reclaim & remove (destructive)

```sh
adare vm prune                       # preview orphaned base disks (deletes nothing)
adare vm prune --force               # reclaim orphaned <name>-base.qcow2 + -nvram.fd
adare vm prune --force --sockets     # also reap dead QMP/QGA sockets in run/
```

`prune` is the garbage collector for debris (orphaned base disks whose VM is no
longer in the DB) left by older removal paths or crashes. **Dry-run by default** —
always preview before `--force`.

```sh
adare vm remove --id <ulid>              # one instance
adare vm remove --stopped                # all stopped instances
adare vm remove --experiment <id>        # instances for an experiment
adare vm remove --env <ulid> --force     # all VMs for an environment
adare vm remove --all --force            # ALL instances incl. running
adare vm snapshot remove <…>             # delete one snapshot
adare vm reset --force                   # reset ALL VMs — use with extreme caution
```

`vm remove --all --force` and `vm reset --force` wipe VMs system-wide. Confirm the
scope with the user before running either; prefer the narrowest selector (`--id`,
`--env`, `--stopped`) that does the job.

## Live view

```sh
adare vm watch <name>                    # read-only live screen in the browser
adare vm watch <name> --interactive      # allow input
```

Opens VirtualSpice's display page pointed at the VM (requires VirtualSpice running,
started by `adare web start`). Toggle view-only/interactive live from VirtualSpice's
own toolbar either way. For driving a session VM rather than just watching, see
`adare-devvm`.
