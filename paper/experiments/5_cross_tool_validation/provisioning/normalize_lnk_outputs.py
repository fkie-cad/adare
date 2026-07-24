#!/usr/bin/env python3
"""Normalize the three LNK parsers' outputs into the paper's Table 1.

Section 5.5 states that "output-format harmonization currently remains a manual step
and should be automated in the future", and section 7 repeats it as an open item. This
script closes that gap: it reads the artifacts the three playbooks pull to the host and
emits Table 1 — per-sample parse success plus a field-count verbosity measure — as
Markdown and CSV.

Input is one or more directories, searched recursively. Each tool is recognised by the
artifact filenames its playbook produces, so the ADARE run-directory layout does not
have to be known in advance::

    lecmd_L<n>.json          + rc_L<n>.txt   -> LECmd     (Windows 11)
    lnkinfo_L<n>.txt         + rc_L<n>.txt   -> lnkinfo    (Ubuntu 24.04)
    exiftool_L<n>.flat.json  + rc_L<n>.txt   -> ExifTool   (Ubuntu 24.04)

Usage::

    python3 normalize_lnk_outputs.py --artifacts <run_dir> [<run_dir> ...]
    python3 normalize_lnk_outputs.py --artifacts <runs_root> --csv table1.csv

Parse success is decided from evidence, not from the exit code alone: a tool counts as
having parsed a sample only if it both exited zero and recovered the link's local path.
That is deliberate — liblnk 20240423 exits zero on L2/L3 while recovering nothing, and a
naive exit-code reading would score it ✓ and silently contradict the paper.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SAMPLES = ("L1", "L2", "L3")

# The expected target of every generated sample; used as the "did it actually parse?"
# probe. Kept in sync with make_lnk_samples.py:TARGET_LOCAL_PATH.
EXPECTED_LOCAL_PATH = r"C:\Windows\System32\notepad.exe"

# ExifTool reports host-filesystem metadata for every file it touches. Counting those
# against LNK-specific richness would flatter it, so they are excluded from the
# verbosity measure. Everything else ExifTool emits is link metadata.
EXIFTOOL_NON_LINK_KEYS = frozenset({
    "SourceFile", "ExifToolVersion", "FileName", "Directory", "FileSize",
    "FileModifyDate", "FileAccessDate", "FileInodeChangeDate", "FilePermissions",
    "FileType", "FileTypeExtension", "MIMEType", "Warning",
})

# LECmd's CSV/JSON record carries the source file's own filesystem timestamps too.
LECMD_NON_LINK_KEYS = frozenset({
    "SourceFile", "SourceCreated", "SourceModified", "SourceAccessed",
})

# lnkinfo prints "<label><tabs>: <value>" lines; the banner and section headers do not.
LNKINFO_FIELD_RE = re.compile(r"^\s+(?P<label>\S[^:]*?)\s*:\s*(?P<value>.+)$")


@dataclass
class SampleResult:
    """One (tool, sample) cell of Table 1."""
    exit_code: int | None = None
    parsed: bool = False
    field_count: int = 0
    local_path: str | None = None
    note: str = ""

    @property
    def mark(self) -> str:
        return "✓" if self.parsed else "✗"


@dataclass
class ToolResult:
    name: str
    host_os: str
    samples: dict[str, SampleResult] = field(default_factory=dict)
    version: str | None = None

    @property
    def verbosity_count(self) -> int:
        """Field count on the richest successfully parsed sample.

        Using the maximum rather than L1 alone keeps the measure defined even if a tool
        happens to fail the sample we would otherwise have used as the reference.
        """
        counts = [s.field_count for s in self.samples.values() if s.parsed]
        return max(counts) if counts else 0


# --------------------------------------------------------------------------- #
# Artifact discovery
# --------------------------------------------------------------------------- #

def _read_text(path: Path) -> str:
    """Read a text artifact, tolerating the BOM PowerShell likes to add."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-16")


def _read_exit_code(directory: Path, sample: str) -> int | None:
    rc_path = directory / f"rc_{sample}.txt"
    if not rc_path.is_file():
        return None
    raw = _read_text(rc_path).strip()
    try:
        return int(raw)
    except ValueError:
        return None


def _find(root: Path, pattern: str) -> list[Path]:
    return sorted(p for p in root.rglob(pattern) if p.is_file())


# --------------------------------------------------------------------------- #
# Per-tool parsers
# --------------------------------------------------------------------------- #

def parse_exiftool(path: Path, sample: str) -> SampleResult:
    result = SampleResult(exit_code=_read_exit_code(path.parent, sample))
    try:
        data = json.loads(_read_text(path))
    except (json.JSONDecodeError, OSError) as exc:
        result.note = f"unreadable output: {exc}"
        return result
    # Tolerate both the flattened object and a raw `-json` array.
    if isinstance(data, list):
        data = data[0] if data else {}
    result.local_path = data.get("LocalBasePath")
    result.field_count = len(set(data) - EXIFTOOL_NON_LINK_KEYS)
    result.parsed = result.exit_code == 0 and result.local_path == EXPECTED_LOCAL_PATH
    if "Warning" in data:
        result.note = str(data["Warning"])
    return result


