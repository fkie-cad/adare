# Windows (`windows.*`)

<!-- Generated; do not edit by hand. -->

The registry of a running Windows guest: whether a key exists and whether a value has the expected data (and type). The functions ask the live registry (in the guest agent through `winreg`, in host test mode through PowerShell over QGA); they do not read offline hive files, and the hostside backend, which has no running Windows guest, cannot run them.

## `windows.registry_key_exists`

tests if Windows registry key exists (Windows only)

Pass when the registry key `key_path` can be opened with `winreg.OpenKey`.

**Use for:** checking an install/config action created a key. Windows guests only (other OSes error). A key that exists but denies read access is an execution error, not a pass.

asserts: state, exists · formats: registry · runs: guest agent or host test mode; not hostside (needs a live guest); no dry-run · os: windows

**Supports:** Placeholders ({{ variable }}) (`placeholder`)

**Not for:**
- the data of a value under the key → `windows.registry_value_matches`
- a file or folder an installer created → `standard.file_exists`
- a section or key in an INI or config file → `ini.contains_key`

| parameter | type | default | description |
|---|---|---|---|
| **key_path** | `str` |  | `HIVE/sub/key` with `/` or `\` separators. Hive is case-insensitive: `HKEY_CLASSES_ROOT`/`HKCR`, `HKEY_CURRENT_USER`/`HKCU`, `HKEY_LOCAL_MACHINE`/`HKLM`, `HKEY_USERS`/`HKU`, `HKEY_CURRENT_CONFIG`/`HKCC`. A bare hive or unknown hive is an execution error. HKCU is the agent's user. |

**Outcomes:**
- PASSED: the key `key_path` can be opened for reading
- FAILED: the key does not exist
- ERROR: the guest is not Windows, or `winreg` is missing
- ERROR: a bare or unknown hive (`HKLM` alone, `HKEY_FOO\x`)
- ERROR: the key exists but denies read access
- ERROR: the hostside backend (refused before boot)

**Limits:**
- Windows guests only. Runs in the guest agent, or in host test mode as a PowerShell `Test-Path` over QGA.
- Hives: `HKEY_CLASSES_ROOT` / `HKCR`, `HKEY_CURRENT_USER` / `HKCU`, `HKEY_LOCAL_MACHINE` / `HKLM`, `HKEY_USERS` / `HKU`, `HKEY_CURRENT_CONFIG` / `HKCC`, case-insensitive. `/` and `\` both separate keys.
- `HKCU` is the hive of the user the test runs as (the agent's user; in host test mode the account QGA commands run as), not necessarily the user who did the GUI actions; address another user through `HKU\<SID>`.
- A key exists or not: values, default value and subkeys are not looked at.
- On 64-bit Windows the view (WOW6432Node redirection) is the one of the process that runs the test.
- In host test mode a bad hive and a denied key read as "does not exist" and fail instead of being an error.

**Use cases:**
- An installer or a setting created a key: Vendor keys under `HKCU\Software` or `HKLM\SOFTWARE`.
- A key was removed: `expect_to_fail: true` after uninstalling or resetting; an unreadable key is still an error.
- A list of last used items or a file association was written: The key appears only after the first use of a feature.

**Examples:**

*the application's settings key* → PASSED

```yaml
tests:
- name: the_application_s_settings_key
  function: windows.registry_key_exists
  parameter:
    key_path: 'HKCU\Software\ExampleVendor\ExampleApp'
```

*short hive name and forward slashes* → PASSED

```yaml
tests:
- name: short_hive_name_and_forward_slashes
  function: windows.registry_key_exists
  parameter:
    key_path: HKLM/SOFTWARE/Microsoft/Windows/CurrentVersion
```

*a key that was never created* → FAILED

```yaml
tests:
- name: a_key_that_was_never_created
  function: windows.registry_key_exists
  parameter:
    key_path: 'HKCU\Software\ExampleVendor\NotInstalled'
```

*a bare hive is an error* → ERROR. The path needs a hive and a subkey.

```yaml
tests:
- name: a_bare_hive_is_an_error
  function: windows.registry_key_exists
  parameter:
    key_path: HKLM
