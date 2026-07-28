"""Tests for recipe / base hash identity (T1, T2, T3, T6).

The load-bearing test here is :func:`test_golden_recipe_hash_of_win11arm64_fresh`
— the guard that adding build-time provisioning and the BYO ISO form moved NO
existing environment's identity. A moved hash silently orphans every already-built
disk on every user's machine and forces multi-hour rebuilds.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

from adare.backend.vm.recipe import compute_base_hash, compute_recipe_hash
from adare.types.environment import parse_environment_file

# The shipped `win11arm64-fresh.yml`, byte-for-byte in dict form.
_WIN11ARM64_FRESH = {
    'vm_type': 'recipe',
    'hypervisor': 'qemu',
    'recipe': {
        'profile': 'windows11arm64',
        'iso': '/Users/miq/Documents/ISO/Win11_25H2_English_Arm64_v2.iso',
        'iso_sha256': '638aa2c88e94385b00f4f178d071e3df0b7d9e335577a83bd533b7f2eb65adf0',
        'template': 'autounattend_win11_arm64.xml',
        'params': {'setup_level': 2, 'disk_size': '120G'},
    },
    'os': {
        'os': 'Windows 11 (ARM64)', 'platform': 'windows', 'distribution': 'Home',
        'version': '11', 'language': 'English', 'architecture': 'aarch64',
    },
}

# T1 GOLDEN VALUE. This is the recipe hash of the environment above, and a disk
# built from it exists in the wild as `windows11arm64-ded5718198b9.qcow2`.
#
# It MUST be updated if — and only if — the shipped
# `templates/autounattend_win11_arm64.xml` is edited, since the hash folds in that
# template's own sha256. Any OTHER change that moves this value is a bug: it means
# an existing environment's identity shifted and every cached disk built from it
# has been orphaned.
GOLDEN_RECIPE_HASH = 'ded5718198b93145e8ba6df11daf40f84974b278f537298490b3bacd0a852085'


# --- Helpers ---

def _hash(env_dict: dict, tmp_path: Path) -> tuple[str, str]:
    """Write *env_dict* as an environment file and return (recipe_hash, base_hash)."""
    env_file = tmp_path / f'env-{abs(hash(yaml.dump(env_dict, sort_keys=True)))}.yml'
    env_file.write_text(yaml.dump(env_dict))
    metadata = parse_environment_file(env_file)
    return compute_recipe_hash(metadata), compute_base_hash(metadata)


def _fresh(**recipe_overrides) -> dict:
    """A deep copy of the golden environment, with `recipe:` keys overridden."""
    env = yaml.safe_load(yaml.dump(_WIN11ARM64_FRESH))
    env['recipe'].update(recipe_overrides)
    return env


def _autopsy_provision(versions: list[str]) -> list[dict]:
    """The Phase-3 Autopsy provision shape, parameterized by version list."""
    return [
        {'name': 'boot-hardening', 'shell': 'cmd',
         'command': 'bcdedit /set {default} recoveryenabled No'},
        {'name': 'autopsy', 'description': 'Autopsy {{ item }}', 'for_each': versions,
         'steps': [
             {'name': 'autopsy-{{ item }}-download',
              'command': 'curl.exe -L -f -o "C:\\Windows\\Temp\\autopsy-{{ item }}.msi" '
                         'https://example.invalid/autopsy-{{ item }}-64bit.msi',
              'timeout_minutes': 20},
             {'name': 'autopsy-{{ item }}-install',
              'command': 'msiexec /i "C:\\Windows\\Temp\\autopsy-{{ item }}.msi"',
              'allow_exit_codes': [0, 3010],
              'verify': 'if (-not (Test-Path "C:\\Program Files\\Autopsy-{{ item }}")) { exit 1 }',
              'log_files': ['C:\\Windows\\Temp\\autopsy-{{ item }}-msi.log'],
              'timeout_minutes': 45},
         ]},
    ]


# --- T1: the golden hash ---

def test_golden_recipe_hash_of_win11arm64_fresh(tmp_path):
    """No existing recipe environment's identity moved. See GOLDEN_RECIPE_HASH."""
    recipe_hash, _ = _hash(_WIN11ARM64_FRESH, tmp_path)
    assert recipe_hash == GOLDEN_RECIPE_HASH


def test_shipped_win11arm64_fresh_file_still_parses_and_hashes_the_same():
    """The real file on disk, not a reconstruction — catches a schema regression."""
    shipped = Path(__file__).parents[6] / 'win11arm64-fresh.yml'
    if not shipped.is_file():  # pragma: no cover - layout guard
        pytest.skip(f'shipped recipe not found at {shipped}')
    metadata = parse_environment_file(shipped)
    assert compute_recipe_hash(metadata) == GOLDEN_RECIPE_HASH


