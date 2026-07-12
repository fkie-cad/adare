"""
Windows icon extraction via Win32 API (ctypes).

Given a version-independent *resolver spec*, this module resolves the correct
icon on THIS Windows machine using documented shell APIs, then renders the
largest available variant to a PNG (returned as base64). Microsoft's bitmaps
are therefore never shipped -- extraction happens at runtime on the licensed
target and is cached by the host.

The key idea: Windows already knows which DLL/index a semantic icon lives at
for this build, so we ask it via stable APIs instead of maintaining a
per-version DLL/index table. Every strategy reduces to a
``(icon_source_path, icon_index)`` pair, and a single renderer then extracts
that icon at ``DESIRED_SIZE`` via ``PrivateExtractIconsW`` and encodes a PNG.

Resolver spec forms (each a single-strategy mapping)::

    {"stock": "SIID_FOLDER"}                 -> SHGetStockIconInfo
    {"exe": "%SystemRoot%\\\\explorer.exe"}   -> icon 0 of an executable
    {"app": "chrome.exe"}                    -> App Paths registry -> exe
    {"fileassoc": ".pdf"}                    -> SHGetFileInfo(USEFILEATTRIBUTES)
    {"dll": "imageres.dll", "index": 3}      -> explicit fallback (rare)

Follows the ctypes structure/error style of ``platforms/mft_reader.py``:
lazy ``import ctypes`` inside the Windows-only code paths, explicit Win32 error
checks, and specific exception types (no bare ``except``).
"""

import base64
import io
import logging
import os
import platform

log = logging.getLogger(__name__)

# Default extraction size. 256px ("jumbo") is the largest embedded variant on
# modern Windows; PrivateExtractIconsW scales up when a term has no 256 variant.
# The host CV matcher is scale-invariant, so a good large PNG is all we need.
DESIRED_SIZE = 256

# --- SHGetStockIconInfo flags (SHGSI_*) ---
SHGSI_ICONLOCATION = 0x000000000  # fill szPath + iIcon (no HICON created)

# --- SHGetFileInfo flags (SHGFI_*) ---
SHGFI_ICONLOCATION = 0x000001000  # fill szDisplayName (icon file) + iIcon
SHGFI_USEFILEATTRIBUTES = 0x000000010  # treat pszPath as a notional file
FILE_ATTRIBUTE_NORMAL = 0x00000080

# --- GDI constants ---
BI_RGB = 0
DIB_RGB_COLORS = 0
MAX_PATH = 260

# Registry: App Paths (per-machine, then per-user)
_APP_PATHS_SUBKEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"

