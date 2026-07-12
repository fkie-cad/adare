"""
Icon library CLI commands.

Debug/verification helpers for the Windows icon library:

- ``exec_icons_list``: print every term defined in the registry with its spec.
- ``exec_icons_dump_all``: connect to a running target, resolve every registry
  term (extract + cache), and write the PNGs plus an HTML contact sheet to
  ``ICONS_DIR/<os_key>/``. This verifies coverage and version-independence: run
  it against a Win10 VM and a Win11 VM and confirm each term yields a valid
  icon from its own per-build cache dir with no code change.
"""

import html
import logging
from types import SimpleNamespace

from adare.backend.experiment.icon_library import IconLibrary, IconLibraryError
from adare.backend.experiment.websocket_client import AdareVMClient
from adare.exceptions import LoggedException

log = logging.getLogger(__name__)


class IconsCLIError(LoggedException):
    """Error during an icons CLI command."""

    def __init__(self, message: str):
        super().__init__(log, message)


def exec_icons_list(args: SimpleNamespace) -> None:
    """Print all registry terms and their resolver specs (no target needed)."""
    library = IconLibrary(os_key=getattr(args, "os_key", "windows"))
    try:
        terms = library.terms()
    except IconLibraryError as exc:
        raise IconsCLIError(str(exc)) from exc

    print(f"Icon registry: {library.registry_path} ({len(terms)} terms)\n")
    for term in terms:
        print(f"  {term:<28} {library.spec_for(term)}")


async def exec_icons_dump_all(args: SimpleNamespace) -> None:
    """Resolve every registry term on a connected target and dump a contact sheet."""
    host = getattr(args, "host", "localhost")
    port = getattr(args, "port", 18765)
    os_key = getattr(args, "os_key", "windows")
    force = getattr(args, "force", False)

    library = IconLibrary(os_key=os_key)
    try:
        terms = library.terms()
    except IconLibraryError as exc:
        raise IconsCLIError(str(exc)) from exc

    log.info(f"Connecting to adarevm at {host}:{port}")
    client = AdareVMClient(host=host, port=port)
    connected = await client.connect(timeout=getattr(args, "connect_timeout", 15.0))
    if not connected:
        raise IconsCLIError(f"Failed to connect to adarevm at {host}:{port}")

    results: list[tuple[str, object, str | None]] = []
    try:
        for term in terms:
            if force:
                cached = library.cached_path(term)
                if cached.is_file():
                    cached.unlink()
            try:
                path = await library.resolve(term, vm_client=client)
                results.append((term, path, None))
                log.info(f"OK   {term} -> {path}")
            except IconLibraryError as exc:
                results.append((term, None, str(exc)))
                log.warning(f"FAIL {term}: {exc}")
    finally:
        await client.disconnect()

    contact_sheet = _write_contact_sheet(library, results, os_key)

    ok = sum(1 for _, path, err in results if err is None)
    print(f"\nDumped {ok}/{len(results)} icons for os_key='{os_key}'")
    print(f"Cache dir:     {library.cache_dir}")
    print(f"Contact sheet: {contact_sheet}")
    if ok < len(results):
        print("\nFailures:")
        for term, _path, err in results:
            if err is not None:
                print(f"  {term}: {err}")


def _write_contact_sheet(library: IconLibrary, results, os_key: str):
    """Write an HTML contact sheet of the dumped icons into the cache dir."""
    library.cache_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = library.cache_dir / "index.html"

    rows = []
    for term, path, err in results:
        spec = html.escape(str(library.spec_for(term)))
        if err is None:
            cell = f'<img src="{html.escape(path.name)}" width="64" height="64" alt="{html.escape(term)}">'
            status = '<span style="color:#2a2">ok</span>'
        else:
            cell = '<span style="color:#a22">&mdash;</span>'
            status = f'<span style="color:#a22" title="{html.escape(err)}">failed</span>'
        rows.append(
            f"<tr><td>{cell}</td><td><code>{html.escape(term)}</code></td>"
            f"<td><code>{spec}</code></td><td>{status}</td></tr>"
        )

    document = (
        "<!doctype html><meta charset='utf-8'>"
        f"<title>ADARE icon library &mdash; {html.escape(os_key)}</title>"
        "<style>body{font-family:sans-serif;background:#fafafa;padding:1rem}"
        "table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:6px 10px}"
        "img{image-rendering:pixelated;background:#eee}</style>"
        f"<h1>ADARE icon library &mdash; {html.escape(os_key)}</h1>"
        f"<p>{len(results)} terms from {html.escape(str(library.registry_path))}</p>"
        "<table><tr><th>icon</th><th>term</th><th>resolver spec</th><th>status</th></tr>"
        + "".join(rows)
        + "</table>"
    )
    sheet_path.write_text(document, encoding="utf-8")
    return sheet_path
