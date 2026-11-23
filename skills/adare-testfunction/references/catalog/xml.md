# XML (`xml.*`)

<!-- Generated; do not edit by hand. -->

XML files, also XML inside office documents (`report.docx!/docProps/core.xml`): whether an element exists, how many there are, the text or an attribute of an element, two values of one file compared as numbers or times, and the namespace of the root element. Elements are selected with the ElementTree `ElementPath` subset of XPath, the same parser on every guest.

## `xml.attribute_matches`

tests if XML element attribute matches expected value with regex and timestamp tolerance support

Pass when `attribute` of the FIRST element selected by `xpath` equals/matches `expected_value`.

With `comparison_type` (`greater`, `less`, ...), `tolerance` or the time parameters the attribute value is compared as a number or timestamp (`case_sensitive` is then ignored); to compare two values of one file use xml.values_compare.

**Use for:** asserting attribute values (an id, a state, a timestamp ...). No matching element or a missing attribute fails.

asserts: value, order · formats: xml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Ordered comparison of numbers and times (`ordered_comparison`)

**Does not support:**
- Several matches (wildcard_mode) (`wildcard_mode`): Only the first element `xpath` selects is checked; narrow `xpath` with a predicate (`[@ref='x']`).

**Not for:**
- the text of an element → `xml.element_text_matches`
- an element with that attribute value exists or is absent → `xml.element_count`
- two attributes of one file compared with each other → `xml.values_compare`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the XML file; a glob must match exactly one path. A missing file or malformed XML is an execution error. |
| **xpath** | `str` |  | ElementTree `ElementPath` subset, evaluated on the root element: `//tag` (any depth), `/root/child` (first step must be the root tag), `child/grandchild`, predicates `[@attr='v']`, `[tag='v']`, `[@attr]`. Any `(`, `::`, `..` or `\|` (even inside a quoted value) is an execution error, so no functions such as `text()`. |
| **attribute** | `str` |  | Attribute name; namespaced attributes need the `{uri}name` form. |
| **expected_value** | `str` |  | Exact expected value, or a regex with `regex_match`; a single `!re`/`!timestamp` tag is matched by type. |
| regex_match | `bool` | `False` | Search `expected_value` as a Python regex (`re.search`, unanchored). |
| case_sensitive | `bool` | `True` | `False` compares lower-cased / uses `re.IGNORECASE`. |
| namespaces | `dict[str, str]` | `None` | Prefix -> URI map for prefixed names in `xpath` (`{ns: 'http://...'}` + `//ns:item`); `{uri}tag` also works without it. |
| comparison_type | `str` | `'equals'` | `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal`. Anything but `equals`, or any parameter below, compares the value with `expected_value` as a number or point in time (ordered mode; `less` = earlier); a `!re` tag, `{{placeholder}}` or `regex_match` is then an error, and so is a value that is no number or timestamp. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both sides are numbers, else timestamps), `number` or `timestamp`. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |

**Outcomes:**
- PASSED: `attribute` of the first selected element equals or matches `expected_value`
- FAILED: the file was read and `xpath` selects nothing, the first element has no such attribute, or the value does not match
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file is no well-formed XML; an XPath outside the ElementPath subset
- ERROR: an invalid regex or placeholder
- ERROR: in ordered mode, a value that is no number or timestamp, or a `!re` / placeholder / `regex_match` with it
- ERROR: bad ordered parameters (`comparison_type`, `value_type`, `timestamp_epoch`, ...)

**Limits:**
- Only the first selected element is checked.
- A namespaced attribute needs the `{uri}name` form; `namespaces` applies to `xpath` only.
- Without ordered mode an unquoted YAML number (`3`) never equals the attribute text: quote it (`'3'`), or set `value_type: number`.
- XPath rules as in xml.element_exists.

**Use cases:**
- An id, state or flag: An attribute of an entry in a settings or history XML.
- A time stored in an attribute: `comparison_type: greater` against a point in time, or `tolerance` around one.

**Examples:**

*visit count of an entry* → PASSED

