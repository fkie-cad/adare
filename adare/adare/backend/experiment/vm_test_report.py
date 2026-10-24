"""Readable failure details for `adare vm test`.

A failed check's reason can carry raw guest stderr -- for Windows guests a
PowerShell CLIXML blob. It is decoded here and printed below the stage tree after
the run, since a multiline reason in the live tree would explode it mid-run.
"""

import re
import xml.etree.ElementTree as ET


def _decode_clixml_xml(xml_block: str) -> str:
    """Decode one PowerShell CLIXML ``<Objs>...</Objs>`` block to readable text.

    Drops ``<Obj S="progress">`` nodes (the "Preparing modules for first use"
    progress-bar noise) and joins the remaining text. Falls back to tag-stripping
    if the block is not well-formed XML.
    """
    try:
        root = ET.fromstring(xml_block)
    except ET.ParseError:
        # Malformed CLIXML: strip tags and return the raw text.
        return re.sub(r'<[^>]+>', ' ', xml_block)

    for progress in root.findall('.//Obj[@S="progress"]'):
        # Remove the progress node in place from its parent.
        parent = None
        for candidate in root.iter():
            if progress in list(candidate):
                parent = candidate
                break
        if parent is not None:
            parent.remove(progress)

    return ' '.join(t for t in root.itertext() if t)


def decode_guest_stderr(stderr: str) -> str:
    """Clean guest stderr into readable lines, decoding any CLIXML block.

    PowerShell remoting wraps stderr in ``#< CLIXML`` followed by an ``<Objs>``
    block. The plain-text lines outside it (``ERROR:`` / ``FATAL:`` /
    ``Task_Status:`` from the scheduled-task wrapper) are kept; the CLIXML block
    is decoded via ``_decode_clixml_xml``. Leftover tags are stripped, whitespace
    collapsed, and consecutive duplicate lines deduped. Non-CLIXML stderr (Linux
    guests, plain errors) passes through cleaned. The ``#< CLIXML`` marker never
    appears in the output.
    """
    if not stderr:
        return ''

    text = stderr
    # Locate the <Objs>...</Objs> block (case-insensitive, dot-matches-newline).
    # The opening tag carries a Version attribute (e.g. <Objs Version="1.1.0.1">).
    objs_match = re.search(r'<Objs[^>]*>.*?</Objs>', text, re.IGNORECASE | re.DOTALL)
    if objs_match:
        decoded = _decode_clixml_xml(objs_match.group(0))
        text = text[: objs_match.start()] + '\n' + decoded + '\n' + text[objs_match.end() :]

    # Strip any remaining tags (e.g. stray <S>, <AV>, <Props> fragments).
    text = re.sub(r'<[^>]+>', ' ', text)
    # Drop the CLIXML marker if it survived.
    text = text.replace('#< CLIXML', ' ')

    lines: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r'\s+', ' ', raw).strip()
        if not line:
            continue
        if lines and lines[-1] == line:
            continue  # dedupe consecutive identical lines
        lines.append(line)
    return '\n'.join(lines)


def split_reason(reason: str | None) -> tuple[str, str]:
    """Split a failure reason into ``(summary, detail)``.

    The adarevm-server failure embeds the raw guest stderr after ``. stderr: ``.
    The summary is the text before that boundary (re-dotted); the detail is the
    decoded stderr. Reasons without the boundary yield ``summary = reason`` and
    an empty detail.
    """
    if not reason:
        return '', ''
    marker = '. stderr: '
    idx = reason.find(marker)
    if idx == -1:
        return reason, ''
    summary = reason[:idx].rstrip('.') + '.'
    detail = decode_guest_stderr(reason[idx + len(marker) :])
    return summary, detail


def print_failures(failures: list[tuple[str, str, str]]) -> None:
    """Print a "Failure details" block of ``(stage message, summary, detail)`` entries.

    Uses bare ``print``: the caller has already stopped the flow console's live
    display, so this renders as plain text below the persisted tree.
    """
    if not failures:
        return
    print()
    print("Failure details:")
    for stage_msg, summary, detail in failures:
        print(f"  ✖ {stage_msg}: {summary}")
        for line in detail.splitlines():
            print(f"       {line}")