# SHSTOCKICONID enum (shellapi.h). These values are fixed by Microsoft and
# version-stable by design -- that stability is exactly why we resolve by
# stock ID rather than by DLL/index. Names map to their integer SIID value.
SHSTOCKICONID: dict[str, int] = {
    "SIID_DOCNOASSOC": 0,
    "SIID_DOCASSOC": 1,
    "SIID_APPLICATION": 2,
    "SIID_FOLDER": 3,
    "SIID_FOLDEROPEN": 4,
    "SIID_DRIVE525": 5,
    "SIID_DRIVE35": 6,
    "SIID_DRIVEREMOVE": 7,
    "SIID_DRIVEFIXED": 8,
    "SIID_DRIVENET": 9,
    "SIID_DRIVENETDISABLED": 10,
    "SIID_DRIVECD": 11,
    "SIID_DRIVERAM": 12,
    "SIID_WORLD": 13,
    "SIID_SERVER": 15,
    "SIID_PRINTER": 16,
    "SIID_MYNETWORK": 17,
    "SIID_FIND": 22,
    "SIID_HELP": 23,
    "SIID_SHARE": 28,
    "SIID_LINK": 29,
    "SIID_SLOWFILE": 30,
    "SIID_RECYCLER": 31,
    "SIID_RECYCLERFULL": 32,
    "SIID_MEDIACDAUDIO": 40,
    "SIID_LOCK": 47,
    "SIID_AUTOLIST": 49,
    "SIID_PRINTERNET": 50,
    "SIID_SERVERSHARE": 51,
    "SIID_PRINTERFAX": 52,
    "SIID_PRINTERFAXNET": 53,
    "SIID_PRINTERFILE": 54,
    "SIID_STACK": 55,
    "SIID_MEDIASVCD": 56,
    "SIID_STUFFEDFOLDER": 57,
    "SIID_DRIVEUNKNOWN": 58,
    "SIID_DRIVEDVD": 59,
    "SIID_MEDIADVD": 60,
    "SIID_MEDIADVDRAM": 61,
    "SIID_MEDIADVDRW": 62,
    "SIID_MEDIADVDR": 63,
    "SIID_MEDIADVDROM": 64,
    "SIID_MEDIACDAUDIOPLUS": 65,
    "SIID_MEDIACDRW": 66,
    "SIID_MEDIACDR": 67,
    "SIID_MEDIACDBURN": 68,
    "SIID_MEDIABLANKCD": 69,
    "SIID_MEDIACDROM": 70,
    "SIID_AUDIOFILES": 71,
    "SIID_IMAGEFILES": 72,
    "SIID_VIDEOFILES": 73,
    "SIID_MIXEDFILES": 74,
    "SIID_FOLDERBACK": 75,
    "SIID_FOLDERFRONT": 76,
    "SIID_SHIELD": 77,
    "SIID_WARNING": 78,
    "SIID_INFO": 79,
    "SIID_ERROR": 80,
    "SIID_KEY": 81,
    "SIID_SOFTWARE": 82,
    "SIID_RENAME": 83,
    "SIID_DELETE": 84,
    "SIID_MEDIAAUDIODVD": 85,
    "SIID_MEDIAMOVIEDVD": 86,
    "SIID_MEDIAENHANCEDCD": 87,
    "SIID_MEDIAENHANCEDDVD": 88,
    "SIID_MEDIAHDDVD": 89,
    "SIID_MEDIABLURAY": 90,
    "SIID_MEDIAVCD": 91,
    "SIID_MEDIADVDPLUSR": 92,
    "SIID_MEDIADVDPLUSRW": 93,
    "SIID_DESKTOPPC": 94,
    "SIID_MOBILEPC": 95,
    "SIID_USERS": 96,
    "SIID_MEDIASMARTMEDIA": 97,
    "SIID_MEDIACOMPACTFLASH": 98,
    "SIID_DEVICECELLPHONE": 99,
    "SIID_DEVICECAMERA": 100,
    "SIID_DEVICEVIDEOCAMERA": 101,
    "SIID_DEVICEAUDIOPLAYER": 102,
    "SIID_DEVICENETWORKCONNECT": 103,
    "SIID_INTERNET": 104,
    "SIID_ZIPFILE": 105,
    "SIID_SETTINGS": 106,
    "SIID_DRIVEHDDVD": 132,
    "SIID_DRIVEBD": 133,
    "SIID_MEDIAHDDVDROM": 134,
    "SIID_MEDIAHDDVDR": 135,
    "SIID_MEDIAHDDVDRAM": 136,
    "SIID_MEDIABDROM": 137,
    "SIID_MEDIABDR": 138,
    "SIID_MEDIABDRE": 139,
    "SIID_CLUSTEREDDRIVE": 140,
}


class WindowsIconError(Exception):
    """Base exception for Windows icon extraction errors."""


class UnsupportedPlatformError(WindowsIconError):
    """Icon extraction attempted on a non-Windows platform."""


class IconSpecError(WindowsIconError):
    """The resolver spec is malformed or references an unknown value."""


class IconResolutionError(WindowsIconError):
    """A Win32 API failed to resolve the spec to an icon source."""


class IconRenderError(WindowsIconError):
    """The resolved icon could not be rendered to a PNG."""