```yaml
tests:
- name: visit_count_of_an_entry
  function: xml.attribute_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //entry[@ref='item-1']
    attribute: visits
    expected_value: '3'
```

*entry modified after a point in time* → PASSED

```yaml
tests:
- name: entry_modified_after_a_point_in_time
  function: xml.attribute_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //entry[@ref='item-2']
    attribute: modified
    expected_value: '2026-03-02T09:00:00Z'
    comparison_type: greater
```

*modified time has the expected date* → PASSED

```yaml
tests:
- name: modified_time_has_the_expected_date
  function: xml.attribute_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //entry[@ref='item-1']
    attribute: modified
    expected_value: !re '2026-03-01T'
```

*a missing attribute fails* → FAILED

```yaml
tests:
- name: a_missing_attribute_fails
  function: xml.attribute_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //entry[@ref='item-1']
    attribute: deleted
    expected_value: 'true'
```

## `xml.element_count`

tests the number of XML elements matching XPath expression

Pass when the number of elements selected by `xpath` satisfies `comparison_type` vs `expected_count`.

**Use for:** counting entries; `expected_count: 0` asserts absence (opposite of xml.element_exists).

asserts: count, absent · formats: xml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Counts with a comparison (`count_comparison`), Negative tests (absence) (`negative`)

**Not for:**
- the text or an attribute of the elements → `xml.element_text_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the XML file; a glob must match exactly one path. A missing file or malformed XML is an execution error. |
| **xpath** | `str` |  | ElementTree `ElementPath` subset, evaluated on the root element: `//tag` (any depth), `/root/child` (first step must be the root tag), `child/grandchild`, predicates `[@attr='v']`, `[tag='v']`, `[@attr]`. Any `(`, `::`, `..` or `\|` (even inside a quoted value) is an execution error, so no functions such as `text()`. |
| **expected_count** | `int` |  | Required non-negative integer to compare against; anything else is an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| namespaces | `dict[str, str]` | `None` | Prefix -> URI map for prefixed names in `xpath` (`{ns: 'http://...'}` + `//ns:item`); `{uri}tag` also works without it. |

**Outcomes:**
- PASSED: the number of elements `xpath` selects satisfies `comparison_type`
- FAILED: the file was read and the count comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file is no well-formed XML; an XPath outside the ElementPath subset
- ERROR: a negative or non-integer `expected_count`, or an unknown `comparison_type`

**Limits:**
- XPath rules as in xml.element_exists; select by attribute or child text with `[@attr='v']` / `[tag='v']`.

**Use cases:**
- An entry was removed: `expected_count: 0` with a predicate for that entry after a delete or clean-up action.
- How many entries a list holds: Recent documents, accounts or bookmarks in a settings XML.

**Examples:**

*two recent entries* → PASSED

```yaml
tests:
- name: two_recent_entries
  function: xml.element_count
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: ./recent/entry
    expected_count: 2
```

*the entry is gone* → PASSED

```yaml
tests:
- name: the_entry_is_gone
  function: xml.element_count
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //entry[@ref='item-9']
    expected_count: 0
```

*at least one entry* → PASSED

```yaml
tests:
- name: at_least_one_entry
  function: xml.element_count
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //entry
    expected_count: 1
    comparison_type: greater_equal
```

*a glob matching two files is an error* → ERROR. The glob must match exactly one file, also for a count.

```yaml
tests:
- name: a_glob_matching_two_files_is_an_error
  function: xml.element_count
  parameter:
    dst: /home/user/.config/app/*.xml
    xpath: //entry
    expected_count: 0
```

## `xml.element_exists`

tests if XML element exists at specified XPath

Pass when `xpath` selects at least one element in XML file `dst`.

**Use for:** checking a config/profile XML gained an entry. For "absent" use xml.element_count with `expected_count: 0`.

