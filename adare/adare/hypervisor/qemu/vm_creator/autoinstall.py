"""Ubuntu autoinstall user-data generation from Jinja2 templates."""

import hashlib
import logging
import secrets
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from adare.config.configdirectory import VM_TEMPLATES_DIR
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel

log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / 'templates'

# Template file mapping by OS name
_TEMPLATE_MAP = {
    'ubuntu2604': 'autoinstall_ubuntu_2604.yaml',
    'ubuntu2604arm64': 'autoinstall_ubuntu_2604.yaml',
    'ubuntu2510': 'autoinstall_ubuntu_2510.yaml',
    'ubuntu2510arm64': 'autoinstall_ubuntu_2510.yaml',
    'ubuntu2404': 'autoinstall_ubuntu_2404.yaml',
    'ubuntu2404arm64': 'autoinstall_ubuntu_2404.yaml',
    'ubuntu2204': 'autoinstall_ubuntu_2204.yaml',
    'ubuntu2204arm64': 'autoinstall_ubuntu_2204.yaml',
}


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
    # Resolve template: os_def.template > _TEMPLATE_MAP > distro fallback
    if os_def.template:
        template_file = os_def.template
    else:
        template_file = _TEMPLATE_MAP.get(os_def.name)
        if template_file is None:
            # Fallback: use latest template matching this distribution
            distro_templates = {k: v for k, v in _TEMPLATE_MAP.items() if k.startswith(os_def.distribution)}
            if distro_templates:
                template_file = distro_templates[max(distro_templates.keys())]
            else:
                raise KeyError(f"No autoinstall template for OS '{os_def.name}'")

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

    Creates the directory structure expected by cloud-init nocloud-net:
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
