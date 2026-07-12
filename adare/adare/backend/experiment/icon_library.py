"""
Windows Icon Library (host side).

Resolves a friendly icon *name* (e.g. ``windows_explorer``) to a PNG file path
that the existing CV matcher can consume. The name -> resolver-spec map is
version-independent and shipped in ``appdata/icon-library.yml``; the actual
bitmap is extracted from the target at runtime via the adarevm ``extract_icon``
tool and cached locally. Microsoft's icons are therefore never redistributed.

Cache layout (see ``config.configdirectory.ICONS_DIR``)::

    <ICONS_DIR>/<os_key>/<term>.png

Keying by ``os_key`` (the OS profile / Windows build) keeps icons from
different Windows versions separate, so an OS upgrade re-extracts instead of
reusing a stale bitmap.

Typical use::

    library = IconLibrary(os_key="windows11")
    png_path = await library.resolve("recycle_bin", vm_client)
    locations = await ctx.host.cv.find_icon(png_path, screenshot)
"""

import base64
import difflib
import logging
import re
from pathlib import Path

import yaml

from adare.config.configdirectory import ICON_LIBRARY_FILE, ICONS_DIR

log = logging.getLogger(__name__)

# Dev-mode fallback: source-tree appdata/ (mirrors os_catalog._load_yaml_profiles).
# icon_library.py lives at adare/adare/backend/experiment/, so parents[3] is the
# adare project directory that contains appdata/.
_SOURCE_REGISTRY = Path(__file__).parents[3] / "appdata" / "icon-library.yml"

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class IconLibraryError(Exception):
    """Base exception for icon library errors."""


class IconRegistryError(IconLibraryError):
    """The icon registry file is missing or malformed."""


class UnknownIconTerm(IconLibraryError):
    """The requested icon term is not defined in the registry."""


class IconExtractionError(IconLibraryError):
    """Extracting/caching the icon from the target failed."""


def _sanitize(name: str) -> str:
    """Make a term or os_key safe for use as a filesystem path component."""
    cleaned = _SAFE_NAME.sub("_", name.strip())
    return cleaned or "_"


