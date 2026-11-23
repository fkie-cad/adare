# Image (`image.*`)

<!-- Generated; do not edit by hand. -->

Metadata stored in image files: PNG text chunks (`tEXt`, `zTXt`, `iTXt`), EXIF tags (IFD0, Exif IFD, GPS IFD of JPEG, PNG `eXIf`, TIFF, WebP) and pixel dimensions. PNG chunks are read by a strict chunk walker that verifies every CRC and keeps duplicate keywords; EXIF values are compared by a fixed text form. Absence is a count function with `expected_count: 0`; a missing or corrupt file is an error, never a pass.

## `image.dimensions_match`

tests if an image has the expected width and/or height in pixels

Pass when the image `dst` is `width` x `height` pixels (only the given ones are checked).

**Use for:** checking an exported, resized or cropped image, or a generated thumbnail.

asserts: value · formats: image · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`)

**Not for:**
- the file size in bytes → `standard.file_size`
- metadata of the image → `image.exif_value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the image (any format Pillow reads); a glob must match exactly one path. A missing file or a file that is not an image is an error. |
| width | `int` | `None` | Expected width in pixels (positive integer). |
| height | `int` | `None` | Expected height in pixels (positive integer). Give at least one of the two; neither, or a non-positive / non-integer value, is an error. |

**Outcomes:**
- PASSED: the given dimensions match
- FAILED: the image was read and a dimension differs (the details show the actual size)
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: not an image Pillow can read
- ERROR: neither `width` nor `height` given, or one that is not a positive integer

**Limits:**
- Only the given dimensions are checked; the size is read without decoding the pixel data.

**Use cases:**
- A screenshot or export was written: The saved image has the size of the screen or the chosen export size.
- A thumbnail was created: Cached thumbnails have a fixed size.

**Examples:**

*thumbnail size* → PASSED

```yaml
tests:
- name: thumbnail_size
  function: image.dimensions_match
  parameter:
    dst: /home/user/.cache/thumbnails/normal/a.png
    width: 128
    height: 128
```

*width only* → PASSED

```yaml
tests:
- name: width_only
  function: image.dimensions_match
  parameter:
    dst: /home/user/Pictures/photo.jpg
    width: 64
```

*another size fails* → FAILED

```yaml
tests:
- name: another_size_fails
  function: image.dimensions_match
  parameter:
    dst: /home/user/Pictures/photo.jpg
    width: 64
    height: 64
```

*an image inside an archive* → PASSED

```yaml
tests:
- name: an_image_inside_an_archive
  function: image.dimensions_match
  parameter:
    dst: /home/user/Documents/report.zip!/media/image1.png
    width: 64
    height: 32
```

*no dimension given is an error* → ERROR

```yaml
tests:
- name: no_dimension_given_is_an_error
  function: image.dimensions_match
  parameter:
    dst: /home/user/Pictures/photo.jpg
```

## `image.exif_value_count`

tests the number of occurrences of an EXIF tag (optionally with a matching value)

Pass when the number of occurrences of EXIF tag `tag` (whose value matches `expected_value`, if given) satisfies `comparison_type` against `expected_count`.

**Use for:** absence: `expected_count: 0` asserts the tag was not written (or stripped, e.g. location data removed on export).