asserts: exists · formats: xml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`)

**Not for:**
- an element is absent → `xml.element_count`
- the text or an attribute of the element → `xml.element_text_matches`
- how many elements there are → `xml.element_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the XML file; a glob must match exactly one path. A missing file or malformed XML is an execution error. |
| **xpath** | `str` |  | ElementTree `ElementPath` subset, evaluated on the root element: `//tag` (any depth), `/root/child` (first step must be the root tag), `child/grandchild`, predicates `[@attr='v']`, `[tag='v']`, `[@attr]`. Any `(`, `::`, `..` or `\|` (even inside a quoted value) is an execution error, so no functions such as `text()`. |
| namespaces | `dict[str, str]` | `None` | Prefix -> URI map for prefixed names in `xpath` (`{ns: 'http://...'}` + `//ns:item`); `{uri}tag` also works without it. |

**Outcomes:**
- PASSED: `xpath` selects at least one element
- FAILED: the file was read and `xpath` selects nothing
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file is no well-formed XML
- ERROR: `xpath` contains `(`, `::`, `..` or `|` (also inside a quoted value), or is otherwise invalid

**Limits:**
- XPath is the `ElementPath` subset: `//tag`, `/root/child` (the first step must be the root tag), `child/grandchild`, `*`, `[@attr]`, `[@attr='v']`, `[tag='v']`, `[1]`. No functions (`text()`, `contains()`), axes, `..` or unions.
- A prefixed name needs `namespaces` (prefix -> URI); `{uri}tag` works without it. A default namespace has no prefix, so give it one in `namespaces`.

**Use cases:**
- An entry was added: A bookmark, a recent document or an account in a settings or profile XML after an action in the GUI.

**Examples:**

*a recent entry exists* → PASSED

```yaml
tests:
- name: a_recent_entry_exists
  function: xml.element_exists
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //entry[@ref='item-2']
```

*an absolute path starts at the root element* → PASSED

```yaml
tests:
- name: an_absolute_path_starts_at_the_root_element
  function: xml.element_exists
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: /settings/general/theme
```

*an absent element fails* → FAILED. To assert absence use xml.element_count with `expected_count` 0, which passes.

```yaml
tests:
- name: an_absent_element_fails
  function: xml.element_exists
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //entry[@ref='item-9']
```

*an XPath function is an error* → ERROR. `text()` is outside the ElementPath subset; the expression is refused instead of matching nothing.

```yaml
tests:
- name: an_xpath_function_is_an_error
  function: xml.element_exists
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //language/text()
```

*a missing file is an error* → ERROR

```yaml
tests:
- name: a_missing_file_is_an_error
  function: xml.element_exists
  parameter:
    dst: /home/user/.config/app/other.xml
    xpath: //entry
```

**Related:**
- `xml.element_count`: `expected_count: 0` for absence, or how many entries there are

## `xml.element_text_matches`

tests if XML element text content matches expected value with placeholder support for regex and timestamp tolerance

Pass when the text of the element(s) selected by `xpath` equals/matches `expected_value`.

With `comparison_type` (`greater`, `less`, ...), `tolerance` or the time parameters the text is compared as a number or timestamp (`case_sensitive` is then ignored); to compare two values of one file use xml.values_compare.

**Use for:** asserting an XML setting or record value, and document properties of office files: the author of a .docx is `dc:creator` in `report.docx!/docProps/core.xml` (xpath `./dc:creator`, namespaces `{dc: 'http://purl.org/dc/elements/1.1/'}`). "Text" is `element.text`: only the text before the element's first child, not stripped (missing -> `''`). To count elements use xml.element_count.

asserts: value, order · formats: xml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Ordered comparison of numbers and times (`ordered_comparison`), Several matches (wildcard_mode) (`wildcard_mode`)

