"""Ubuntu autoinstall user-data generation from Jinja2 templates."""

import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

from adare.config.configdirectory import VM_TEMPLATES_DIR
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel

log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / 'templates'

_SUPPORTED_TEMPLATE_SCHEMA = 1
_FRONTMATTER_RE = re.compile(
    r'\{#-?\s*adare-template\s*\n(?P<body>.*?)\n\s*-?#\}',
    re.DOTALL,
)


@dataclass(frozen=True)
class TemplateMetadata:
    """Self-describing metadata parsed from a template's Jinja-comment frontmatter."""
    id: str
    description: str
    supports: tuple[str, ...]
    schema: int
    maintainer: str
    revision: str
    path: Path


def parse_template_metadata(path: Path) -> TemplateMetadata | None:
    """Parse the ``{# adare-template ... #}`` frontmatter from a template file.

    Returns ``None`` if no frontmatter block is present. Raises ``ValueError``
    if the block is malformed or declares an unsupported schema.
    """
    try:
        head = path.read_text(encoding='utf-8', errors='replace')[:4096]
    except OSError:
        return None
    m = _FRONTMATTER_RE.search(head)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group('body')) or {}
    except yaml.YAMLError as e:
        raise ValueError(f'Invalid YAML in template frontmatter of {path}: {e}') from e
    if not isinstance(data, dict):
        raise ValueError(f'Template frontmatter in {path} must be a YAML mapping')

    schema = data.get('schema', 1)
    if schema != _SUPPORTED_TEMPLATE_SCHEMA:
        raise ValueError(
            f'Unsupported template schema {schema!r} in {path} '
            f'(this adare release supports schema {_SUPPORTED_TEMPLATE_SCHEMA})'
        )

    supports = data.get('supports') or []
    if not isinstance(supports, list) or not all(isinstance(x, str) for x in supports):
        raise ValueError(f"'supports' must be a list of strings in {path}")

    return TemplateMetadata(
        id=str(data.get('id') or path.stem),
        description=str(data.get('description', '')),
        supports=tuple(supports),
        schema=int(schema),
        maintainer=str(data.get('maintainer', '')),
        revision=str(data.get('revision', '')),
        path=path,
    )


def discover_templates(*dirs: Path) -> dict[str, TemplateMetadata]:
    """Scan ``dirs`` for templates with ``adare-template`` frontmatter.

    Returns a mapping ``os_name -> metadata``. Within a single directory, two
    templates claiming the same ``os_name`` raises ``ValueError``. Across
    directories, later arguments override earlier (so user templates can
    override built-ins).
    """
    result: dict[str, TemplateMetadata] = {}
    for d in dirs:
        if d is None or not d.is_dir():
            continue
        per_dir: dict[str, TemplateMetadata] = {}
        for entry in sorted(d.iterdir()):
            if not entry.is_file() or entry.suffix.lower() not in ('.yaml', '.yml'):
                continue
            meta = parse_template_metadata(entry)
            if meta is None:
                continue
            for os_name in meta.supports:
                if os_name in per_dir:
                    raise ValueError(
                        f"Conflicting templates in {d}: '{os_name}' is claimed "
                        f'by both {per_dir[os_name].path.name} and {entry.name}'
                    )
                per_dir[os_name] = meta
        result.update(per_dir)
    return result


_DISCOVERY_CACHE: tuple[tuple[float, float], dict[str, TemplateMetadata]] | None = None


def _discovery_cache_key() -> tuple[float, float]:
    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return -1.0
    return (_mtime(TEMPLATES_DIR), _mtime(VM_TEMPLATES_DIR))


def _cached_discovery() -> dict[str, TemplateMetadata]:
    global _DISCOVERY_CACHE
    key = _discovery_cache_key()
    if _DISCOVERY_CACHE is not None and _DISCOVERY_CACHE[0] == key:
        return _DISCOVERY_CACHE[1]
    discovered = discover_templates(TEMPLATES_DIR, VM_TEMPLATES_DIR)
    _DISCOVERY_CACHE = (key, discovered)
    return discovered