class IconLibrary:
    """Resolve icon terms to cached PNG paths, extracting on cache miss."""

    def __init__(
        self,
        os_key: str,
        vm_client=None,
        registry_path: Path | None = None,
        cache_root: Path | None = None,
    ):
        """Initialise the library for a given target OS.

        Args:
            os_key: OS profile / Windows build identifier used to key the cache
                (e.g. ``"windows11"``). Different keys never share cached icons.
            vm_client: Optional connected AdareVMClient bound as the default
                extraction transport. When set, ``resolve(term)`` needs no
                explicit client; callers with their own client may still pass one.
            registry_path: Override for the icon-library.yml location. Defaults
                to the installed appdata copy with a source-tree fallback.
            cache_root: Override for the icon cache root (defaults to ICONS_DIR).
        """
        self.os_key = os_key
        self.vm_client = vm_client
        self.registry_path = registry_path or self._locate_registry()
        self.cache_dir = (cache_root or ICONS_DIR) / _sanitize(os_key)
        self._registry: dict[str, dict] | None = None

    @staticmethod
    def _locate_registry() -> Path:
        """Return the first existing registry path (installed, then source)."""
        for candidate in (ICON_LIBRARY_FILE, _SOURCE_REGISTRY):
            if candidate.is_file():
                return candidate
        # Return the installed path so error messages point at the expected spot.
        return ICON_LIBRARY_FILE

    @property
    def registry(self) -> dict[str, dict]:
        """The loaded term -> spec mapping (lazily read and cached)."""
        if self._registry is None:
            self._registry = self._load_registry()
        return self._registry

    def _load_registry(self) -> dict[str, dict]:
        """Load and validate the icon registry YAML."""
        if not self.registry_path.is_file():
            raise IconRegistryError(
                f"Icon registry not found at {self.registry_path}. "
                f"Ensure appdata/icon-library.yml is installed."
            )
        try:
            data = yaml.safe_load(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise IconRegistryError(f"Failed to read icon registry {self.registry_path}: {exc}") from exc

        if not isinstance(data, dict) or "icons" not in data:
            raise IconRegistryError(
                f"Icon registry {self.registry_path} must be a mapping with an 'icons' key"
            )
        icons = data["icons"]
        if not isinstance(icons, dict):
            raise IconRegistryError(f"'icons' in {self.registry_path} must be a mapping")

        log.debug(f"Loaded {len(icons)} icon terms from {self.registry_path}")
        return icons

    def terms(self) -> list[str]:
        """Return all icon terms defined in the registry (sorted)."""
        return sorted(self.registry.keys())

    def spec_for(self, term: str) -> dict:
        """Return the resolver spec for a term, or raise UnknownIconTerm."""
        spec = self.registry.get(term)
        if spec is None:
            suggestions = difflib.get_close_matches(term, self.terms(), n=3, cutoff=0.5)
            hint = (
                f"Did you mean: {', '.join(suggestions)}?"
                if suggestions
                else f"Run `adare icons list` to see all {len(self.terms())} terms."
            )
            raise UnknownIconTerm(
                f"Icon term '{term}' is not defined in {self.registry_path.name}. {hint}"
            )
        if not isinstance(spec, dict) or not spec:
            raise IconRegistryError(f"Icon term '{term}' has an invalid spec: {spec!r}")
        return spec

    def cached_path(self, term: str) -> Path:
        """Return the cache path for a term (whether or not it exists yet)."""
        return self.cache_dir / f"{_sanitize(term)}.png"

    async def resolve(self, term: str, vm_client=None) -> Path:
        """Resolve a term to a cached PNG path, extracting on cache miss.

        Args:
            term: Friendly icon name defined in the registry.
            vm_client: Connected AdareVMClient used to extract on cache miss.
                Falls back to the client bound at construction.

        Returns:
            Path to the cached PNG for this term and OS key.

        Raises:
            UnknownIconTerm: term not in the registry.
            IconExtractionError: extraction over the websocket failed.
            IconRegistryError: registry missing/malformed.
        """
        spec = self.spec_for(term)
        cache_path = self.cached_path(term)

        if cache_path.is_file() and cache_path.stat().st_size > 0:
            log.debug(f"Icon cache hit: {term} -> {cache_path}")
            return cache_path

        log.info(f"Icon cache miss for '{term}' (os_key={self.os_key}); extracting from target")
        png_bytes = await self._extract(term, spec, vm_client or self.vm_client)

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            cache_path.write_bytes(png_bytes)
        except OSError as exc:
            raise IconExtractionError(f"Failed to write icon cache {cache_path}: {exc}") from exc

        log.info(f"Cached icon '{term}' -> {cache_path} ({len(png_bytes)} bytes)")
        return cache_path

    async def _extract(self, term: str, spec: dict, vm_client) -> bytes:
        """Call the adarevm extract_icon tool and decode the base64 PNG."""
        if vm_client is None:
            raise IconExtractionError(
                f"Cannot extract icon '{term}': no VM client available. "
                f"Icon extraction requires a connected target (agent mode)."
            )
        try:
            result = await vm_client.extract_icon(spec)
        except (RuntimeError, OSError, ConnectionError) as exc:
            raise IconExtractionError(f"extract_icon failed for '{term}' (spec={spec}): {exc}") from exc

        data = result.get("data") if isinstance(result, dict) else None
        if not data:
            raise IconExtractionError(f"extract_icon returned no image data for '{term}' (spec={spec})")
        try:
            return base64.b64decode(data)
        except (ValueError, TypeError) as exc:
            raise IconExtractionError(f"Invalid base64 PNG for '{term}': {exc}") from exc