**Not for:**
- an attribute value → `xml.attribute_matches`
- how many elements there are, or that one is absent → `xml.element_count`
- two values of one file compared with each other → `xml.values_compare`
- a string anywhere in the file, whatever the structure → `text.occurrence_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the XML file; a glob must match exactly one path. A missing file or malformed XML is an execution error. |
| **xpath** | `str` |  | ElementTree `ElementPath` subset, evaluated on the root element: `//tag` (any depth), `/root/child` (first step must be the root tag), `child/grandchild`, predicates `[@attr='v']`, `[tag='v']`, `[@attr]`. Any `(`, `::`, `..` or `\|` (even inside a quoted value) is an execution error, so no functions such as `text()`. No match fails. |
| **expected_value** | `str` |  | Required. Exact expected text (`''` for an empty element), or a regex with `regex_match`. A single `!re`/`!timestamp` tag is matched by type (`case_sensitive` then ignored); an invalid regex is an error. |
| regex_match | `bool` | `False` | Search `expected_value` as a Python regex (`re.search`, unanchored). |
| case_sensitive | `bool` | `True` | `False` compares lower-cased / uses `re.IGNORECASE`. |
| wildcard_mode | `str` | `'any'` | For several matched elements: `any` (default) or `all` must match; other values are an execution error (only checked when several elements match). Allowed: `any`, `all`. |
| namespaces | `dict[str, str]` | `None` | Prefix -> URI map for prefixed names in `xpath` (`{ns: 'http://...'}` + `//ns:item`); `{uri}tag` also works without it. |
| comparison_type | `str` | `'equals'` | `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal`. Anything but `equals`, or any parameter below, compares the value with `expected_value` as a number or point in time (ordered mode; `less` = earlier); a `!re` tag, `{{placeholder}}` or `regex_match` is then an error, and so is a value that is no number or timestamp. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both sides are numbers, else timestamps), `number` or `timestamp`. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |

**Outcomes:**
- PASSED: the text of the selected element (several: `any` one, or `all`) equals or matches `expected_value`
- FAILED: the file was read and `xpath` selects nothing, or the text does not match
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file is no well-formed XML; an XPath outside the ElementPath subset
- ERROR: an invalid regex or placeholder; an invalid `wildcard_mode` when several elements match
- ERROR: in ordered mode, a text that is no number or timestamp, or a `!re` / placeholder / `regex_match` with it
- ERROR: bad ordered parameters (`comparison_type`, `value_type`, `timestamp_epoch`, ...)

**Limits:**
- The text is `element.text`, the text before the first child element, not stripped; an element with no text gives `''`.
- Without ordered mode an unquoted YAML number (`41`) is not converted to text and never equals the element text: quote it (`'41'`), or set `value_type: number`.
- `regex_match` uses `re.search` (unanchored); a `!re` tag uses `re.match` (anchored at the start).
- `wildcard_mode` is only checked when several elements match.
- XPath rules as in xml.element_exists.

**Use cases:**
- A setting has a value: A language, theme or path in a settings XML after it was changed in the GUI.
- Office document properties: The author of a .docx is `dc:creator` in `report.docx!/docProps/core.xml`.
- A counter or time after an action: `comparison_type: greater` against a number, or a `!timestamp` between the times saved around the action.

**Examples:**

*language setting* → PASSED

```yaml
tests:
- name: language_setting
  function: xml.element_text_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: ./general/language
    expected_value: de_DE
```

*author of an office document* → PASSED. The member of the zip container is read through `!`; the `dc` prefix is mapped in `namespaces`.

```yaml
tests:
- name: author_of_an_office_document
  function: xml.element_text_matches
  parameter:
    dst: /home/user/Documents/report.docx!/docProps/core.xml
    xpath: ./dc:creator
    expected_value: Alice Example
    namespaces:
      dc: http://purl.org/dc/elements/1.1/
```

*every recent entry under Documents* → PASSED

```yaml
tests:
- name: every_recent_entry_under_documents
  function: xml.element_text_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: ./recent/entry
    expected_value: '^/home/user/Documents/'
    regex_match: true
    wildcard_mode: all
```

*counter greater than a number* → PASSED

```yaml
tests:
- name: counter_greater_than_a_number
  function: xml.element_text_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: ./counters/saved
    expected_value: 40
    comparison_type: greater
```

*document modified during the action* → PASSED. The two times are saved with `save_timestamp` before and after the action.