def _require_windows() -> None:
    """Raise UnsupportedPlatformError unless running on Windows."""
    if platform.system().lower() != "windows":
        raise UnsupportedPlatformError(
            f"Windows icon extraction is only supported on Windows "
            f"(current platform: {platform.system()})"
        )


def _make_structs():
    """Build the ctypes structures needed for icon extraction.

    Defined lazily inside a function so importing this module never touches
    ``ctypes.wintypes`` on non-Windows hosts (mirrors mft_reader.py).
    """
    import ctypes
    from ctypes import wintypes

    class SHSTOCKICONINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hIcon", wintypes.HICON),
            ("iSysImageIndex", ctypes.c_int),
            ("iIcon", ctypes.c_int),
            ("szPath", wintypes.WCHAR * MAX_PATH),
        ]

    class SHFILEINFOW(ctypes.Structure):
        _fields_ = [
            ("hIcon", wintypes.HICON),
            ("iIcon", ctypes.c_int),
            ("dwAttributes", wintypes.DWORD),
            ("szDisplayName", wintypes.WCHAR * MAX_PATH),
            ("szTypeName", wintypes.WCHAR * 80),
        ]

    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", wintypes.BOOL),
            ("xHotspot", wintypes.DWORD),
            ("yHotspot", wintypes.DWORD),
            ("hbmMask", wintypes.HBITMAP),
            ("hbmColor", wintypes.HBITMAP),
        ]

    class BITMAP(ctypes.Structure):
        _fields_ = [
            ("bmType", wintypes.LONG),
            ("bmWidth", wintypes.LONG),
            ("bmHeight", wintypes.LONG),
            ("bmWidthBytes", wintypes.LONG),
            ("bmPlanes", wintypes.WORD),
            ("bmBitsPixel", wintypes.WORD),
            ("bmBits", ctypes.c_void_p),
        ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ("bmiHeader", BITMAPINFOHEADER),
            ("bmiColors", wintypes.DWORD * 3),
        ]

    return {
        "SHSTOCKICONINFO": SHSTOCKICONINFO,
        "SHFILEINFOW": SHFILEINFOW,
        "ICONINFO": ICONINFO,
        "BITMAP": BITMAP,
        "BITMAPINFOHEADER": BITMAPINFOHEADER,
        "BITMAPINFO": BITMAPINFO,
    }


# ---------------------------------------------------------------------------
# Strategy resolvers: each maps a spec to an (icon_source_path, icon_index)
# ---------------------------------------------------------------------------

def _resolve_stock(name: str) -> tuple[str, int]:
    """Resolve a SHSTOCKICONID name to (path, index) via SHGetStockIconInfo."""
    import ctypes

    if name not in SHSTOCKICONID:
        raise IconSpecError(f"Unknown stock icon id: {name!r}")
    siid = SHSTOCKICONID[name]

    structs = _make_structs()
    info = structs["SHSTOCKICONINFO"]()
    info.cbSize = ctypes.sizeof(info)

    hresult = ctypes.windll.shell32.SHGetStockIconInfo(
        siid, SHGSI_ICONLOCATION, ctypes.byref(info)
    )
    if hresult != 0:
        raise IconResolutionError(
            f"SHGetStockIconInfo failed for {name} (siid={siid}): HRESULT 0x{hresult & 0xFFFFFFFF:08X}"
        )

    path = os.path.expandvars(info.szPath)
    log.info(f"CLAUDE: stock {name} -> {path!r} index {info.iIcon}")
    return path, info.iIcon


def _resolve_exe(exe: str) -> tuple[str, int]:
    """Resolve an executable path to (path, index 0)."""
    path = os.path.expandvars(exe)
    if not os.path.isfile(path):
        raise IconResolutionError(f"Executable not found for icon extraction: {path!r}")
    log.info(f"CLAUDE: exe {exe!r} -> {path!r} index 0")
    return path, 0


