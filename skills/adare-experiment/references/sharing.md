# Sharing experiments over the web — reference

**External send.** Every command here talks to the ADARE web server. Publishing or
submitting **sends experiment data off this machine**; it may be cached or indexed
server-side even if later deleted. Confirm with the user before publishing, and
prefer publishing a `--prod` (integrity-checked) run.

## Auth

```sh
adare web login       # interactive login
adare web status      # show login status
adare web logout
```

## Check before you send

```sh
adare web check experiment <…>     # does this experiment exist on the server?
adare web check run <…>            # does this run exist on the server?
```

## Publish a run

```sh
adare web publish <ULID> [-p PROJECT]
```

Publishes one experiment run to the server with a progress display. Publish the ULID
of a **production** run.

## Submit as a PR to the shared repository

```sh
adare web submit experiment    <…>
adare web submit environment   <…>
adare web submit testfunction  <…>
```

`submit` opens a pull request against the shared repo — use it to contribute an
experiment, environment descriptor, or testfunction back. (Run `adare web submit
<kind> --help` for that kind's exact args.)

## Download

```sh
adare web download experiment   <…>
adare web download environment  <…>
adare web download testfunction <…>
adare web download bundle       <…>   # experiment + all its dependencies
```

`bundle` is the convenient one: it pulls an experiment together with everything it
needs. Use `--help` on each subcommand for its arguments.

## Sync everything

```sh
adare web sync [-p PROJECT]
```

Syncs all environments and experiments in the project with the server. Broad
operation — know what's local vs remote before running it.

## Related

- `adare web start` / `adare web services` / `adare web build` belong to the local
  web UI (FastAPI + VirtualSpice), not to sharing — see `adare-devvm` for the live
  screen viewer (`vm watch` / `dev start --watch`).