```yaml
tests:
- name: document_modified_during_the_action
  function: xml.element_text_matches
  parameter:
    dst: /home/user/Documents/report.docx!/docProps/core.xml
    xpath: ./dcterms:modified
    expected_value: !timestamp {after: '{{before_save}}', before: '{{after_save}}'}
    namespaces:
      dcterms: http://purl.org/dc/terms/
```

*an unquoted number never equals the text* → FAILED. The element text is `41`, but `expected_value: 41` is a number. Quote it, or set `value_type: number`.

```yaml
tests:
- name: an_unquoted_number_never_equals_the_text
  function: xml.element_text_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: ./counters/opened
    expected_value: 41
```

*a missing element fails* → FAILED

```yaml
tests:
- name: a_missing_element_fails
  function: xml.element_text_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: ./general/font
    expected_value: Sans
```

*a text that is no number is an error in ordered mode* → ERROR

```yaml
tests:
- name: a_text_that_is_no_number_is_an_error_in_ordered_
  function: xml.element_text_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: ./general/theme
    expected_value: 3
    comparison_type: greater
```

**Related:**
- `xml.xpath_result_matches`: the first element's text as a number, or whether anything matched, as a typed result

## `xml.namespace_matches`

tests if XML namespace declarations match expected namespaces

Pass when the namespaces detected in `dst` contain (or equal) `expected_namespaces`.

**Use for:** checking which XML dialect/schema version a file uses. Only the root element's own namespace is detected, under prefix `''`: ElementTree drops `xmlns:*` attributes, so other declared prefixes are never seen and expecting them fails.

asserts: value · formats: xml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`)

**Not for:**
- elements in a namespace exist → `xml.element_exists`
- the version or type of a document in an attribute → `xml.attribute_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the XML file; a glob must match exactly one path. A missing file or malformed XML is an execution error. |
| expected_namespaces | `dict[str, str]` | `None` | Required map prefix -> URI, e.g. `{'': 'http://www.w3.org/2000/svg'}`; `None` is an execution error. |
| check_mode | `str` | `'contains'` | `contains` (default; every expected prefix present with that URI) or `exact` (dicts equal). Other values are an execution error. Allowed: `contains`, `exact`. |

**Outcomes:**
- PASSED: the detected namespaces contain (`exact`: equal) `expected_namespaces`
- FAILED: the file was read and an expected prefix is missing or has another URI (`exact`, also an extra one)
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file is no well-formed XML
- ERROR: `expected_namespaces` missing; an unknown `check_mode`

**Limits:**
- Only the namespace of the root element is detected, under prefix `''`, even when the root is written with a prefix. Other `xmlns:prefix` declarations are never seen: expecting them fails.
- Prefixes and URIs compare exactly (case-sensitive).

**Use cases:**
- Which dialect or schema version a file uses: The root namespace of an SVG, an office part or a settings file written by a newer version.

**Examples:**

*an SVG file* → PASSED

```yaml
tests:
- name: an_svg_file
  function: xml.namespace_matches
  parameter:
    dst: /home/user/Pictures/logo.svg
    expected_namespaces:
      '': http://www.w3.org/2000/svg
```

*exact also passes with other declared prefixes* → PASSED. `xmlns:xlink` is declared, but only the root namespace is detected.

```yaml
tests:
- name: exact_also_passes_with_other_declared_prefixes
  function: xml.namespace_matches
  parameter:
    dst: /home/user/Pictures/logo.svg
    expected_namespaces:
      '': http://www.w3.org/2000/svg
    check_mode: exact
```

*a declared prefix is not detected* → FAILED. The file declares `xmlns:xlink`; the test fails anyway.

```yaml
tests:
- name: a_declared_prefix_is_not_detected
  function: xml.namespace_matches
  parameter:
    dst: /home/user/Pictures/logo.svg
    expected_namespaces:
      xlink: http://www.w3.org/1999/xlink
```

## `xml.values_compare`

compares two values (element text or attribute) of one XML file as numbers or timestamps (earlier/later, within a tolerance, A = B + offset)