def _resolve_app(app: str) -> tuple[str, int]:
    """Resolve an App Paths registry entry to its executable's (path, index 0).

    Looks up ``App Paths\\<app>`` under HKLM then HKCU. The default value is
    the executable's full path (this is how ``Start > Run`` resolves names).
    """
    import winreg

    subkey = f"{_APP_PATHS_SUBKEY}\\{app}"
    exe_path = None
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value, _ = winreg.QueryValueEx(key, None)
                if value:
                    exe_path = value
                    break
        except FileNotFoundError:
            continue
        except OSError as exc:
            log.warning(f"CLAUDE: App Paths lookup error for {app!r}: {exc}")
            continue

    if not exe_path:
        raise IconResolutionError(f"No App Paths registry entry found for {app!r}")

    return _resolve_exe(exe_path.strip('"'))


def _resolve_fileassoc(extension: str) -> tuple[str, int]:
    """Resolve a file extension to its associated icon (path, index).

    Uses SHGetFileInfoW with SHGFI_USEFILEATTRIBUTES so no real file is
    touched -- ``pszPath`` is treated as a notional file name.
    """
    import ctypes

    if not extension.startswith("."):
        raise IconSpecError(f"File association must start with a dot: {extension!r}")

    structs = _make_structs()
    info = structs["SHFILEINFOW"]()
    notional = f"dummy{extension}"

    ret = ctypes.windll.shell32.SHGetFileInfoW(
        ctypes.c_wchar_p(notional),
        FILE_ATTRIBUTE_NORMAL,
        ctypes.byref(info),
        ctypes.sizeof(info),
        SHGFI_ICONLOCATION | SHGFI_USEFILEATTRIBUTES,
    )
    if ret == 0:
        raise IconResolutionError(f"SHGetFileInfoW failed for extension {extension!r}")

    path = os.path.expandvars(info.szDisplayName)
    if not path:
        raise IconResolutionError(f"No icon location returned for extension {extension!r}")
    log.info(f"CLAUDE: fileassoc {extension!r} -> {path!r} index {info.iIcon}")
    return path, info.iIcon


def _resolve_dll(dll: str, index: int) -> tuple[str, int]:
    """Resolve an explicit (dll, index) fallback. Rare -- only for icons with
    no stock id and no owning executable."""
    path = os.path.expandvars(dll)
    log.info(f"CLAUDE: dll {dll!r} index {index} -> {path!r}")
    return path, int(index)


def _resolve_spec_to_source(spec: dict) -> tuple[str, int]:
    """Dispatch a resolver spec to its (icon_source_path, icon_index) pair."""
    if not isinstance(spec, dict) or not spec:
        raise IconSpecError(f"Resolver spec must be a non-empty mapping, got {spec!r}")

    if "stock" in spec:
        return _resolve_stock(str(spec["stock"]))
    if "exe" in spec:
        return _resolve_exe(str(spec["exe"]))
    if "app" in spec:
        return _resolve_app(str(spec["app"]))
    if "fileassoc" in spec:
        return _resolve_fileassoc(str(spec["fileassoc"]))
    if "dll" in spec:
        if "index" not in spec:
            raise IconSpecError("dll spec requires an 'index' field")
        return _resolve_dll(str(spec["dll"]), spec["index"])

    raise IconSpecError(
        f"Unrecognised resolver spec; expected one of "
        f"stock/exe/app/fileassoc/dll, got keys {sorted(spec.keys())}"
    )


# ---------------------------------------------------------------------------
# Extraction + rendering
# ---------------------------------------------------------------------------

def _extract_hicon(path: str, index: int, size: int):
    """Extract a single HICON at ``size`` via PrivateExtractIconsW.

    Returns the HICON handle. Caller must DestroyIcon it.
    """
    import ctypes
    from ctypes import wintypes

    hicon = wintypes.HICON()
    icon_id = wintypes.UINT()

    extracted = ctypes.windll.user32.PrivateExtractIconsW(
        ctypes.c_wchar_p(path),
        int(index),
        int(size),
        int(size),
        ctypes.byref(hicon),
        ctypes.byref(icon_id),
        1,
        0,
    )
    if extracted < 1 or not hicon.value:
        raise IconResolutionError(
            f"PrivateExtractIconsW extracted no icon from {path!r} index {index} "
            f"at {size}px (returned {extracted})"
        )
    return hicon