def resolve_template(os_def: OsDefinition) -> str | None:
    """Resolve the template filename for ``os_def``.

    Priority: explicit ``os_def.template`` > discovered metadata map (user dir
    overrides built-in) > distribution-prefix fallback (any discovered entry
    whose ``os_name`` begins with ``os_def.distribution``; ties broken by
    ``max()`` over the keys). Returns ``None`` if nothing matches.
    """
    if os_def.template:
        return os_def.template
    discovered = _cached_discovery()
    meta = discovered.get(os_def.name)
    if meta is not None:
        return meta.path.name
    prefix_matches = {k: v for k, v in discovered.items() if k.startswith(os_def.distribution)}
    if prefix_matches:
        return prefix_matches[max(prefix_matches.keys())].path.name
    return None


def resolve_template_metadata(os_def: OsDefinition) -> TemplateMetadata | None:
    """Return the discovered ``TemplateMetadata`` that would be used for ``os_def``.

    Returns ``None`` if ``os_def.template`` overrides discovery or nothing matches.
    """
    if os_def.template:
        return None
    discovered = _cached_discovery()
    meta = discovered.get(os_def.name)
    if meta is not None:
        return meta
    prefix_matches = {k: v for k, v in discovered.items() if k.startswith(os_def.distribution)}
    if prefix_matches:
        return prefix_matches[max(prefix_matches.keys())]
    return None