Pass when the value selected by `xpath` compares to the one selected by `other_xpath` (+ `offset`).

**Use for:** relations inside one XML file: a last-saved value later than the first-opened one (two attributes, or two elements), two timestamps within a few seconds of each other, a counter one above another (`comparison_type: equals` with `offset: 1`). To compare one value with a constant use xml.element_text_matches or xml.attribute_matches with `comparison_type`.

asserts: compare, order · formats: xml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Ordered comparison of numbers and times (`ordered_comparison`)

**Does not support:**
- Several matches (wildcard_mode) (`wildcard_mode`): Each side must select exactly one value; several are an error.
- Regex values (!re) (`regex_tag`): Values compare as numbers or times only; test text with xml.element_text_matches.

**Not for:**
- one value against a constant → `xml.element_text_matches`
- one attribute against a constant → `xml.attribute_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the XML file; a glob must match exactly one path. A missing file or malformed XML is an error. |
| **xpath** | `str` |  | Selects the element of the first value (ElementTree `ElementPath` subset as in xml.element_text_matches). It must select exactly one element (with `attribute`: one element that has the attribute): nothing fails, several are an error. |
| **other_xpath** | `str` |  | Selects the element of the second value; same rules (may equal `xpath` to compare two attributes of one element). |
| attribute | `str \| None` | `None` | Take the first value from this attribute (`{uri}name` for namespaced attributes); `None` (default) takes the element text (`element.text`, before the first child, not stripped). |
| other_attribute | `str \| None` | `None` | The same for the second value. |
| comparison_type | `str` | `'equals'` | How the first value relates to the second: `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal` (`less` = earlier for timestamps). Other values are an error. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both are numbers, else timestamps), `number` or `timestamp`. A value that is no number or timestamp is an error. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| offset | `int \| float \| None` | `None` | Added to the second value before comparing (seconds for timestamps, may be negative): `first <comparison_type> second + offset`. |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |
| namespaces | `dict[str, str]` | `None` | Prefix -> URI map for prefixed names in both XPaths (`{ns: 'http://...'}` + `//ns:item`); `{uri}tag` also works without it. |

**Outcomes:**
- PASSED: `first <comparison_type> second + offset` holds
- FAILED: the file was read and a side selects nothing (or no element with the attribute), or the comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file is no well-formed XML; an XPath outside the ElementPath subset
- ERROR: a side selects several values
- ERROR: a value is no number or timestamp (an empty element text too), or one is a number and the other a timestamp
- ERROR: bad parameters (`comparison_type`, `value_type`, `tolerance` with an order comparison, `timestamp_epoch`, ...)

**Limits:**
- Each side is the text (`element.text`) or `attribute` of the one element its XPath selects; `other_xpath` may equal `xpath` to compare two attributes of one element.
- XPath rules as in xml.element_exists.

**Use cases:**
- A is earlier than B: A last-saved value later than the first-opened one, an end after a start (`comparison_type` `less` / `greater`).
- A within a few seconds of B: Two timestamps written by one action (`tolerance: 5`).
- A = B + n: A counter one above another (`offset: 1`), or a time a fixed interval after another (`offset` in seconds).

**Examples:**

*modified not before created* → PASSED

```yaml
tests:
- name: modified_not_before_created
  function: xml.values_compare
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //entry[@ref='item-1']
    attribute: modified
    other_xpath: //entry[@ref='item-1']
    other_attribute: created
    comparison_type: greater_equal
```

*written within five seconds* → PASSED

```yaml
tests:
- name: written_within_five_seconds
  function: xml.values_compare
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //entry[@ref='item-1']
    attribute: modified
    other_xpath: //entry[@ref='item-1']
    other_attribute: created
    tolerance: 5
```

*saved is one above opened* → PASSED

```yaml
tests:
- name: saved_is_one_above_opened
  function: xml.values_compare
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: ./counters/saved
    other_xpath: ./counters/opened
    offset: 1
```

*a side that selects nothing fails* → FAILED

