"""Provision the VirtualSpice (spice-client) binary from GitHub Releases.

ADARE treats VirtualSpice as a runtime binary dependency rather than vendoring
its source. This module downloads a pinned, tagged release asset, verifies it
against the release's ``SHA256SUMS``, and caches it under the user's data dir so
subsequent runs are network-free.

Cache layout:
    ~/.local/share/adare/virtualspice/<version>/spice-client

Release assets (published by miqsoft/VirtualSpice ``release.yml``):
    spice-client-macos-arm64.tar.gz
    spice-client-macos-x86_64.tar.gz
    spice-client-linux-x86_64.tar.gz
    SHA256SUMS
"""

from __future__ import annotations

import hashlib
import io
import logging
import platform
import tarfile
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Pinned release. Bump this (and republish assets + SHA256SUMS) to roll forward.
VIRTUALSPICE_REPO = "miqsoft/VirtualSpice"
VIRTUALSPICE_VERSION = "v0.1.0"

# Binary name inside the cache (stable, matches what process_manager probes for).
BINARY_NAME = "spice-client"

_RELEASE_BASE = "https://github.com/{repo}/releases/download/{version}"
_CHECKSUMS_NAME = "SHA256SUMS"
_DOWNLOAD_TIMEOUT = 60  # seconds, per-request


class VirtualSpiceProvisionError(Exception):
    """Base error for VirtualSpice binary provisioning."""


class UnsupportedPlatformError(VirtualSpiceProvisionError):
    """No published release asset matches this OS/arch."""


class ReleaseAssetError(VirtualSpiceProvisionError):
    """A release asset (binary or SHA256SUMS) could not be fetched or parsed."""


class ChecksumMismatchError(VirtualSpiceProvisionError):
    """A downloaded asset failed sha256 verification."""


# OS/arch -> release asset stem (without the .tar.gz suffix).
_ASSET_MATRIX: dict[tuple[str, tuple[str, ...]], str] = {
    ("Darwin", ("arm64", "aarch64")): "spice-client-macos-arm64",
    ("Darwin", ("x86_64", "amd64")): "spice-client-macos-x86_64",
    ("Linux", ("x86_64", "amd64")): "spice-client-linux-x86_64",
}


def _asset_stem() -> str:
    """Return the release asset stem for the current platform.

    Raises UnsupportedPlatformError with a specific message otherwise.
    """
    system = platform.system()
    machine = platform.machine().lower()
    for (want_system, want_machines), stem in _ASSET_MATRIX.items():
        if system == want_system and machine in want_machines:
            return stem
    raise UnsupportedPlatformError(
        f"No VirtualSpice release asset for {system}/{machine}. "
        f"Supported: Darwin/arm64, Darwin/x86_64, Linux/x86_64. "
        f"Build from source or set VIRTUALSPICE_BINARY."
    )


def _cache_dir() -> Path:
    return (
        Path.home()
        / ".local"
        / "share"
        / "adare"
        / "virtualspice"
        / VIRTUALSPICE_VERSION
    )


def _binary_path() -> Path:
    return _cache_dir() / BINARY_NAME


def cached_binary_path() -> Path | None:
    """Return the cached binary path if present and executable, else None.

    Network-free — safe to call from process_manager._find_binary().
    """
    import os

    path = _binary_path()
    if path.is_file() and os.access(path, os.X_OK):
        return path
    return None


def is_platform_supported() -> bool:
    """Whether a release asset exists for the current platform (no network)."""
    try:
        _asset_stem()
        return True
    except UnsupportedPlatformError:
        return False


def _release_base() -> str:
    return _RELEASE_BASE.format(repo=VIRTUALSPICE_REPO, version=VIRTUALSPICE_VERSION)


def _fetch_expected_sha256(session, tarball_name: str) -> str:
    """Fetch SHA256SUMS from the release and return the hash for ``tarball_name``."""
    url = f"{_release_base()}/{_CHECKSUMS_NAME}"
    import requests

    try:
        resp = session.get(url, timeout=_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ReleaseAssetError(
            f"Could not fetch {_CHECKSUMS_NAME} from {url}: {exc}"
        ) from exc

    for line in resp.text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Format: "<hexdigest>  <filename>" (two spaces) or "<hexdigest> *<filename>".
        parts = line.split()
        if len(parts) != 2:
            continue
        digest, name = parts
        name = name.lstrip("*")
        if name == tarball_name:
            return digest.lower()

    raise ReleaseAssetError(
        f"{_CHECKSUMS_NAME} has no entry for {tarball_name}"
    )


def _download_bytes(
    session,
    url: str,
    progress_cb: Callable[[int, int], None] | None,
) -> bytes:
    """Stream a URL into memory, invoking progress_cb(downloaded, total)."""
    import requests

    try:
        with session.get(url, stream=True, timeout=_DOWNLOAD_TIMEOUT) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            buf = io.BytesIO()
            downloaded = 0
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                buf.write(chunk)
                downloaded += len(chunk)
                if progress_cb is not None:
                    progress_cb(downloaded, total)
            return buf.getvalue()
    except requests.RequestException as exc:
        raise ReleaseAssetError(f"Download failed for {url}: {exc}") from exc


def _extract_single_binary(tar_bytes: bytes, dest: Path) -> None:
    """Extract the single regular-file member from a .tar.gz into ``dest``.

    Reads the member's bytes directly (never uses member names as filesystem
    paths) so a malicious archive cannot escape the cache directory.
    """
    try:
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
            member = next(
                (m for m in tar.getmembers() if m.isfile()), None
            )
            if member is None:
                raise ReleaseAssetError("Release tarball contains no file member")
            extracted = tar.extractfile(member)
            if extracted is None:
                raise ReleaseAssetError(
                    f"Could not read member {member.name} from release tarball"
                )
            payload = extracted.read()
    except tarfile.TarError as exc:
        raise ReleaseAssetError(f"Malformed release tarball: {exc}") from exc

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".partial")
    tmp.write_bytes(payload)
    tmp.replace(dest)


def ensure_binary(
    progress_cb: Callable[[int, int], None] | None = None,
    *,
    force: bool = False,
) -> Path:
    """Ensure the VirtualSpice binary is present in the managed cache.

    Downloads + sha256-verifies + extracts the pinned release asset if missing.
    Returns the path to the executable. Raises a VirtualSpiceProvisionError
    subclass on any failure (unsupported platform, download, checksum).
    """
    if not force:
        cached = cached_binary_path()
        if cached is not None:
            logger.debug("VirtualSpice already cached at %s", cached)
            return cached

    stem = _asset_stem()
    tarball_name = f"{stem}.tar.gz"
    tarball_url = f"{_release_base()}/{tarball_name}"

    import requests

    with requests.Session() as session:
        expected = _fetch_expected_sha256(session, tarball_name)
        logger.info("Downloading VirtualSpice %s ...", tarball_name)
        data = _download_bytes(session, tarball_url, progress_cb)

    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ChecksumMismatchError(
            f"sha256 mismatch for {tarball_name}: "
            f"expected {expected}, got {actual}"
        )

    dest = _binary_path()
    _extract_single_binary(data, dest)
    dest.chmod(0o755)
    logger.info("VirtualSpice binary installed to %s", dest)
    return dest