asserts: count, absent · formats: image · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Counts with a comparison (`count_comparison`), Negative tests (absence) (`negative`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`)

**Not for:**
- the value of a tag → `image.exif_value_matches`
- text chunks of a PNG → `image.png_text_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the image; a glob must match exactly one path. A missing file, a file that is not an image or has corrupt EXIF data is an error. |
| **tag** | `str \| int` |  | Tag name (`Make`, `GPSLatitude`) or number (`0x010f`); names are looked up in their IFD (IFD0 + Exif IFD, or GPS IFD), numbers in all three, and each IFD that has the tag counts once. An unknown name is an error. |
| **expected_count** | `int` |  | Required non-negative integer to compare against; anything else is an error. |
| expected_value | `str \| int \| float \| bool \| None` | `None` | Count only occurrences whose value text equals/matches this (same formatting as image.exif_value_matches); `None` (default) counts every occurrence. |
| regex_match | `bool` | `False` | Search `expected_value` as a Python regex (`re.search`, unanchored). |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |

**Outcomes:**
- PASSED: the number of occurrences of `tag` (whose value matches `expected_value`, if given) satisfies `comparison_type`
- FAILED: the image was read and the count comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: not an image, or corrupt EXIF data
- ERROR: an unknown tag name or a tag number out of range
- ERROR: a negative or non-integer `expected_count`; an unknown `comparison_type`; an invalid regex or unknown placeholder

**Limits:**
- Each IFD that has the tag counts once; a number is looked up in all three IFDs.
- Values compare by the text form of image.exif_value_matches; there is no ordered comparison.

**Use cases:**
- Photo metadata was stripped: `expected_count: 0` on a GPS or camera tag after an export that removes metadata.

**Examples:**

*no location in the photo* → PASSED

```yaml
tests:
- name: no_location_in_the_photo
  function: image.exif_value_count
  parameter:
    dst: /home/user/Pictures/photo.jpg
    tag: GPSLatitude
    expected_count: 0
```

*the camera make once* → PASSED

```yaml
tests:
- name: the_camera_make_once
  function: image.exif_value_count
  parameter:
    dst: /home/user/Pictures/photo.jpg
    tag: Make
    expected_value: ExampleCam
    expected_count: 1
```

*a make still present fails a strip check* → FAILED

```yaml
tests:
- name: a_make_still_present_fails_a_strip_check
  function: image.exif_value_count
  parameter:
    dst: /home/user/Pictures/photo.jpg
    tag: Make
    expected_count: 0
```

*an image without EXIF has no tags* → PASSED

```yaml
tests:
- name: an_image_without_exif_has_no_tags
  function: image.exif_value_count
  parameter:
    dst: /home/user/Pictures/photo.png
    tag: Make
    expected_count: 0
```

*a file that is not an image is an error* → ERROR

```yaml
tests:
- name: a_file_that_is_not_an_image_is_an_error
  function: image.exif_value_count
  parameter:
    dst: /home/user/Pictures/photo.jpg
    tag: GPSLatitude
    expected_count: 0
```

## `image.exif_value_matches`

tests if an EXIF tag (IFD0, Exif or GPS IFD) equals or matches an expected value

Pass when EXIF tag `tag` of the image `dst` equals (or matches) `expected_value`.

With `comparison_type` (`greater`, `less`, ...), `tolerance` or the time parameters the value is compared as a number or timestamp (EXIF dates need `time_format: "%Y:%m:%d %H:%M:%S"`).

**Use for:** camera, time and location metadata written into photos (JPEG, PNG eXIf, TIFF, WebP). A tag present in several IFDs passes if one occurrence matches (`wildcard_mode: all`: every occurrence must match); a missing tag fails. For "absent" use image.exif_value_count with `expected_count: 0`.

asserts: exists, value, order · formats: image · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Ordered comparison of numbers and times (`ordered_comparison`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Several matches (wildcard_mode) (`wildcard_mode`)

**Not for:**
- a tag is absent or was stripped → `image.exif_value_count`
- text chunks of a PNG → `image.png_text_matches`
- the width or height of an image → `image.dimensions_match`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the image; a glob must match exactly one path. A missing file, a file that is not an image or has corrupt EXIF data is an error. |
| **tag** | `str \| int` |  | Tag name as in Pillow's tables (`Make`, `DateTimeOriginal`, `GPSLatitude`) or a number (`0x9003`, `36867`). Main-table names are looked up in IFD0 and the Exif IFD, GPS names in the GPS IFD, numbers in all three. An unknown name is an error. |
| **expected_value** | `str \| int \| float \| bool` |  | Compared with the value's text form: text as stored (trailing NULs removed); integers in decimal; rationals and floats as decimals (`72`, `2.8`, `0.004`; `nan` for x/0); sequences joined with `", "` (GPS `51, 30, 12.5`); bytes as text when printable UTF-8, else lowercase hex; the user comment without its 8-byte charset prefix; the UTF-16 title/comment tags (0x9C9B-0x9C9F) decoded. A YAML number is formatted the same way (write a sequence as text, `51, 30, 12.5`); a `!re`/`!timestamp` tag or `{{placeholder}}` is matched by type. |
| regex_match | `bool` | `False` | Search `expected_value` as a Python regex (`re.search`, unanchored). An invalid regex is an error. |
| wildcard_mode | `str` | `'any'` | With the tag in several IFDs, `any` (default): one occurrence must match; `all`: every one must match. Other values are an error. Allowed: `any`, `all`. |
| comparison_type | `str` | `'equals'` | `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal`. Anything but `equals`, or any parameter below, compares the value with `expected_value` as a number or point in time (ordered mode; `less` = earlier); `!re` / `regex_match` are then errors, a lone `{{ name }}` is the saved variable; a value that is no number or timestamp is an error. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both sides are numbers, else timestamps), `number` or `timestamp`. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |

**Outcomes:**
- PASSED: an occurrence of `tag` matches `expected_value` (`wildcard_mode: all`: every occurrence)
- FAILED: the image was read and `tag` is missing, or no occurrence matches (the details list the values)
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: not an image, or corrupt EXIF data
- ERROR: an unknown tag name or a tag number out of range
- ERROR: an invalid regex or unknown placeholder; a `wildcard_mode` other than `any` / `all`
- ERROR: in ordered mode, a value or `expected_value` that is no number or timestamp, or a `!re` or `regex_match` with it, text around a `{{ name }}` or a saved variable that is no number or time

**Limits:**
- Values compare by text form: text as stored without trailing NULs; integers in decimal; rationals and floats as decimals (`72`, `2.8`, `0.004`; `nan` for x/0); sequences joined with `", "` (GPS `51, 30, 12.5`); bytes as text when printable UTF-8, else lowercase hex.
- The user comment (0x9286) is compared without its 8-byte charset prefix; the UTF-16 title/comment/author/keywords/subject tags (0x9C9B-0x9C9F) decoded.
- A YAML number in `expected_value` is formatted the same way; write a sequence as text (`51, 30, 12.5`).
- Main-table names are looked up in IFD0 and the Exif IFD, GPS names in the GPS IFD, numbers in all three.
- EXIF dates (`2026:01:01 10:00:00`) need `time_format: '%Y:%m:%d %H:%M:%S'` in ordered mode (without it they are an error), and `format: '%Y:%m:%d %H:%M:%S'` in a `!timestamp` tag: without it only the time of day is read and the date becomes today, so the test fails.
- EXIF dates have no zone; ordered mode reads them as UTC unless `utc_offset` is set.

**Use cases:**
- Camera and software metadata: Make, model or software written into a photo by a device or an editor.
- Capture time: `DateTimeOriginal` after a point in time, with `comparison_type` and `time_format`.
- Location data: `GPSLatitude` / `GPSLongitude` as degrees, minutes, seconds (`51, 30, 12.5`).

**Examples:**

*camera make* → PASSED

```yaml
tests:
- name: camera_make
  function: image.exif_value_matches
  parameter:
    dst: /home/user/Pictures/photo.jpg
    tag: Make
    expected_value: ExampleCam
```

*a tag by number* → PASSED. 0x0110 is `Model`.

```yaml
tests:
- name: a_tag_by_number
  function: image.exif_value_matches
  parameter:
    dst: /home/user/Pictures/photo.jpg
    tag: '0x0110'
    expected_value: Model 7
```

*a rational as a number* → PASSED. The resolution 72/1 reads as `72`; a YAML number is formatted the same way.

```yaml
tests:
- name: a_rational_as_a_number
  function: image.exif_value_matches
  parameter:
    dst: /home/user/Pictures/photo.jpg
    tag: XResolution
    expected_value: 72
```

*captured after a point in time* → PASSED

```yaml
tests:
- name: captured_after_a_point_in_time
  function: image.exif_value_matches
  parameter:
    dst: /home/user/Pictures/photo.jpg
    tag: DateTimeOriginal
    expected_value: '2025:12:31 00:00:00'
    comparison_type: greater
    time_format: '%Y:%m:%d %H:%M:%S'
```

*an EXIF date without time_format is an error in ordered mode* → ERROR

```yaml
tests:
- name: an_exif_date_without_time_format_is_an_error_in_
  function: image.exif_value_matches
  parameter:
    dst: /home/user/Pictures/photo.jpg
    tag: DateTimeOriginal
    expected_value: '2025:12:31 00:00:00'
    comparison_type: greater
```

*software by pattern* → PASSED

```yaml
tests:
- name: software_by_pattern
  function: image.exif_value_matches
  parameter:
    dst: /home/user/Pictures/photo.jpg
    tag: Software
    expected_value: '^Editor '
    regex_match: true
    wildcard_mode: all
```

*a missing tag fails* → FAILED. To assert absence use image.exif_value_count with `expected_count` 0, which passes.

```yaml
tests:
- name: a_missing_tag_fails
  function: image.exif_value_matches
  parameter:
    dst: /home/user/Pictures/photo.jpg
    tag: Artist
    expected_value: analyst
```

*an unknown tag name is an error* → ERROR

```yaml
tests:
- name: an_unknown_tag_name_is_an_error
  function: image.exif_value_matches
  parameter:
    dst: /home/user/Pictures/photo.jpg
    tag: CameraMaker
    expected_value: ExampleCam
```

*capture time near a saved timestamp* → PASSED

```yaml
tests:
- name: capture_time_near_a_saved_timestamp
  function: image.exif_value_matches
  parameter:
    dst: /home/user/Pictures/photo.jpg
    tag: DateTimeOriginal
    expected_value: !timestamp {timestamp: '{{photo_taken}}', tolerance: 60, format: '%Y:%m:%d %H:%M:%S'}
```

## `image.png_text_count`

tests the number of PNG text chunks with a keyword (optionally with a matching text)

Pass when the number of text chunks with `keyword` (whose text matches `expected_value`, if given) satisfies `comparison_type` against `expected_count`.

**Use for:** duplicate keywords and absence: `expected_count: 0` asserts no such chunk (or none with that text).

asserts: count, absent · formats: image · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Counts with a comparison (`count_comparison`), Negative tests (absence) (`negative`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`)

**Not for:**
- the text of a chunk → `image.png_text_matches`
- EXIF tags of a photo → `image.exif_value_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the PNG file; a glob must match exactly one path. A missing file, a bad signature, a truncated chunk, any chunk CRC mismatch, a malformed or undecompressable text chunk, or a missing IEND is an error. |
| **keyword** | `str` |  | Chunk keyword, compared exactly; tEXt, zTXt and iTXt chunks are counted together, also those after the image data. |
| **expected_count** | `int` |  | Required non-negative integer to compare against; anything else is an error. |
| expected_value | `str \| int \| float \| bool \| None` | `None` | Count only chunks whose text equals/matches this (same rules as image.png_text_matches); `None` (default) counts every chunk with `keyword`. |
| regex_match | `bool` | `False` | Search `expected_value` as a Python regex (`re.search`, unanchored). |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |

**Outcomes:**
- PASSED: the number of chunks with `keyword` (whose text matches `expected_value`, if given) satisfies `comparison_type`
- FAILED: the PNG was read and the count comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one; the file is over the read cap
- ERROR: not a well-formed PNG (signature, truncated chunk, CRC mismatch, malformed text chunk, no `IEND`)
- ERROR: a negative or non-integer `expected_count`; an unknown `comparison_type`; an invalid regex or unknown placeholder

**Limits:**
- `tEXt`, `zTXt` and `iTXt` chunks with `keyword` are counted together, also those after the image data.

**Use cases:**
- Metadata was stripped: `expected_count: 0` on a keyword after an export that removes metadata.
- A keyword is written once: No duplicate text chunks after a re-save.

**Examples:**

*no source chunk* → PASSED

```yaml
tests:
- name: no_source_chunk
  function: image.png_text_count
  parameter:
    dst: /home/user/Pictures/photo.png
    keyword: Source
    expected_count: 0
```

*one software chunk of this version* → PASSED

```yaml
tests:
- name: one_software_chunk_of_this_version
  function: image.png_text_count
  parameter:
    dst: /home/user/Pictures/photo.png
    keyword: Software
    expected_value: '^app 1\.'
    regex_match: true
    expected_count: 1
```

*a comment still present fails a strip check* → FAILED

```yaml
tests:
- name: a_comment_still_present_fails_a_strip_check
  function: image.png_text_count
  parameter:
    dst: /home/user/Pictures/photo.png
    keyword: Comment
    expected_count: 0
```

*a missing file is an error, not an absence* → ERROR

```yaml
tests:
- name: a_missing_file_is_an_error_not_an_absence
  function: image.png_text_count
  parameter:
    dst: /home/user/Pictures/other.png
    keyword: Comment
    expected_count: 0
```

## `image.png_text_matches`

tests if a PNG text chunk (tEXt/zTXt/iTXt) with a keyword exists or matches an expected value

Pass when the PNG `dst` has a text chunk with `keyword` (whose text matches `expected_value`).

**Use for:** metadata an application embeds in saved images (software, source, comment). With several chunks for `keyword`, one match is enough (`wildcard_mode: all`: every chunk must match). For "absent" use image.png_text_count with `expected_count: 0`.

asserts: exists, value · formats: image · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Several matches (wildcard_mode) (`wildcard_mode`)

**Not for:**
- a keyword is absent, or how many chunks have it → `image.png_text_count`
- EXIF tags of a photo → `image.exif_value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the PNG file; a glob must match exactly one path. A missing file, a bad signature, a truncated chunk, any chunk CRC mismatch, a malformed or undecompressable text chunk, or a missing IEND is an error. |
| **keyword** | `str` |  | Chunk keyword, compared exactly (case-sensitive). All chunks up to IEND are read, also those after the image data. tEXt is Latin-1, zTXt zlib + Latin-1, iTXt UTF-8 (compressed or not; language tag and translated keyword are ignored). |
| expected_value | `str \| int \| float \| bool \| None` | `None` | `None` (default): the keyword exists. Otherwise compared with the text; a YAML number/boolean is compared as its text, a `!re`/`!timestamp` tag or `{{placeholder}}` is matched by type. |
| regex_match | `bool` | `False` | Search `expected_value` as a Python regex (`re.search`, unanchored). An invalid regex is an error. |
| wildcard_mode | `str` | `'any'` | With several chunks for `keyword`, `any` (default): one must match; `all`: every one must match. Ignored without `expected_value`. Other values are an error. Allowed: `any`, `all`. |

**Outcomes:**
- PASSED: a text chunk with `keyword` exists and (with `expected_value`) its text matches; with `wildcard_mode: all` every such chunk's text
- FAILED: the PNG was read and has no chunk with `keyword` (the details list the keywords found), or no such chunk's text matches
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one; the file is over the read cap
- ERROR: not a well-formed PNG (signature, truncated chunk, CRC mismatch in any chunk, malformed or undecompressable text chunk, no `IEND`)
- ERROR: an invalid regex or unknown placeholder; a `wildcard_mode` other than `any` / `all`

**Limits:**
- Keywords compare exactly (case-sensitive); all chunks up to `IEND` are read, also those after the image data.
- `tEXt` is Latin-1, `zTXt` zlib + Latin-1, `iTXt` UTF-8 (compressed or not; its language tag and translated keyword are ignored).
- A YAML number or boolean in `expected_value` is compared as its text (`3`, `true`).
- A decompressed text chunk over 16 MiB is an error.

**Use cases:**
- Metadata an application embeds in saved images: Software, source, comment or creation time written on export.

**Examples:**

*comment written on export* → PASSED

```yaml
tests:
- name: comment_written_on_export
  function: image.png_text_matches
  parameter:
    dst: /home/user/Pictures/photo.png
    keyword: Comment
    expected_value: exported by app
```

*a keyword exists* → PASSED

```yaml
tests:
- name: a_keyword_exists
  function: image.png_text_matches
  parameter:
    dst: /home/user/Pictures/photo.png
    keyword: Software
```

*every comment by pattern* → PASSED

```yaml
tests:
- name: every_comment_by_pattern
  function: image.png_text_matches
  parameter:
    dst: /home/user/Pictures/photo.png
    keyword: Comment
    expected_value: 'by app$'
    regex_match: true
    wildcard_mode: all
```

*a missing keyword fails* → FAILED. To assert absence use image.png_text_count with `expected_count` 0, which passes.

```yaml
tests:
- name: a_missing_keyword_fails
  function: image.png_text_matches
  parameter:
    dst: /home/user/Pictures/photo.png
    keyword: Source
```

*keywords are case-sensitive* → FAILED

```yaml
tests:
- name: keywords_are_case_sensitive
  function: image.png_text_matches
  parameter:
    dst: /home/user/Pictures/photo.png
    keyword: comment
```

*a file that is not a PNG is an error* → ERROR

```yaml
tests:
- name: a_file_that_is_not_a_png_is_an_error
  function: image.png_text_matches
  parameter:
    dst: /home/user/Pictures/photo.png
    keyword: Comment
```

*creation time between two saved timestamps* → PASSED

```yaml
tests:
- name: creation_time_between_two_saved_timestamps
  function: image.png_text_matches
  parameter:
    dst: /home/user/Pictures/photo.png
    keyword: Creation Time
    expected_value: !timestamp {after: '{{before_export}}', before: '{{after_export}}'}
```