def generate_password_hash(password: str) -> str:
    """Generate a SHA-512 crypt hash suitable for autoinstall identity.password.

    Uses the SHA-512 crypt format ($6$salt$hash) compatible with /etc/shadow.
    Implements the crypt-sha512 algorithm since the crypt module was removed in Python 3.13.

    Args:
        password: Plaintext password

    Returns:
        SHA-512 crypt hash string (e.g. $6$salt$hash...)
    """
    salt = secrets.token_hex(8)

    # Use passlib if available (most reliable), otherwise use subprocess with openssl
    try:
        import subprocess
        result = subprocess.run(
            ['openssl', 'passwd', '-6', '-salt', salt, password],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass

    # Fallback: use Python hashlib-based SHA-512 crypt implementation
    return _sha512_crypt(password, salt)


def _sha512_crypt(password: str, salt: str) -> str:
    """Pure Python SHA-512 crypt implementation (simplified).

    Generates a hash compatible with glibc's crypt() using $6$ prefix.
    """

    password_bytes = password.encode('utf-8')
    salt_bytes = salt[:16].encode('utf-8')

    # Step 1-3: Initial digest B
    b = hashlib.sha512(password_bytes + salt_bytes + password_bytes).digest()

    # Step 4-8: Digest A
    a_ctx = hashlib.sha512()
    a_ctx.update(password_bytes + salt_bytes)

    # Step 9-10: Add bytes from B
    plen = len(password_bytes)
    i = plen
    while i > 64:
        a_ctx.update(b)
        i -= 64
    a_ctx.update(b[:i])

    # Step 11: Process password length bits
    i = plen
    while i > 0:
        if i & 1:
            a_ctx.update(b)
        else:
            a_ctx.update(password_bytes)
        i >>= 1
    a = a_ctx.digest()

    # Step 12-13: Digest DP
    dp_ctx = hashlib.sha512()
    for _ in range(plen):
        dp_ctx.update(password_bytes)
    dp = dp_ctx.digest()

    # Step 14: Produce P string
    p = b''
    i = plen
    while i > 64:
        p += dp
        i -= 64
    p += dp[:i]

    # Step 15-16: Digest DS
    ds_ctx = hashlib.sha512()
    for _ in range(16 + a[0]):
        ds_ctx.update(salt_bytes)
    ds = ds_ctx.digest()

    # Step 17: Produce S string
    s = b''
    i = len(salt_bytes)
    while i > 64:
        s += ds
        i -= 64
    s += ds[:i]

    # Step 18-19: Rounds
    c = a
    for i in range(5000):
        ctx = hashlib.sha512()
        if i & 1:
            ctx.update(p)
        else:
            ctx.update(c)
        if i % 3:
            ctx.update(s)
        if i % 7:
            ctx.update(p)
        if i & 1:
            ctx.update(c)
        else:
            ctx.update(p)
        c = ctx.digest()

    # Step 20: Encode
    itoa64 = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

    def _encode_triple(a_val, b_val, c_val, n):
        v = (a_val << 16) | (b_val << 8) | c_val
        result = ''
        for _ in range(n):
            result += itoa64[v & 0x3F]
            v >>= 6
        return result

    encoded = (
        _encode_triple(c[0], c[21], c[42], 4) +
        _encode_triple(c[22], c[43], c[1], 4) +
        _encode_triple(c[44], c[2], c[23], 4) +
        _encode_triple(c[3], c[24], c[45], 4) +
        _encode_triple(c[25], c[46], c[4], 4) +
        _encode_triple(c[47], c[5], c[26], 4) +
        _encode_triple(c[6], c[27], c[48], 4) +
        _encode_triple(c[28], c[49], c[7], 4) +
        _encode_triple(c[50], c[8], c[29], 4) +
        _encode_triple(c[9], c[30], c[51], 4) +
        _encode_triple(c[31], c[52], c[10], 4) +
        _encode_triple(c[53], c[11], c[32], 4) +
        _encode_triple(c[12], c[33], c[54], 4) +
        _encode_triple(c[34], c[55], c[13], 4) +
        _encode_triple(c[56], c[14], c[35], 4) +
        _encode_triple(c[15], c[36], c[57], 4) +
        _encode_triple(c[37], c[58], c[16], 4) +
        _encode_triple(c[59], c[17], c[38], 4) +
        _encode_triple(c[18], c[39], c[60], 4) +
        _encode_triple(c[40], c[61], c[19], 4) +
        _encode_triple(c[62], c[20], c[41], 4) +
        _encode_triple(0, 0, c[63], 2)
    )

    return f'$6${salt_bytes.decode()}${encoded}'


def generate_user_data(os_def: OsDefinition, vm_name: str, setup_level: int = SetupLevel.FULL) -> str:
    """Generate autoinstall user-data YAML for an Ubuntu installation.

    Args:
        os_def: OS definition from the catalog
        vm_name: Name for the VM (used as hostname)
        setup_level: VM setup level (0=bare, 1=base, 2=full)

    Returns:
        Complete user-data YAML content as a string

    Raises:
        KeyError: If no template exists for the given OS
    """
    template_file = resolve_template(os_def)
    if template_file is None:
        discovered = _cached_discovery()
        ids = sorted({m.id for m in discovered.values()}) or ['(none)']
        raise KeyError(
            f"No autoinstall template for OS '{os_def.name}'. "
            f"Discovered template IDs: {', '.join(ids)}. "
            f'Searched: built-in={TEMPLATES_DIR}, user={VM_TEMPLATES_DIR}.'
        )

    # Sanitize hostname (RFC 1123: lowercase alphanumeric and hyphens)
    hostname = vm_name.lower().replace('_', '-').replace(' ', '-')
    hostname = ''.join(c for c in hostname if c.isalnum() or c == '-')
    hostname = hostname.strip('-')[:63] or 'adare-vm'

    password_hash = generate_password_hash('adare')

    # Search user templates first, then built-in templates
    search_paths = [str(VM_TEMPLATES_DIR), str(TEMPLATES_DIR)]
    env = Environment(
        loader=FileSystemLoader(search_paths),
        keep_trailing_newline=True,
    )
    template = env.get_template(template_file)

    # Miniforge uses 'aarch64' for ARM and 'x86_64' for Intel in its download URLs
    miniforge_arch = 'aarch64' if os_def.architecture == 'aarch64' else 'x86_64'

    user_data = template.render(
        hostname=hostname,
        password_hash=password_hash,
        miniforge_arch=miniforge_arch,
        setup_level=setup_level,
    )

    log.info(f'Generated autoinstall user-data for {os_def.display_name} (hostname: {hostname})')
    return user_data


def write_autoinstall_dir(os_def: OsDefinition, vm_name: str, output_dir: Path, setup_level: int = SetupLevel.FULL) -> Path:
    """Write autoinstall user-data and meta-data files to a directory.

    Creates the file pair expected by the cloud-init NoCloud datasource:
      output_dir/
        user-data
        meta-data   (empty file, required by cloud-init)

    Args:
        os_def: OS definition from the catalog
        vm_name: Name for the VM
        output_dir: Directory to write files to
        setup_level: VM setup level (0=bare, 1=base, 2=full)

    Returns:
        Path to the output directory
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    user_data = generate_user_data(os_def, vm_name, setup_level=setup_level)
    (output_dir / 'user-data').write_text(user_data)
    (output_dir / 'meta-data').write_text('')

    log.info(f'Wrote autoinstall files to {output_dir}')
    return output_dir