def parse_lecmd(path: Path, sample: str) -> SampleResult:
    result = SampleResult(exit_code=_read_exit_code(path.parent, sample))
    try:
        raw = _read_text(path).strip()
    except OSError as exc:
        result.note = f"unreadable output: {exc}"
        return result
    if not raw:
        result.note = "empty output"
        return result

    record: dict | None = None
    # LECmd is expected to emit newline-delimited JSON (like PECmd). Fall back to a
    # single document or an array so a change in its export format degrades to a note
    # rather than a crash.
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            record = None
            break
        if isinstance(candidate, dict):
            record = candidate
            break
    if record is None:
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            result.note = f"not JSON/JSONL: {exc}"
            return result
        if isinstance(document, list):
            document = document[0] if document else {}
        if not isinstance(document, dict):
            result.note = "unexpected JSON shape"
            return result
        record = document
        result.note = "output was a JSON document, not JSONL"

    result.local_path = record.get("LocalPath")
    populated = {k for k, v in record.items() if v not in (None, "", [])}
    result.field_count = len(populated - LECMD_NON_LINK_KEYS)
    result.parsed = result.exit_code == 0 and result.local_path == EXPECTED_LOCAL_PATH
    return result


def parse_lnkinfo(path: Path, sample: str) -> SampleResult:
    result = SampleResult(exit_code=_read_exit_code(path.parent, sample))
    try:
        text = _read_text(path)
    except OSError as exc:
        result.note = f"unreadable output: {exc}"
        return result

    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = LNKINFO_FIELD_RE.match(line)
        if match:
            fields[match.group("label").strip()] = match.group("value").strip()
    result.field_count = len(fields)
    # lnkinfo escapes backslashes in some builds (20240423 prints C:\\Windows\\...).
    local = fields.get("Local path")
    if local:
        result.local_path = local.replace("\\\\", "\\")
    result.parsed = result.exit_code == 0 and result.local_path == EXPECTED_LOCAL_PATH

    err_path = path.parent / f"{path.stem}.err.txt"
    if not result.parsed and err_path.is_file():
        stderr = _read_text(err_path).strip().splitlines()
        reason = next((ln.strip() for ln in stderr if "size" in ln.lower()), "")
        result.note = reason or (stderr[0].strip() if stderr else "")
    if result.parsed and "Is corrupted" in text:
        result.note = "flagged corrupted but recovered (liblnk >= 20240423)"
    return result


TOOL_SPECS = (
    # (display name, host OS, glob, parser, version-file glob)
    ("LECmd", "Windows 11", "lecmd_{sample}.json", parse_lecmd),
    ("ExifTool", "Ubuntu 24.04", "exiftool_{sample}.flat.json", parse_exiftool),
    ("lnkinfo", "Ubuntu 24.04", "lnkinfo_{sample}.txt", parse_lnkinfo),
)


def collect(roots: list[Path]) -> list[ToolResult]:
    tools: list[ToolResult] = []
    for name, host_os, template, parser in TOOL_SPECS:
        tool = ToolResult(name=name, host_os=host_os)
        for sample in SAMPLES:
            matches: list[Path] = []
            for root in roots:
                matches.extend(_find(root, template.format(sample=sample)))
            if not matches:
                continue
            if len(matches) > 1:
                print(
                    f"note: {len(matches)} artifacts matched "
                    f"{template.format(sample=sample)}; using the newest",
                    file=sys.stderr,
                )
                matches.sort(key=lambda p: p.stat().st_mtime)
            chosen = matches[-1]
            tool.samples[sample] = parser(chosen, sample)
            if tool.version is None:
                version_file = chosen.parent / "tool_version.txt"
                if version_file.is_file():
                    tool.version = _read_text(version_file).strip().splitlines()[0].strip()
        if tool.samples:
            tools.append(tool)
    return tools


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def verbosity_labels(tools: list[ToolResult]) -> dict[str, str]:
    """Rank tools by field count and label them High / Medium / Low.

    With three tools this reproduces Table 1's ordinal column directly. With any other
    number the extremes are still labelled and the middle band is 'Medium', which keeps
    the output meaningful if a fourth parser is added later.
    """
    ranked = sorted(tools, key=lambda t: t.verbosity_count, reverse=True)
    labels: dict[str, str] = {}
    for position, tool in enumerate(ranked):
        if tool.verbosity_count == 0:
            labels[tool.name] = "n/a"
        elif position == 0:
            labels[tool.name] = "High"
        elif position == len(ranked) - 1:
            labels[tool.name] = "Low"
        else:
            labels[tool.name] = "Medium"
    return labels