```yaml
tests:
- name: a_side_that_selects_nothing_fails
  function: xml.values_compare
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: ./counters/printed
    other_xpath: ./counters/opened
```

*a side with several values is an error* → ERROR

```yaml
tests:
- name: a_side_with_several_values_is_an_error
  function: xml.values_compare
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //entry
    attribute: visits
    other_xpath: ./counters/opened
    comparison_type: less
```

## `xml.xpath_result_matches`

tests if XPath expression result matches expected value (text, number, or boolean)

Pass when `xpath` evaluated as `result_type` equals `expected_value`.

**Use for:** typed checks on the first matched element. Prefer xml.element_text_matches for text.

asserts: value, exists · formats: xml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`)

**Does not support:**
- Regex values (!re) (`regex_tag`): `expected_value` is compared as plain text, number or boolean; use xml.element_text_matches for `!re`, `regex_match` and `!timestamp`.
- Ordered comparison of numbers and times (`ordered_comparison`): Only equality; use xml.element_text_matches with `comparison_type` for greater / less.

**Not for:**
- text with regex, placeholders or several elements → `xml.element_text_matches`
- an element is absent → `xml.element_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the XML file; a glob must match exactly one path. A missing file or malformed XML is an execution error. |
| **xpath** | `str` |  | ElementTree `ElementPath` subset, evaluated on the root element: `//tag` (any depth), `/root/child` (first step must be the root tag), `child/grandchild`, predicates `[@attr='v']`, `[tag='v']`, `[@attr]`. Any `(`, `::`, `..` or `\|` (even inside a quoted value) is an execution error, so no functions such as `text()`. |
| **expected_value** | `str \| int \| float \| bool` |  | Required. Converted per `result_type`: `str()`, `float()` or `bool()`. Note `bool('false')` is True -- use unquoted YAML `true`/`false`. |
| result_type | `str` | `'text'` | `text` (default; first element's `.text`, `''` if none), `number` (`float` of that text; no match -> 0.0, non-numeric -> execution error) or `boolean` (whether anything matched). Other values are an execution error. Allowed: `text`, `number`, `boolean`. |
| namespaces | `dict[str, str]` | `None` | Prefix -> URI map for prefixed names in `xpath` (`{ns: 'http://...'}` + `//ns:item`); `{uri}tag` also works without it. |

**Outcomes:**
- PASSED: the result of `xpath` as `result_type` equals `expected_value`
- FAILED: the file was read and the result differs
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file is no well-formed XML; an XPath outside the ElementPath subset
- ERROR: `result_type: number` and the first element's text is no number; an unknown `result_type`

**Limits:**
- `text` and `number` use the first selected element only; with no match `text` is `''` and `number` is `0.0` (so `expected_value: 0` passes on a missing element).
- `boolean` is whether `xpath` selects anything. `expected_value` is converted with `bool()`: a quoted `'false'` is true, write unquoted `false`.
- XPath rules as in xml.element_exists.

**Use cases:**
- A numeric field: A counter or size compared as a number (`42` equals `42.0`).

**Examples:**

*opened counter as a number* → PASSED

```yaml
tests:
- name: opened_counter_as_a_number
  function: xml.xpath_result_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: ./counters/opened
    expected_value: 41
    result_type: number
```

*whether a recent entry exists* → PASSED

```yaml
tests:
- name: whether_a_recent_entry_exists
  function: xml.xpath_result_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //entry[@ref='item-1']
    expected_value: true
    result_type: boolean
```

*a quoted 'false' is true* → FAILED. `bool('false')` is true; the element is missing, so the result is false and the test fails.

```yaml
tests:
- name: a_quoted_false_is_true
  function: xml.xpath_result_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: //entry[@ref='item-9']
    expected_value: 'false'
    result_type: boolean
```

*a text that is no number is an error* → ERROR

```yaml
tests:
- name: a_text_that_is_no_number_is_an_error
  function: xml.xpath_result_matches
  parameter:
    dst: /home/user/.config/app/settings.xml
    xpath: ./general/language
    expected_value: 1
    result_type: number
```
