# Inspecting runs and experiments — reference

## Runs

```sh
adare run list                                   # every run
adare run list --filter <dotnotation>            # filter (see below)
adare run info [<ULID>]                           # run detail; latest run if ULID omitted
adare run remove <ULID>                           # delete one run (destructive)
```

### Dotnotation filter

`--filter` takes `[project][.environment][.experiment]` — a left-anchored path where
trailing segments are optional:

- `myproject` → all runs in the project
- `myproject.ubuntu24` → runs on that environment
- `myproject.ubuntu24.test_csv` → runs of that one experiment

`run info` with no ULID shows the **latest** run — handy right after `exp run`.

## Experiments

```sh
adare exp info <NAME>                # by name in the current project
adare exp info -u <ULID>             # by experiment ULID
adare exp info -d <project.env.exp>  # by dotnotation
adare exp list [-e <env>]            # list experiments (aliases: l)
```

## Environments

```sh
adare env list                       # environments in the project (aliases: l)
adare env info <ENVIRONMENT_NAME>    # detail for one environment
```

## Output format

All of these honor the global `--output-format/--format [rich|json|yaml]` and
`--output-file PATH` options — use `--format json` when you want to parse a run's
fields programmatically rather than read the rich table:

```sh
adare --format json run info <ULID>
```