def render_markdown(tools: list[ToolResult], labels: dict[str, str]) -> str:
    lines = [
        "Table 1: Comparison of LNK parser behaviour on three samples.",
        "L1 is structurally valid; L2 and L3 contain non-standard appended data.",
        "(✓ = success, ✗ = failure). Verbosity is the count of populated link-metadata",
        "fields on the richest successfully parsed sample.",
        "",
        "| Tool | Host OS | L1 | L2 | L3 | Verbosity | Fields | Tool version |",
        "|---|---|:--:|:--:|:--:|---|--:|---|",
    ]
    for tool in tools:
        marks = [
            tool.samples[s].mark if s in tool.samples else "–"
            for s in SAMPLES
        ]
        lines.append(
            f"| {tool.name} | {tool.host_os} | {marks[0]} | {marks[1]} | {marks[2]} "
            f"| {labels.get(tool.name, 'n/a')} | {tool.verbosity_count} "
            f"| {tool.version or '—'} |"
        )

    notes = [
        (tool.name, sample, tool.samples[sample].note)
        for tool in tools
        for sample in SAMPLES
        if sample in tool.samples and tool.samples[sample].note
    ]
    if notes:
        lines.extend(["", "Notes:"])
        lines.extend(f"- **{name} / {sample}**: {note}" for name, sample, note in notes)
    return "\n".join(lines) + "\n"


def write_csv(tools: list[ToolResult], labels: dict[str, str], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "tool", "host_os", "sample", "exit_code", "parsed",
            "link_field_count", "verbosity", "local_path", "tool_version", "note",
        ])
        for tool in tools:
            for sample in SAMPLES:
                result = tool.samples.get(sample)
                if result is None:
                    continue
                writer.writerow([
                    tool.name, tool.host_os, sample,
                    "" if result.exit_code is None else result.exit_code,
                    "yes" if result.parsed else "no",
                    result.field_count, labels.get(tool.name, "n/a"),
                    result.local_path or "", tool.version or "", result.note,
                ])


PAPER_TABLE1 = {
    "LECmd": {"L1": True, "L2": True, "L3": True, "verbosity": "High"},
    "ExifTool": {"L1": True, "L2": True, "L3": True, "verbosity": "Low"},
    "lnkinfo": {"L1": True, "L2": False, "L3": False, "verbosity": "Medium"},
}


def compare_with_paper(tools: list[ToolResult], labels: dict[str, str]) -> list[str]:
    """Report where the measured table diverges from the paper's Table 1."""
    divergences: list[str] = []
    for tool in tools:
        expected = PAPER_TABLE1.get(tool.name)
        if expected is None:
            continue
        for sample in SAMPLES:
            result = tool.samples.get(sample)
            if result is None:
                divergences.append(f"{tool.name}/{sample}: no artifact found")
                continue
            if result.parsed != expected[sample]:
                want = "✓" if expected[sample] else "✗"
                divergences.append(
                    f"{tool.name}/{sample}: measured {result.mark}, paper says {want}"
                )
        measured_verbosity = labels.get(tool.name, "n/a")
        if measured_verbosity != expected["verbosity"]:
            divergences.append(
                f"{tool.name}: verbosity measured {measured_verbosity}, "
                f"paper says {expected['verbosity']}"
            )
    return divergences


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize LNK parser outputs into the paper's Table 1.",
    )
    parser.add_argument(
        "--artifacts", type=Path, nargs="+", required=True,
        help="One or more directories holding pulled artifacts (searched recursively)",
    )
    parser.add_argument("--csv", type=Path, help="Also write the per-sample rows to this CSV")
    parser.add_argument(
        "--markdown", type=Path, help="Write the Markdown table here instead of stdout",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit non-zero if the measured table diverges from the paper's Table 1",
    )
    args = parser.parse_args(argv)

    missing = [str(p) for p in args.artifacts if not p.is_dir()]
    if missing:
        print(f"error: not a directory: {', '.join(missing)}", file=sys.stderr)
        return 2

    tools = collect(args.artifacts)
    if not tools:
        print(
            "error: no recognised parser artifacts found. Expected files named "
            "lecmd_L*.json, lnkinfo_L*.txt or exiftool_L*.flat.json.",
            file=sys.stderr,
        )
        return 1

    labels = verbosity_labels(tools)
    table = render_markdown(tools, labels)

    if args.markdown:
        args.markdown.write_text(table, encoding="utf-8")
        print(f"wrote {args.markdown}")
    else:
        print(table)

    if args.csv:
        write_csv(tools, labels, args.csv)
        print(f"wrote {args.csv}")

    divergences = compare_with_paper(tools, labels)
    if divergences:
        print("\nDivergence from the paper's Table 1:", file=sys.stderr)
        for item in divergences:
            print(f"  - {item}", file=sys.stderr)
        if args.strict:
            return 1
    else:
        print("\nMeasured table matches the paper's Table 1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