def _dib_bytes(hdc, hbitmap, width: int, height: int, structs) -> bytes:
    """GetDIBits a 32bpp top-down BGRA buffer from an HBITMAP."""
    import ctypes

    bmi = structs["BITMAPINFO"]()
    bmi.bmiHeader.biSize = ctypes.sizeof(structs["BITMAPINFOHEADER"])
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # negative => top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB

    buf = ctypes.create_string_buffer(width * height * 4)
    scanlines = ctypes.windll.gdi32.GetDIBits(
        hdc, hbitmap, 0, height, buf, ctypes.byref(bmi), DIB_RGB_COLORS
    )
    if scanlines == 0:
        raise IconRenderError("GetDIBits returned 0 scanlines")
    return buf.raw


def _hicon_to_png(hicon, size: int) -> bytes:
    """Render an HICON to PNG bytes, preserving/deriving the alpha channel."""
    import ctypes

    structs = _make_structs()
    info = structs["ICONINFO"]()
    if not ctypes.windll.user32.GetIconInfo(hicon, ctypes.byref(info)):
        raise IconRenderError("GetIconInfo failed")

    hbm_color = info.hbmColor
    hbm_mask = info.hbmMask
    hdc = ctypes.windll.user32.GetDC(0)
    try:
        bmp = structs["BITMAP"]()
        if hbm_color:
            ctypes.windll.gdi32.GetObjectW(
                hbm_color, ctypes.sizeof(bmp), ctypes.byref(bmp)
            )
            width, height = bmp.bmWidth, bmp.bmHeight
        else:
            # Monochrome icon: mask holds AND+XOR stacked vertically.
            ctypes.windll.gdi32.GetObjectW(
                hbm_mask, ctypes.sizeof(bmp), ctypes.byref(bmp)
            )
            width, height = bmp.bmWidth, bmp.bmHeight // 2

        color = _dib_bytes(hdc, hbm_color, width, height, structs) if hbm_color else None
        mask = _dib_bytes(hdc, hbm_mask, width, height, structs)

        rgba = _compose_rgba(color, mask, width, height)
    finally:
        ctypes.windll.user32.ReleaseDC(0, hdc)
        if hbm_color:
            ctypes.windll.gdi32.DeleteObject(hbm_color)
        if hbm_mask:
            ctypes.windll.gdi32.DeleteObject(hbm_mask)

    return _encode_png(rgba, width, height)


def _compose_rgba(color: bytes | None, mask: bytes, width: int, height: int) -> bytes:
    """Convert BGRA color bits (+ AND mask) to straight RGBA bytes.

    Modern 32bpp icons carry their own per-pixel alpha. When the color bitmap
    has an all-zero alpha channel (legacy icons), alpha is derived from the
    monochrome AND mask (white = transparent, black = opaque).
    """
    n = width * height
    out = bytearray(n * 4)

    if color is None:
        # Monochrome icon: treat mask as opacity, paint black where opaque.
        for i in range(n):
            transparent = mask[i * 4] != 0  # blue byte of the 32bpp-expanded mask
            out[i * 4 + 3] = 0 if transparent else 255
        return bytes(out)

    has_alpha = any(color[i * 4 + 3] != 0 for i in range(n))
    for i in range(n):
        b = color[i * 4 + 0]
        g = color[i * 4 + 1]
        r = color[i * 4 + 2]
        a = color[i * 4 + 3]
        if not has_alpha:
            a = 0 if mask[i * 4] != 0 else 255
        out[i * 4 + 0] = r
        out[i * 4 + 1] = g
        out[i * 4 + 2] = b
        out[i * 4 + 3] = a
    return bytes(out)


