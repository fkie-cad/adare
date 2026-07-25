#!/usr/bin/env python3
"""Generate the three benign LNK stand-ins used by case study 5.5.

The paper's §5.5 ran three LNK parsers (LECmd, lnkinfo, ExifTool) against three
*malicious* samples pulled from VirusTotal (hashes in ``README.md``). Those files
are deliberately not committed, so this script synthesises benign files that
reproduce the one property the case study actually turns on:

    L1  a structurally valid Windows shell link
    L2  the same link body + 512 bytes of non-standard appended data
    L3  the same link body + 4096 bytes of non-standard appended data

That is the behaviour split reported in Table 1: ``lnkinfo`` rejects L2/L3 on
strict size constraints, while LECmd and ExifTool tolerate the appended bytes and
parse the link anyway.

Layout follows MS-SHLLINK. The link body is a ShellLinkHeader, a LinkInfo
structure with a VolumeID + LocalBasePath, the NAME_STRING / RELATIVE_PATH /
WORKING_DIR string data, and one real TrackerDataBlock. No LinkTargetIDList is
emitted — it is optional per the specification and all three parsers accept its
absence, which keeps the generator free of hand-rolled shell item IDs.

Where the appended bytes go matters, and it is the whole reason L2/L3 behave
differently from L1:

* L1 closes the link with an ExtraData **TerminalBlock** (a 32-bit size < 4).
* L2/L3 omit that terminal block, so the appended bytes land where liblnk expects
  the next ExtraData block. liblnk reads their first four bytes as a block size
  (``b"ADAR"`` little-endian = 0x52414441) and rejects the file in
  ``liblnk_data_block_read_file_io_handle`` with *"invalid data block size value
  exceeds file size"* — verbatim the "strict size constraints" the paper reports.
  ExifTool and LECmd stop after the string data instead and report the remainder
  as an unparsed overlay, so they still recover every link field.

Putting the appended bytes *behind* a terminal block would make all three parsers
succeed and the case study would assert nothing — that variant was measured and
discarded during construction.

Usage::

    python3 make_lnk_samples.py --output-dir <project>/shared/data

The playbooks reference the results as ``{{ adare_project_shared_data }}/L1.lnk``
etc., so the output directory is the *project*-level ``shared/data``, not an
experiment-local one — the same mechanism the Autopsy playbooks use for
``2020JimmyWilson.E01``.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path

# --------------------------------------------------------------------------- #
# MS-SHLLINK constants
# --------------------------------------------------------------------------- #

HEADER_SIZE = 0x0000004C
# CLSID 00021401-0000-0000-C000-000000000046 in little-endian wire order
LINK_CLSID = bytes(
    (0x01, 0x14, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00,
     0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46)
)

# LinkFlags
HAS_LINK_TARGET_ID_LIST = 0x00000001
HAS_LINK_INFO = 0x00000002
HAS_NAME = 0x00000004
HAS_RELATIVE_PATH = 0x00000008
HAS_WORKING_DIR = 0x00000010
HAS_ARGUMENTS = 0x00000020
HAS_ICON_LOCATION = 0x00000040
IS_UNICODE = 0x00000080

# FileAttributesFlags
FILE_ATTRIBUTE_ARCHIVE = 0x00000020

# ShowCommand
SW_SHOWNORMAL = 0x00000001

# LinkInfoFlags
VOLUME_ID_AND_LOCAL_BASE_PATH = 0x00000001

# DriveType
DRIVE_FIXED = 0x00000003

# ExtraData block signatures
TRACKER_DATA_BLOCK_SIGNATURE = 0xA0000003
TRACKER_DATA_BLOCK_SIZE = 0x00000060  # 96 bytes total
TRACKER_DATA_BLOCK_LENGTH = 0x00000058  # 88 bytes after BlockSize/Signature/Length/Version

# --------------------------------------------------------------------------- #
# Fixed sample content — deterministic so hashes are reproducible
# --------------------------------------------------------------------------- #

TARGET_LOCAL_PATH = r"C:\Windows\System32\notepad.exe"
TARGET_RELATIVE_PATH = r"..\..\Windows\System32\notepad.exe"
TARGET_WORKING_DIR = r"C:\Windows\System32"
TARGET_NAME = "ADARE case study 5.5 benign stand-in"
VOLUME_LABEL = "ADARE-LAB"
MACHINE_ID = "adare-lab-vm"  # NetBIOS-style name recorded in the TrackerDataBlock
DRIVE_SERIAL = 0x1A2B3C4D
TARGET_FILE_SIZE = 201_216  # bytes; surfaces as ExifTool's TargetFileSize

# A fixed point in time, so regenerating the samples is byte-for-byte stable.
FIXED_TIME = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)

# Appended non-standard payload sizes. Differing sizes are the point: the paper's
# L2 and L3 both carry appended data, and lnkinfo rejects both regardless of size.
APPENDED_SIZES = {"L2": 512, "L3": 4096}


def _filetime(moment: datetime) -> int:
    """Convert a datetime to a Windows FILETIME (100 ns ticks since 1601-01-01)."""
    epoch = datetime(1601, 1, 1, tzinfo=UTC)
    delta = moment - epoch
    return int(delta.total_seconds() * 10_000_000)


def _unicode_string_data(value: str) -> bytes:
    """Encode one StringData entry for a Unicode link (CountCharacters + UTF-16LE).

    Per MS-SHLLINK 2.4 the count is in characters and the string is *not*
    null-terminated.
    """
    encoded = value.encode("utf-16-le")
    return struct.pack("<H", len(value)) + encoded


def _build_volume_id() -> bytes:
    """VolumeID with an ANSI volume label (MS-SHLLINK 2.3.1)."""
    label = VOLUME_LABEL.encode("ascii") + b"\x00"
    volume_label_offset = 0x10  # fixed part is 16 bytes
    size = volume_label_offset + len(label)
    return (
        struct.pack("<IIII", size, DRIVE_FIXED, DRIVE_SERIAL, volume_label_offset)
        + label
    )


def _build_link_info() -> bytes:
    """LinkInfo with VolumeID + LocalBasePath, no network relative link (2.3)."""
    volume_id = _build_volume_id()
    local_base_path = TARGET_LOCAL_PATH.encode("ascii") + b"\x00"
    common_path_suffix = b"\x00"  # empty suffix, still null-terminated

    header_size = 0x1C  # no optional Unicode offsets
    volume_id_offset = header_size
    local_base_path_offset = volume_id_offset + len(volume_id)
    common_path_suffix_offset = local_base_path_offset + len(local_base_path)
    total_size = common_path_suffix_offset + len(common_path_suffix)

    return (
        struct.pack(
            "<IIIIIII",
            total_size,
            header_size,
            VOLUME_ID_AND_LOCAL_BASE_PATH,
            volume_id_offset,
            local_base_path_offset,
            0,  # CommonNetworkRelativeLinkOffset — unused
            common_path_suffix_offset,
        )
        + volume_id
        + local_base_path
        + common_path_suffix
    )


def _build_header() -> bytes:
    """ShellLinkHeader (MS-SHLLINK 2.1) — exactly 76 bytes."""
    flags = (
        HAS_LINK_INFO
        | HAS_NAME
        | HAS_RELATIVE_PATH
        | HAS_WORKING_DIR
        | IS_UNICODE
    )
    ticks = _filetime(FIXED_TIME)
    header = (
        struct.pack("<I", HEADER_SIZE)
        + LINK_CLSID
        + struct.pack("<I", flags)
        + struct.pack("<I", FILE_ATTRIBUTE_ARCHIVE)
        + struct.pack("<Q", ticks)   # CreationTime
        + struct.pack("<Q", ticks)   # AccessTime
        + struct.pack("<Q", ticks)   # WriteTime
        + struct.pack("<I", TARGET_FILE_SIZE)
        + struct.pack("<i", 0)       # IconIndex
        + struct.pack("<I", SW_SHOWNORMAL)
        + struct.pack("<H", 0)       # HotKey
        + struct.pack("<H", 0)       # Reserved1
        + struct.pack("<I", 0)       # Reserved2
        + struct.pack("<I", 0)       # Reserved3
    )
    if len(header) != HEADER_SIZE:
        raise AssertionError(f"header is {len(header)} bytes, expected {HEADER_SIZE}")
    return header


def _build_tracker_data_block() -> bytes:
    """TrackerDataBlock (MS-SHLLINK 2.5.10) — a real ExtraData block, 96 bytes.

    Included for two reasons. It makes the sample look like a shortcut Windows would
    actually write (LECmd surfaces MachineID / MachineMACAddress / TrackerCreatedOn from
    it, which is part of the verbosity the paper reports), and it means L1 exercises
    liblnk's ExtraData *block* parser successfully. The contrast with L2/L3 then isolates
    the real finding: block parsing works fine, it is specifically the malformed block
    size that the strict constraint rejects.

    The GUIDs are fixed and obviously synthetic — a lab machine name and two
    lab-prefixed identifiers, not values copied from a real host.
    """
    machine_id = MACHINE_ID.encode("ascii")
    if len(machine_id) >= 16:
        raise ValueError("MachineID must be shorter than 16 bytes to leave room for the NUL")
    machine_id = machine_id.ljust(16, b"\x00")

    # Droid and DroidBirth are each a pair of 16-byte GUIDs (volume + object identifier).
    droid = bytes(range(0x10, 0x30))
    droid_birth = bytes(range(0x30, 0x50))

    block = (
        struct.pack("<I", TRACKER_DATA_BLOCK_SIZE)
        + struct.pack("<I", TRACKER_DATA_BLOCK_SIGNATURE)
        + struct.pack("<I", TRACKER_DATA_BLOCK_LENGTH)
        + struct.pack("<I", 0)  # Version
        + machine_id
        + droid
        + droid_birth
    )
    if len(block) != TRACKER_DATA_BLOCK_SIZE:
        raise AssertionError(
            f"tracker block is {len(block)} bytes, expected {TRACKER_DATA_BLOCK_SIZE}"
        )
    return block


def _build_link_body() -> bytes:
    """Everything before the ExtraData terminal block.

    Header + LinkInfo + StringData + one real ExtraData block. L2/L3 append their
    non-standard bytes directly after this, i.e. where the *next* ExtraData block would
    start — which is what trips liblnk's size constraint.
    """
    return (
        _build_header()
        + _build_link_info()
        + _unicode_string_data(TARGET_NAME)
        + _unicode_string_data(TARGET_RELATIVE_PATH)
        + _unicode_string_data(TARGET_WORKING_DIR)
        + _build_tracker_data_block()
    )


def build_valid_lnk() -> bytes:
    """The L1 sample: a structurally valid shell link closed with a terminal block."""
    # ExtraData TerminalBlock: a BlockSize < 4 ends the block list cleanly.
    return _build_link_body() + struct.pack("<I", 0)


def build_appended_lnk(size: int) -> bytes:
    """L2/L3: the link body followed by ``size`` bytes of non-standard data.

    Deliberately emitted *without* a terminal block, so the appended bytes occupy
    the ExtraData region — see the module docstring for why that is the point.

    The filler is deterministic and obviously inert — a repeating ASCII marker —
    so anyone inspecting the sample can see it is padding and not a payload. The
    marker must not begin with bytes that form a plausible ExtraData block size,
    or liblnk would accept it; ``ADAR`` little-endian is 0x52414441, far beyond
    any real file size, which is exactly the rejection we want to trigger.
    """
    marker = b"ADARE-NONSTANDARD-APPENDED-DATA-"
    filler = (marker * (size // len(marker) + 1))[:size]
    return _build_link_body() + filler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate benign LNK stand-ins (L1/L2/L3) for case study 5.5.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("shared/data"),
        help="Directory to write L1.lnk, L2.lnk, L3.lnk into "
             "(should be the ADARE project's shared/data; default: ./shared/data)",
    )
    args = parser.parse_args(argv)

    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    samples = {"L1": build_valid_lnk()}
    for name, size in APPENDED_SIZES.items():
        samples[name] = build_appended_lnk(size)

    for name, payload in sorted(samples.items()):
        path = out_dir / f"{name}.lnk"
        path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        print(f"{name}.lnk  {len(payload):>6} bytes  sha256={digest}")

    print(f"\nWrote {len(samples)} samples to {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
