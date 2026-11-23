# Linux (`linux.*`)

<!-- Generated; do not edit by hand. -->

Live state of a Linux guest: the status of a systemd unit, running processes and local user accounts, plus a search in the last lines of a plain-text log. The first three ask the running system (in the guest agent through `systemctl`, `pgrep` and the user database, in host test mode through QGA commands) and so need a running Linux guest; `log_entry_exists` reads the log file itself and also works on rotated, compressed logs and on a disk image.

## `linux.log_entry_exists`

tests if one of the last lines of a text log contains a string or matches a regex

Pass when one of the last `max_lines` lines of text log `dst` matches `content`.

**Use for:** checking an action left a trace in a plain-text log (syslog, auth.log, app logs; not the binary journal). To count entries, or to search the whole file, use text.line_count.

asserts: content, exists · formats: text, system · runs: guest agent, host test mode or hostside; dry-run on a local file · os: linux

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`)

**Does not support:**
- Regex values (!re) (`regex_tag`): A `!re` or `!timestamp` value (or a placeholder left at run time) in `content` is an error; write the regex as a plain string with `regex_match: true`.
- Text encodings (`encoding`): There is no `encoding` parameter; the encoding is detected (BOM, UTF-16, else UTF-8) and undecodable bytes are replaced.
- Counts with a comparison (`count_comparison`): It asserts one matching line; to count lines use text.line_count.

**Not for:**
- how many lines match, or a match anywhere in the whole file → `text.line_count`
- a string in a binary or UTF-16 file, counted or absent → `text.occurrence_count`
- the binary systemd journal → `text.occurrence_count`
- a regex anywhere in a text file, not line by line → `standard.file_content_matches_regex`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path of the log; a glob must match exactly one path, `archive!member` reads a rotated, compressed log (`/var/log/syslog.2.gz!`). A missing file is an error. The encoding is detected (BOM, UTF-16, else UTF-8); undecodable bytes are replaced, so binary garbage does not stop the search. |
| **content** | `str` |  | With `regex_match` (default) a Python regex searched in each line (`re.search`, case-sensitive; `(?i)` for case-insensitive); an invalid regex, a POSIX class (`[[:space:]]`) or a `!re`/`!timestamp` tag is an error. Otherwise a substring a line must contain. |
| regex_match | `bool` | `True` | `True` (default): `content` is a regex; `False`: a plain substring. |
| max_lines | `int` | `1000` | How many trailing lines to search (default 1000); must be positive. |

**Outcomes:**
- PASSED: at least one of the last `max_lines` lines matches `content`
- FAILED: the log was read and none of the searched lines matches
- ERROR: the log does not exist or is a directory; a glob matches no file or more than one
- ERROR: an invalid regex, a POSIX class (`[[:space:]]`) or a `!re` / `!timestamp` value in `content`
- ERROR: `max_lines` is not a positive integer; the file cannot be read

**Limits:**
- Only the last `max_lines` lines (default 1000) are searched; an older entry fails. Raise `max_lines` or use text.line_count for the whole file.
- `content` is a Python regex by default (`re.search` in each line, case-sensitive; `(?i)` for case-insensitive), no `grep` pattern. `.`, `(` and `[` are regex syntax; use `regex_match: false` for a literal substring.
- A match never spans lines.
- The binary systemd journal is not a text log; export it with `journalctl` in a `run` action first.
- It reads the file itself, so it also works in host test mode and in the hostside backend, and on any OS (the collection name notwithstanding).

**Use cases:**
- A system event was logged: Logins, `sudo`, package installs in `auth.log` or `syslog`.
- An application logged an action: An opened file, an error or a sync in an application log.
- Rotated logs: `/var/log/syslog.2.gz!` reads a compressed, rotated log.
- Nothing was logged: `expect_to_fail: true` asserts that no recent line matches; a missing log is still an error.

**Examples:**

*the login was logged* → PASSED

```yaml
tests:
- name: the_login_was_logged
  function: linux.log_entry_exists
  parameter:
    dst: /var/log/auth.log
    content: 'session opened for user alice'
```

*a regex in a rotated, compressed log* → PASSED

```yaml
tests:
- name: a_regex_in_a_rotated_compressed_log
  function: linux.log_entry_exists
  parameter:
    dst: /var/log/auth.log.2.gz!
    content: 'sshd\[\d+\]: Accepted password for \w+'
    max_lines: 5000
```

*a literal substring with regex characters* → PASSED. `(` and `.` would be regex syntax; `regex_match: false` searches them literally.

```yaml
tests:
- name: a_literal_substring_with_regex_characters
  function: linux.log_entry_exists
  parameter:
    dst: /home/user/.local/share/app/app.log
    content: 'opened report (final).odt'
    regex_match: false
    max_lines: 500
```

*one log among rotated files, by glob* → PASSED. The glob must match exactly one file.

```yaml
tests:
- name: one_log_among_rotated_files_by_glob
  function: linux.log_entry_exists
  parameter:
    dst: /var/log/app/app-*.log
    content: '(?i)sync failed'
```

*an entry older than max_lines fails* → FAILED. Only the tail of the log is searched.

```yaml
tests:
- name: an_entry_older_than_max_lines_fails
  function: linux.log_entry_exists
  parameter:
    dst: /var/log/app/app.log
    content: Segmentation fault
    max_lines: 3
```

*a POSIX character class is an error* → ERROR. Python regexes read `[[:space:]]` as a character set that never matches, so it is refused; write `\s`.

```yaml
tests:
- name: a_posix_character_class_is_an_error
  function: linux.log_entry_exists
  parameter:
    dst: /var/log/auth.log
    content: 'user[[:space:]]alice'
```

**Related:**
- `text.line_count`: `expected_count: 0` asserts that no line of the whole file matches, which this function cannot.

## `linux.process_running`

tests if a process is running with expected number of instances (Linux only)

Pass when `pgrep -f process_name` finds at least `min_instances` processes.

**Use for:** checking an application/daemon is (still) running after an action. Linux only. No matching process always fails, even with `min_instances: 0`.

asserts: state, count · formats: system · runs: guest agent or host test mode; not hostside (needs a live guest); no dry-run · os: linux

**Supports:** Placeholders ({{ variable }}) (`placeholder`)

**Does not support:**
- Counts with a comparison (`count_comparison`): Only "at least `min_instances`"; there is no exact count, no maximum and no `expected_count: 0`.
- Negative tests (absence) (`negative`): No match always fails, even with `min_instances: 0`; "not running" needs `expect_to_fail`.

**Not for:**
- the state of a systemd unit → `linux.system_service_status`
- a program is shown on screen → `visual.exists`

| parameter | type | default | description |
|---|---|---|---|
| **process_name** | `str` |  | Extended regex matched against each process's FULL command line (`pgrep -f`), so `someapp` also matches `/usr/lib/someapp/someapp --worker`. |
| min_instances | `int` | `1` | Minimum number of matching PIDs (default 1). |

**Outcomes:**
- PASSED: `pgrep -f process_name` finds at least `min_instances` processes
- FAILED: no process matches (also with `min_instances` 0)
- FAILED: fewer than `min_instances` processes match
- ERROR: the guest is not Linux; `pgrep` is missing or does not answer within 10 s
- ERROR: the hostside backend (a disk image has no processes; refused before boot)

**Limits:**
- Linux guests only: on a Windows guest it is an error, in the guest agent and in host test mode. Runs in the guest agent, or in host test mode as a QGA command; not in the hostside backend.
- `process_name` is an extended regex matched against the FULL command line (`pgrep -f`): `someapp` also matches `/usr/lib/someapp/someapp --worker` and an editor that has `someapp.conf` open. Anchor it (`^/usr/bin/someapp`) to be strict.
- A pattern such as `python` can match the guest agent itself.
- Host test mode matches the same way (`pgrep -f` over QGA, its own shell left out of the count) and honours `min_instances`.
- It does not check the user, the arguments or how long the process has run.

**Use cases:**
- An application is still running: After an action that should not close it (save, export).
- Worker processes: `min_instances: 3` for a program that starts several workers.
- An application was closed: `expect_to_fail: true`; a missing process is a failure, so the inverted test passes.

**Examples:**

*the application runs* → PASSED

```yaml
tests:
- name: the_application_runs
  function: linux.process_running
  parameter:
    process_name: someapp
```

*at least three workers* → PASSED

```yaml
tests:
- name: at_least_three_workers
  function: linux.process_running
  parameter:
    process_name: '^/usr/lib/someapp/someapp --type=worker'
    min_instances: 3
```

*a process that does not run* → FAILED

```yaml
tests:
- name: a_process_that_does_not_run
  function: linux.process_running
  parameter:
    process_name: no-such-daemon
```

## `linux.system_service_status`

tests if a systemd service has expected status (Linux only)

Pass when `systemctl is-active <service_name>` prints exactly `expected_status`.

**Use for:** checking a systemd unit was started/stopped by an action. Linux guests only (other OSes, a missing `systemctl` or a 10 s timeout are execution errors).

asserts: state, value · formats: system · runs: guest agent or host test mode; not hostside (needs a live guest); no dry-run · os: linux

**Supports:** Placeholders ({{ variable }}) (`placeholder`)

**Does not support:**
- Regex values (!re) (`regex_tag`): `expected_status` is compared exactly; a `!re` value never matches.

**Not for:**
- whether a program is running, whatever started it → `linux.process_running`
- a service left a line in its log file → `linux.log_entry_exists`

| parameter | type | default | description |
|---|---|---|---|
| **service_name** | `str` |  | Unit name as given to systemctl, e.g. `ssh` or `cups.service`. |
| **expected_status** | `str` |  | Exact, case-sensitive `is-active` output: `active`, `inactive`, `failed`, `activating`, `deactivating` ... (unknown units usually print `inactive`). |

**Outcomes:**
- PASSED: `systemctl is-active <service_name>` prints exactly `expected_status`
- FAILED: the unit is in another state (the output is reported)
- FAILED: an unknown unit (`systemctl` usually prints `inactive` for it, which passes when that was expected)
- ERROR: the guest is not Linux; `systemctl` is missing or does not answer within 10 s
- ERROR: the hostside backend (a disk image has no running services; refused before boot)

**Limits:**
- Linux guests with systemd only. Runs in the guest agent, or in host test mode as a QGA command; not in the hostside backend.
- `expected_status` is the exact, case-sensitive output of `is-active`: `active`, `inactive`, `failed`, `activating`, `deactivating`, `reloading` ...
- An unknown unit and a stopped unit both print `inactive`; the test cannot tell them apart.
- In host test mode a failed `systemctl` call reads as `unknown` and fails instead of being an error.
- The state is read at the test's position; it says nothing about whether the unit is enabled at boot.

**Use cases:**
- An action started or stopped a service: `active` after enabling a feature in the GUI, `inactive` after turning it off.
- A service did not crash: `expect_to_fail` on `failed` is weaker than asserting `active`.

**Examples:**

*the SSH server is running* → PASSED

```yaml
tests:
- name: the_ssh_server_is_running
  function: linux.system_service_status
  parameter:
    service_name: ssh
    expected_status: active
```

*a unit stopped by the action* → PASSED

```yaml
tests:
- name: a_unit_stopped_by_the_action
  function: linux.system_service_status
  parameter:
    service_name: cups.service
    expected_status: inactive
```

*a unit that crashed* → FAILED. Fails while the unit runs normally (`active`).

```yaml
tests:
- name: a_unit_that_crashed
  function: linux.system_service_status
  parameter:
    service_name: ssh
    expected_status: failed
```

## `linux.user_exists`

tests if a user account exists with optional UID and home directory checks (Linux only)

Pass when local user `username` exists (`pwd.getpwnam`) and optional UID/home match.

**Use for:** verifying an account was created by an installer or admin action. Linux only.

asserts: state, exists · formats: system · runs: guest agent or host test mode; hostside; no dry-run · os: linux

**Supports:** Placeholders ({{ variable }}) (`placeholder`)

**Not for:**
- a user's home folder or a file in it exists → `standard.file_exists`
- who owns a file → `standard.file_permissions`

| parameter | type | default | description |
|---|---|---|---|
| **username** | `str` |  | Login name, exact and case-sensitive. |
| uid | `int` | `None` | Expected numeric UID; `None` skips the check. |
| home_dir | `str` | `None` | Expected home directory, compared as an exact string (a trailing `/` matters); `None` skips the check. |

**Outcomes:**
- PASSED: the local account `username` exists and `uid` / `home_dir` (when given) match
- FAILED: no account `username`
- FAILED: the account has another UID or home directory
- ERROR: the guest is not Linux, or the Python `pwd` module is missing

**Limits:**
- Linux guests only (on Windows an error). In the guest agent it asks the user database (`pwd.getpwnam`, so NSS sources such as LDAP count); in host test mode it runs `getent passwd` (the same user database); in the hostside backend it reads `/etc/passwd` of the disk image, so accounts from NSS sources such as LDAP are not seen. `uid` and `home_dir` are checked in all three.
- `username` is exact and case-sensitive; `home_dir` is compared as a string (a trailing `/` matters).
- It does not check groups, the shell, the password or whether the account is locked.

**Use cases:**
- An installer or admin action created an account: A service user created by a package, or a user added in the settings GUI.
- An account was removed: `expect_to_fail: true` after deleting the user.

**Examples:**

*account with its home directory* → PASSED

```yaml
tests:
- name: account_with_its_home_directory
  function: linux.user_exists
  parameter:
    username: alice
    home_dir: /home/alice
```

*first regular user* → PASSED

```yaml
tests:
- name: first_regular_user
  function: linux.user_exists
  parameter:
    username: alice
    uid: 1000
```

*a trailing slash is a different home directory* → FAILED. `home_dir` is compared as text, so `/home/alice/` does not match `/home/alice`.

```yaml
tests:
- name: a_trailing_slash_is_a_different_home_directory
  function: linux.user_exists
  parameter:
    username: alice
    home_dir: /home/alice/
```