# --- T2: base hash vs recipe hash ---

def test_base_hash_equals_recipe_hash_when_there_is_no_provision(tmp_path):
    """No provision steps => Stage 2 is skipped and behaviour is unchanged."""
    recipe_hash, base_hash = _hash(_WIN11ARM64_FRESH, tmp_path)
    assert recipe_hash == base_hash


def test_base_hash_differs_from_recipe_hash_when_provision_is_present(tmp_path):
    env = _fresh(provision=_autopsy_provision(['4.4.0']))
    recipe_hash, base_hash = _hash(env, tmp_path)
    assert recipe_hash != base_hash


def test_provision_does_not_change_the_base_hash(tmp_path):
    """The whole point of the two-level cache: solr4 and solr8 share one OS install."""
    _, plain_base = _hash(_WIN11ARM64_FRESH, tmp_path)
    _, solr4_base = _hash(_fresh(provision=_autopsy_provision(['4.4.0', '4.4.1'])), tmp_path)
    _, solr8_base = _hash(_fresh(provision=_autopsy_provision(['4.18.0'])), tmp_path)
    assert plain_base == solr4_base == solr8_base == GOLDEN_RECIPE_HASH


def test_two_recipes_differing_only_in_provision_have_different_recipe_hashes(tmp_path):
    solr4, _ = _hash(_fresh(provision=_autopsy_provision(['4.4.0'])), tmp_path)
    solr8, _ = _hash(_fresh(provision=_autopsy_provision(['4.18.0'])), tmp_path)
    assert solr4 != solr8


# --- T3: expansion-based hashing ---

def _substitute(value, item: str):
    """Recursively replace `{{ item }}` in a nested dict/list/str structure.

    Done in Python rather than by round-tripping through YAML: `yaml.dump`
    line-folds long strings, which splits a `{{ item }}` occurrence across the fold
    and makes a textual replace miss it.
    """
    if isinstance(value, str):
        return value.replace('{{ item }}', item)
    if isinstance(value, list):
        return [_substitute(entry, item) for entry in value]
    if isinstance(value, dict):
        return {key: _substitute(entry, item) for key, entry in value.items()}
    return value


def test_refactoring_literal_steps_into_an_equivalent_for_each_keeps_the_hash(tmp_path):
    """Hashing the EXPANSION, not the YAML: a pure refactor must not force a rebuild."""
    grouped = _fresh(provision=_autopsy_provision(['4.4.0', '4.4.1']))

    literal = yaml.safe_load(yaml.dump(grouped))
    group = literal['recipe']['provision'][1]
    unrolled = []
    for version in ['4.4.0', '4.4.1']:
        for step in group['steps']:
            rendered = _substitute(step, version)
            rendered['description'] = f'Autopsy {version}'
            unrolled.append(rendered)
    literal['recipe']['provision'] = [literal['recipe']['provision'][0]] + unrolled

    assert _hash(literal, tmp_path)[0] == _hash(grouped, tmp_path)[0]


def test_reordering_for_each_changes_the_hash(tmp_path):
    """Install order is a build input: 4.4.0-then-4.4.1 is not 4.4.1-then-4.4.0."""
    forward, _ = _hash(_fresh(provision=_autopsy_provision(['4.4.0', '4.4.1'])), tmp_path)
    reverse, _ = _hash(_fresh(provision=_autopsy_provision(['4.4.1', '4.4.0'])), tmp_path)
    assert forward != reverse


def test_adding_a_for_each_item_changes_the_hash(tmp_path):
    small, _ = _hash(_fresh(provision=_autopsy_provision(['4.4.0'])), tmp_path)
    large, _ = _hash(_fresh(provision=_autopsy_provision(['4.4.0', '4.4.1'])), tmp_path)
    assert small != large


def test_editing_a_description_does_not_change_the_hash(tmp_path):
    """Prose cannot affect the disk; a typo must not cost a multi-hour rebuild."""
    original = _fresh(provision=_autopsy_provision(['4.4.0']))
    edited = yaml.safe_load(yaml.dump(original))
    edited['recipe']['provision'][1]['description'] = 'Autopsy {{ item }} — typo fixed'
    assert _hash(edited, tmp_path)[0] == _hash(original, tmp_path)[0]