def _encode_png(rgba: bytes, width: int, height: int) -> bytes:
    """Encode straight RGBA bytes to a PNG.

    Prefers Pillow (already a target dependency via pyautogui screenshots);
    falls back to a self-contained stdlib zlib encoder so extraction never
    hard-depends on Pillow being importable.
    """
    try:
        from PIL import Image
    except ImportError:
        return _encode_png_stdlib(rgba, width, height)

    image = Image.frombuffer("RGBA", (width, height), rgba, "raw", "RGBA", 0, 1)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _encode_png_stdlib(rgba: bytes, width: int, height: int) -> bytes:
    """Minimal PNG encoder (RGBA, no filtering) using only stdlib zlib."""
    import struct as _struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            _struct.pack(">I", len(data))
            + tag
            + data
            + _struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter type: none
        raw.extend(rgba[y * stride:(y + 1) * stride])

    ihdr = _struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    return png


def extract_icon_png(spec: dict, size: int = DESIRED_SIZE) -> str:
    """Resolve a spec on this machine and return the icon as a base64 PNG.

    This is the public entry point used by the adarevm ``extract_icon`` tool.

    Args:
        spec: Resolver spec (single strategy: stock/exe/app/fileassoc/dll).
        size: Desired icon edge in pixels (default 256).

    Returns:
        Base64-encoded PNG string (largest available variant).

    Raises:
        UnsupportedPlatformError: not running on Windows.
        IconSpecError: malformed spec.
        IconResolutionError: a Win32 API failed to resolve the icon source.
        IconRenderError: the resolved icon could not be rendered.
    """
    _require_windows()

    import ctypes

    path, index = _resolve_spec_to_source(spec)
    hicon = _extract_hicon(path, index, size)
    try:
        png_bytes = _hicon_to_png(hicon, size)
    finally:
        ctypes.windll.user32.DestroyIcon(hicon)

    encoded = base64.b64encode(png_bytes).decode("ascii")
    log.info(f"CLAUDE: extracted icon for spec {spec} -> {len(png_bytes)} byte PNG")
    return encoded


def _build_cli_spec(args) -> dict:
    """Build a resolver spec from parsed CLI arguments (unit-check helper)."""
    if args.stock:
        return {"stock": args.stock}
    if args.exe:
        return {"exe": args.exe}
    if args.app:
        return {"app": args.app}
    if args.fileassoc:
        return {"fileassoc": args.fileassoc}
    if args.dll:
        return {"dll": args.dll, "index": args.index}
    raise IconSpecError("Provide one of --stock/--exe/--app/--fileassoc/--dll")


def main(argv=None) -> int:
    """CLI for the manual extraction unit check (verification step 1).

    Example::

        python -m adarevm.platforms.windows_icons --exe %SystemRoot%\\explorer.exe -o explorer.png
        python -m adarevm.platforms.windows_icons --stock SIID_RECYCLER -o recycle.png
    """
    import argparse

    parser = argparse.ArgumentParser(description="Extract a Windows icon to PNG.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stock", help="SHSTOCKICONID name, e.g. SIID_FOLDER")
    group.add_argument("--exe", help="Executable path (icon index 0)")
    group.add_argument("--app", help="App Paths registry name, e.g. chrome.exe")
    group.add_argument("--fileassoc", help="File extension, e.g. .pdf")
    group.add_argument("--dll", help="DLL/exe path for explicit (dll,index) fallback")
    parser.add_argument("--index", type=int, default=0, help="Icon index for --dll")
    parser.add_argument("--size", type=int, default=DESIRED_SIZE, help="Icon size (px)")
    parser.add_argument("-o", "--output", default="icon.png", help="Output PNG path")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    spec = _build_cli_spec(args)
    encoded = extract_icon_png(spec, size=args.size)
    data = base64.b64decode(encoded)
    with open(args.output, "wb") as handle:
        handle.write(data)
    print(f"Wrote {len(data)} bytes to {args.output} (spec={spec})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