```

## `windows.registry_value_matches`

tests if Windows registry value matches expected value (Windows only)

Pass when registry value `value_name` under `key_path` equals `expected_value`.

**Use for:** asserting a setting/MRU value written by an application. Windows only. A missing key or value fails.

asserts: state, value · formats: registry · runs: guest agent or host test mode; not hostside (needs a live guest); no dry-run · os: windows

**Supports:** Placeholders ({{ variable }}) (`placeholder`)

**Does not support:**
- Regex values (!re) (`regex_tag`): `expected_value` is compared with `==`; there is no regex matching and a `!re` value never matches.
- Ordered comparison of numbers and times (`ordered_comparison`): Only equality; no greater, less or tolerance.
- Times as expected values (!timestamp) (`timestamp_tag`): A time stored in a value (FILETIME bytes, a number) is compared as raw data only.

**Not for:**
- a key exists, whatever its values → `windows.registry_key_exists`
- a setting stored in an INI or config file → `ini.value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **key_path** | `str` |  | `HIVE/sub/key` (see windows.registry_key_exists), `/` or `\` separators. |
| **value_name** | `str` |  | Name of the value; `''` selects the key's default value. |
| **expected_value** | `str \| int \| bytes` |  | Compared with Python `==` against the `winreg` data, so the type matters: REG_DWORD/QWORD -> int, REG_SZ/REG_EXPAND_SZ -> str (unexpanded), REG_BINARY -> bytes. REG_MULTI_SZ (a list) can never match. A `{{ }}` placeholder still present at run time is resolved, and all-digit results become int. |
| value_type | `str \| None` | `None` | Optional type name check, case-insensitive, e.g. `REG_SZ`. Canonical names: REG_NONE, REG_SZ, REG_EXPAND_SZ, REG_BINARY, REG_DWORD, REG_DWORD_BIG_ENDIAN, REG_LINK, REG_MULTI_SZ, REG_RESOURCE_LIST, REG_FULL_RESOURCE_DESCRIPTOR, REG_RESOURCE_REQUIREMENTS_LIST, REG_QWORD. The legacy aliases `REG_DWORD_LITTLE_ENDIAN` and `REG_QWORD_LITTLE_ENDIAN` (and `UNKNOWN_TYPE_11`, the name earlier versions reported) are accepted for REG_DWORD / REG_QWORD. `None` skips the check. |

**Outcomes:**
- PASSED: the value `value_name` under `key_path` equals `expected_value` (and has type `value_type`, when given)
- FAILED: the key or the value does not exist
- FAILED: the data differs (also when only the Python type differs, `'1'` vs `1`)
- FAILED: the type name differs from `value_type`
- FAILED: a `REG_MULTI_SZ` value (a list), which never equals `expected_value`
- ERROR: the guest is not Windows, or `winreg` is missing
- ERROR: a bare or unknown hive
- ERROR: the key or value denies read access
- ERROR: the hostside backend (refused before boot)

**Limits:**
- Windows guests only. Runs in the guest agent, or in host test mode as PowerShell over QGA; hives and separators as in windows.registry_key_exists.
- `value_name: ''` selects the default value of the key.
- In the guest agent the type of `expected_value` matters: `REG_DWORD` / `REG_QWORD` data is an int (write `1`, not `'1'`), `REG_SZ` / `REG_EXPAND_SZ` a string (unexpanded, `%USERPROFILE%` stays), `REG_BINARY` bytes. A placeholder that resolves to digits becomes an int.
- `value_type` uses the canonical names: `REG_NONE`, `REG_SZ`, `REG_EXPAND_SZ`, `REG_BINARY`, `REG_DWORD`, `REG_DWORD_BIG_ENDIAN`, `REG_LINK`, `REG_MULTI_SZ`, `REG_RESOURCE_LIST`, `REG_FULL_RESOURCE_DESCRIPTOR`, `REG_RESOURCE_REQUIREMENTS_LIST`, `REG_QWORD` (case-insensitive). The guest agent reports a `REG_DWORD` / `REG_QWORD` under these names and also accepts the legacy aliases `REG_DWORD_LITTLE_ENDIAN` / `REG_QWORD_LITTLE_ENDIAN` (and `UNKNOWN_TYPE_11`) for them.
- Host test mode (PowerShell over QGA) compares and names the same way: DWORD/QWORD data is an int, strings are not expanded, `value_type` accepts the canonical and the legacy names and the report uses the canonical ones.
- `HKCU` is the hive of the user the test runs as (the agent's user; in host test mode the account QGA commands run as), not necessarily the user who did the GUI actions.

**Use cases:**
- A setting changed in the GUI: A checkbox or option stored as `REG_DWORD` 0/1 or a string.
- A last used entry: The value an application writes for the last opened folder or file.
- Version or install path written by an installer: A `REG_SZ` under the vendor key.

**Examples:**

*a string setting of the desktop* → PASSED

```yaml
tests:
- name: a_string_setting_of_the_desktop
  function: windows.registry_value_matches
  parameter:
    key_path: 'HKCU\Control Panel\Desktop'
    value_name: ScreenSaveActive
    expected_value: '1'
```

*a DWORD flag* → PASSED. The data of a `REG_DWORD` is an int, so `expected_value` is unquoted.

```yaml
tests:
- name: a_dword_flag
  function: windows.registry_value_matches
  parameter:
    key_path: 'HKCU\Software\ExampleVendor\ExampleApp\Settings'
    value_name: ShowToolbar
    expected_value: 1
```

*string with a type check* → PASSED

```yaml
tests:
- name: string_with_a_type_check
  function: windows.registry_value_matches
  parameter:
    key_path: 'HKCU\Software\ExampleVendor\ExampleApp'
    value_name: InstallDir
    expected_value: 'C:\Program Files\ExampleApp'
    value_type: REG_SZ
```

*a quoted number does not equal a DWORD* → FAILED. In the guest agent `'1'` (a string) is not the int `1` stored in a `REG_DWORD`.

```yaml
tests:
- name: a_quoted_number_does_not_equal_a_dword
  function: windows.registry_value_matches
  parameter:
    key_path: 'HKCU\Software\ExampleVendor\ExampleApp\Settings'
    value_name: ShowToolbar
    expected_value: '1'
```

*a DWORD with a type check* → PASSED. `REG_DWORD` is the canonical name; the legacy alias `REG_DWORD_LITTLE_ENDIAN` is accepted too. A `REG_QWORD` works the same way.

```yaml
tests:
- name: a_dword_with_a_type_check
  function: windows.registry_value_matches
  parameter:
    key_path: 'HKCU\Software\ExampleVendor\ExampleApp\Settings'
    value_name: ShowToolbar
    expected_value: 1
    value_type: REG_DWORD
```