def test_editing_log_files_does_not_change_the_hash(tmp_path):
    original = _fresh(provision=_autopsy_provision(['4.4.0']))
    edited = yaml.safe_load(yaml.dump(original))
    edited['recipe']['provision'][1]['steps'][1]['log_files'] = ['C:\\other.log']
    assert _hash(edited, tmp_path)[0] == _hash(original, tmp_path)[0]


def test_editing_allow_exit_codes_does_change_the_hash(tmp_path):
    original = _fresh(provision=_autopsy_provision(['4.4.0']))
    edited = yaml.safe_load(yaml.dump(original))
    edited['recipe']['provision'][1]['steps'][1]['allow_exit_codes'] = [0]
    assert _hash(edited, tmp_path)[0] != _hash(original, tmp_path)[0]


# --- T6: ISO identity ---

def test_uppercase_iso_sha256_hashes_identically_after_normalization(tmp_path):
    """Letter case must not fork identity.

    Before `normalized_iso_sha256`, an uppercase digest produced a DIFFERENT recipe
    hash and an environment that could never build (`verify_iso_hash` compares
    case-sensitively). This test is that fix's proof.
    """
    upper = _fresh(iso_sha256=_WIN11ARM64_FRESH['recipe']['iso_sha256'].upper())
    assert _hash(upper, tmp_path)[0] == GOLDEN_RECIPE_HASH


def test_whitespace_around_iso_sha256_is_normalized(tmp_path):
    padded = _fresh(iso_sha256=f"  {_WIN11ARM64_FRESH['recipe']['iso_sha256']}\n")
    assert _hash(padded, tmp_path)[0] == GOLDEN_RECIPE_HASH


def test_changing_the_iso_path_does_not_change_the_hash(tmp_path):
    """Where the ISO lives is not a build input — only which bytes it has."""
    moved = _fresh(iso='/somewhere/else/Win11.iso')
    assert _hash(moved, tmp_path)[0] == GOLDEN_RECIPE_HASH


def test_byo_form_is_hash_neutral(tmp_path):
    """A BYO env over the same ISO bytes is a build-cache HIT off the URL-form build.

    Intended: `iso_name` / `iso_notes` are excluded from the identity, so converting
    an environment with `adare env recipe-byo` does not orphan its built disk.
    """
    byo = yaml.safe_load(yaml.dump(_WIN11ARM64_FRESH))
    byo['recipe'].pop('iso')
    byo['recipe']['iso_name'] = 'Win11_25H2_English_Arm64_v2.iso'
    byo['recipe']['iso_notes'] = 'Download from microsoft.com/software-download/windows11'
    assert _hash(byo, tmp_path)[0] == GOLDEN_RECIPE_HASH


def test_changing_iso_sha256_changes_the_hash(tmp_path):
    changed = _fresh(iso_sha256='0' * 64)
    assert _hash(changed, tmp_path)[0] != GOLDEN_RECIPE_HASH


@pytest.mark.parametrize('params', [
    {'setup_level': 1, 'disk_size': '120G'},
    {'setup_level': 2, 'disk_size': '160G'},
    {'setup_level': 2, 'disk_size': '120G', 'ram_mb': 8192},
    {'setup_level': 2, 'disk_size': '120G', 'cpus': 4},
])
def test_changing_any_build_param_changes_the_hash(tmp_path, params):
    assert _hash(_fresh(params=params), tmp_path)[0] != GOLDEN_RECIPE_HASH


def test_changing_the_template_changes_the_hash(tmp_path):
    """A different answer file is a different install procedure."""
    other = _fresh(template='autounattend_win11.xml')
    assert _hash(other, tmp_path)[0] != GOLDEN_RECIPE_HASH


def test_adding_a_postsetupinstallation_changes_the_hash(tmp_path):
    """`postsetupinstallations` keeps its previous meaning AND its hash contribution."""
    env = yaml.safe_load(yaml.dump(_WIN11ARM64_FRESH))
    env['postsetupinstallations'] = [{'name': 'tool', 'command': 'install-tool'}]
    assert _hash(env, tmp_path)[0] != GOLDEN_RECIPE_HASH


def test_provision_and_postsetupinstallations_are_independent_inputs(tmp_path):
    """Same command as a build-time step vs. a per-run step => different identities."""
    as_provision = _fresh(provision=[{'name': 'tool', 'command': 'install-tool'}])
    as_postsetup = yaml.safe_load(yaml.dump(_WIN11ARM64_FRESH))
    as_postsetup['postsetupinstallations'] = [{'name': 'tool', 'command': 'install-tool'}]
    assert _hash(as_provision, tmp_path)[0] != _hash(as_postsetup, tmp_path)[0]
