"""CLI handlers for `adare vlm` — configure the GUI-automation vision-LLM.

Stores named profiles (base URL, model, coordinate space, API key) in
``~/.adare/config.json`` so ``dev agent`` / ``dev record`` / ``dev author`` and
self-heal pick up the active one without per-shell env vars. Swap profiles
interactively (`adare vlm use`) or by name (`adare vlm use <name>`). Environment
variables still override the active profile for a single run (see
``config/server._cfg``).
"""

import logging

import click

from adare.config import userconfig
from adare.console import console, print_error_message, print_success_message

log = logging.getLogger(__name__)

# Env-var names are also the profile keys (the store is flat + self-documenting).
_BASE_URL = 'ADARE_VLLM_BASE_URL'
_MODEL = 'ADARE_VLLM_MODEL'
_API_KEY = 'ADARE_VLLM_API_KEY'
_COORD = 'ADARE_VLLM_COORD_SPACE'

# Code defaults — kept in sync with config/server.py so `vlm show` reports the
# same values the app resolves when nothing is configured.
_DEFAULTS = {
    _BASE_URL: 'http://localhost:8000/v1',
    _MODEL: 'Qwen/Qwen2-VL-7B-Instruct',
    _API_KEY: 'EMPTY',
    _COORD: 'absolute',
}

# Per-provider presets applied when creating a profile (overridable by flags).
_PRESETS = {
    'ollama-cloud': {
        _BASE_URL: 'https://ollama.com/v1',
        _MODEL: 'qwen3-vl:235b-cloud',
        _COORD: 'normalized_1000',
        'needs_key': True,
    },
    'local': {
        _BASE_URL: 'http://localhost:8000/v1',
        _MODEL: 'Qwen/Qwen2-VL-7B-Instruct',
        _COORD: 'absolute',
        'needs_key': False,
    },
}

# Providers offered by the `create` wizard, in menu order: (key, label).
_PROVIDERS = [
    ('ollama-cloud', 'Ollama Cloud'),
    ('local', 'Local (self-hosted vLLM / OpenAI-compatible)'),
    ('custom', 'Custom (any OpenAI-compatible endpoint)'),
]

# Known-good models offered per provider in the wizard's model step (a final
# "custom" entry always lets the user type their own).
_MODEL_SUGGESTIONS = {
    'ollama-cloud': ['qwen3-vl:235b-cloud', 'qwen3-vl:32b-cloud'],
    'local': ['Qwen/Qwen2-VL-7B-Instruct', 'Qwen/Qwen2-VL-72B-Instruct'],
    'custom': [],
}

# Coordinate spaces (matches config/server.py's VLLM_COORD_SPACE options).
_COORDS = [
    ('absolute', 'absolute — raw pixels of the image shown'),
    ('normalized_1000', 'normalized_1000 — 0..1000 on both axes (e.g. Qwen3-VL)'),
]


# ── use ──────────────────────────────────────────────────────────────────────

def exec_vlm_use(arguments):
    """Activate a profile, or create one from a provider preset.

    ``arguments.target`` may be an existing profile name, a preset keyword
    (``ollama-cloud`` / ``local``), or ``None`` for the interactive picker.
    """
    target = getattr(arguments, 'target', None)
    if target is None:
        _interactive_use()
        return
    if target in _PRESETS:
        _create_from_preset(target, arguments)
        return
    if userconfig.get_profile(target) is not None:
        userconfig.set_active(target)
        _activated_message(target)
        return
    print_error_message(
        title=f"No profile or provider named '{target}'",
        next_steps=['Pick interactively: adare vlm use',
                    'List profiles: adare vlm list',
                    f'Create one: adare vlm use ollama-cloud|local --name {target}'],
    )
    exit(1)


def _create_from_preset(provider, arguments):
    """Build a profile from a preset (+flag overrides) and activate it."""
    preset = _PRESETS[provider]
    values = {
        _BASE_URL: getattr(arguments, 'base_url', None) or preset[_BASE_URL],
        _MODEL: getattr(arguments, 'model', None) or preset[_MODEL],
        _COORD: preset[_COORD],
    }
    if preset['needs_key']:
        api_key = getattr(arguments, 'api_key', None)
        if not api_key:
            print_error_message(
                title=f'{provider} needs an API key',
                next_steps=[f'Pass it: adare vlm use {provider} --api-key <key>',
                            'Or run `adare vlm use` and pick "new" to be prompted',
                            'Get one at https://ollama.com/settings/keys'],
            )
            exit(1)
        values[_API_KEY] = api_key

    name = getattr(arguments, 'name', None) or _default_profile_name(provider)
    userconfig.set_profile(name, values, activate=True)
    _activated_message(name, created=True)
    _maybe_verify(values, getattr(arguments, 'no_verify', False))


def _interactive_use():
    """Numbered menu: pick a saved profile to activate, or create a new one."""
    existing = userconfig.profiles()
    active = userconfig.active_name()

    console.print('[bold]Select a VLM profile:[/bold]')
    ordered = sorted(existing)
    for i, name in enumerate(ordered, start=1):
        mark = '  [green](active)[/green]' if name == active else ''
        console.print(f'  [cyan]{i}[/cyan]) {name}{mark}   [dim]{_summary(existing[name])}[/dim]')
    create_idx = len(ordered) + 1
    if ordered:
        console.print('  [dim]---[/dim]')
    console.print(f'  [cyan]{create_idx}[/cyan]) [green]+ create new profile (guided)[/green]')

    choice = click.prompt('>', type=click.IntRange(1, create_idx))
    if choice <= len(ordered):
        name = ordered[choice - 1]
        userconfig.set_active(name)
        _activated_message(name)
        return
    _wizard()


# ── create (guided wizard) ────────────────────────────────────────────────────

def exec_vlm_create(arguments):
    """Guided wizard: provider -> endpoint -> model -> coords -> key -> name."""
    _wizard(skip_verify=getattr(arguments, 'no_verify', False))


def _wizard(skip_verify=False):
    """Walk the user through building and activating a profile."""
    provider = _select_provider()
    base_url = _prompt_base_url(provider)
    model = _prompt_model(provider)
    coord = _prompt_coord(provider)
    api_key = _prompt_key(provider)

    default_name = _default_profile_name(provider)
    name = click.prompt('Profile name', default=default_name).strip() or default_name

    values = {_BASE_URL: base_url, _MODEL: model, _COORD: coord}
    if api_key:
        values[_API_KEY] = api_key
    userconfig.set_profile(name, values, activate=True)
    _activated_message(name, created=True)
    _maybe_verify(values, skip_verify)


def _select_provider():
    """Step 1 — pick a provider from the numbered menu."""
    choice = _menu('Provider:', [label for _, label in _PROVIDERS])
    return _PROVIDERS[choice - 1][0]


def _prompt_base_url(provider):
    """Step 2 — endpoint URL, pre-filled from the preset (required for custom)."""
    default = _PRESETS.get(provider, {}).get(_BASE_URL, 'http://localhost:8000/v1')
    return click.prompt('Base URL', default=default).strip() or default


def _prompt_model(provider):
    """Step 3 — pick a known model or type a custom one."""
    suggestions = _MODEL_SUGGESTIONS.get(provider, [])
    if not suggestions:
        default = _PRESETS.get(provider, {}).get(_MODEL, _DEFAULTS[_MODEL])
        return click.prompt('Model id', default=default).strip() or default
    choice = _menu('Model:', suggestions + ['custom — type your own'])
    if choice <= len(suggestions):
        return suggestions[choice - 1]
    return click.prompt('Model id').strip()


def _prompt_coord(provider):
    """Step 4 — coordinate space (asked only for custom; preset otherwise)."""
    if provider != 'custom':
        return _PRESETS[provider][_COORD]
    choice = _menu('Coordinate space the model returns clicks in:',
                   [label for _, label in _COORDS])
    return _COORDS[choice - 1][0]


def _prompt_key(provider):
    """Step 5 — API key: required for cloud, optional for custom, none for local."""
    if provider == 'ollama-cloud':
        key = click.prompt('Ollama Cloud API key (ollama.com/settings/keys)',
                           hide_input=True, default='', show_default=False).strip()
        if not key:
            print_error_message(
                title='No API key entered',
                next_steps=['Run `adare vlm create` again and paste the key',
                            'Get one at https://ollama.com/settings/keys'],
            )
            exit(1)
        return key
    if provider == 'custom':
        return click.prompt('API key (leave blank for none)', hide_input=True,
                            default='', show_default=False).strip() or None
    return None


def _menu(title, labels):
    """Print a numbered menu and return the chosen 1-based index."""
    console.print(f'[bold]{title}[/bold]')
    for i, label in enumerate(labels, start=1):
        console.print(f'  [cyan]{i}[/cyan]) {label}')
    return click.prompt('>', type=click.IntRange(1, len(labels)))


# ── list / save / rm / show ──────────────────────────────────────────────────

def exec_vlm_list(arguments):
    """List saved profiles, marking the active one."""
    from rich.table import Table

    existing = userconfig.profiles()
    if not existing:
        print_success_message(
            title='No VLM profiles yet',
            next_steps=['Create one with the guided wizard: adare vlm create',
                        'Or quickly: adare vlm use ollama-cloud --api-key <key>'],
        )
        return
    active = userconfig.active_name()
    table = Table(title='VLM profiles', title_style='bold')
    table.add_column('', style='green', no_wrap=True)
    table.add_column('Profile', style='cyan', no_wrap=True)
    table.add_column('Model')
    table.add_column('Endpoint')
    table.add_column('Key', style='dim')
    for name in sorted(existing):
        values = existing[name]
        table.add_row(
            '✓' if name == active else '',
            name,
            values.get(_MODEL, _DEFAULTS[_MODEL]),
            values.get(_BASE_URL, _DEFAULTS[_BASE_URL]),
            _mask(values.get(_API_KEY)),
        )
    console.print(table)
    console.print(f'Config file: {userconfig.path()}', style='dim')


def exec_vlm_save(arguments):
    """Snapshot the currently-effective config as a named profile."""
    name = getattr(arguments, 'name', None)
    if not name:
        print_error_message(title='A profile name is required',
                            next_steps=['adare vlm save <name>'])
        exit(1)
    values = {key: _resolved(key)[0] for key in (_BASE_URL, _MODEL, _COORD, _API_KEY)}
    # Do not persist the placeholder key.
    if values.get(_API_KEY) in (None, '', 'EMPTY'):
        values.pop(_API_KEY, None)
    activate = not getattr(arguments, 'no_activate', False)
    userconfig.set_profile(name, values, activate=activate)
    print_success_message(
        title=f"Saved current config as profile '{name}'"
              + ('' if activate else ' (not activated)'),
        location=str(userconfig.path()),
        next_steps=['See all: adare vlm list'],
    )


def exec_vlm_remove(arguments):
    """Delete a named profile."""
    name = getattr(arguments, 'name', None)
    was_active = (name == userconfig.active_name())
    if not userconfig.remove_profile(name):
        print_error_message(title=f"No such profile: '{name}'",
                            next_steps=['List profiles: adare vlm list'])
        exit(1)
    next_steps = ['See all: adare vlm list']
    if was_active:
        next_steps.insert(0, 'No active profile now — VLM falls back to code defaults. '
                             'Pick one: adare vlm use')
    print_success_message(title=f"Removed profile '{name}'", next_steps=next_steps)


def exec_vlm_show(arguments):
    """Print the resolved VLM config with each value's source."""
    from rich.table import Table

    active = userconfig.active_name()
    table = Table(title=f'Resolved VLM configuration (active profile: {active or "none"})',
                  title_style='bold')
    table.add_column('Setting', style='cyan', no_wrap=True)
    table.add_column('Value')
    table.add_column('Source', style='dim')
    for name in (_BASE_URL, _MODEL, _COORD, _API_KEY):
        value, source = _resolved(name)
        shown = _mask(value) if name == _API_KEY else value
        table.add_row(name, shown, source)
    console.print(table)
    console.print(f'Config file: {userconfig.path()}', style='dim')


# ── helpers ──────────────────────────────────────────────────────────────────

def _resolved(name):
    """Return (value, source): env > active-profile > default.

    Mirrors config/server._cfg's ``or`` semantics — an empty string falls through
    to the next source — so the reported source matches what the app actually uses.
    """
    import os
    if os.environ.get(name):
        return os.environ[name], 'env'
    profile_value = userconfig.get(name)
    if profile_value:
        return profile_value, 'config-file'
    return _DEFAULTS[name], 'default'


def _summary(values):
    """One-line 'model @ host' summary of a profile for the picker."""
    model = values.get(_MODEL, _DEFAULTS[_MODEL])
    base = values.get(_BASE_URL, _DEFAULTS[_BASE_URL])
    host = base.split('://')[-1].split('/')[0]
    return f'{model} @ {host}'


def _default_profile_name(provider):
    """A memorable default name that does not collide with an existing profile."""
    existing = userconfig.profiles()
    base = {'ollama-cloud': 'cloud', 'local': 'local', 'custom': 'custom'}.get(provider, provider)
    if base not in existing:
        return base
    i = 2
    while f'{base}-{i}' in existing:
        i += 1
    return f'{base}-{i}'


def _activated_message(name, created=False):
    values = userconfig.get_profile(name) or {}
    verb = 'Created and activated' if created else 'Switched to'
    print_success_message(
        title=f"{verb} profile '{name}'",
        location=str(userconfig.path()),
        next_steps=[_summary(values),
                    'Verify the endpoint: adare vm gui-doctor',
                    'See all: adare vlm list'],
    )


def _maybe_verify(values, skip):
    """Live-check a newly configured keyed endpoint (cloud / custom-with-key).

    Non-fatal: the profile is already saved, so a failure (bad token, wrong URL,
    offline) is a warning the user can act on, not an error. Skipped for keyless
    profiles (e.g. local), which often point at a server that is not up yet.
    """
    if skip or _API_KEY not in values:
        return
    console.print('Checking endpoint and API token ...', style='dim')
    ok, message = _verify_profile(values)
    if ok is True:
        console.print(f'[green]✓ endpoint + token OK[/green] — replied {message!r}')
    elif ok is False:
        console.print(f'[yellow]⚠ could not reach the endpoint / token rejected[/yellow]: {message}')
        console.print('[yellow]  The profile was saved anyway — fix the key/URL and re-run '
                      '`adare vlm create`, or run `adare vm gui-doctor`.[/yellow]')
    else:  # None — could not run the check
        console.print(f'[dim]token check skipped: {message} '
                      '(verify later with `adare vm gui-doctor`)[/dim]')


def _verify_profile(values):
    """Return (ok, message): True/False, or None when the check cannot run.

    A tiny text completion against the configured endpoint exercises URL, model
    and Authorization in one cheap call, with a short timeout so a wrong host
    fails fast instead of hanging on the default 120s.
    """
    import asyncio

    try:
        from adare.backend.experiment.vlm.client import VLMClient
        from adare.backend.experiment.vlm.exceptions import VLMError
    except ImportError as exc:
        return None, f'vlm client unavailable ({exc})'

    client = VLMClient(
        base_url=values.get(_BASE_URL, _DEFAULTS[_BASE_URL]),
        model=values.get(_MODEL, _DEFAULTS[_MODEL]),
        api_key=values.get(_API_KEY, _DEFAULTS[_API_KEY]),
        timeout=20.0,
    )
    try:
        reply = asyncio.run(client.chat(
            [{'role': 'user', 'content': 'Reply with the single word: OK'}],
            max_tokens=5,
        ))
    except VLMError as exc:
        return False, str(exc)
    return True, reply.strip()[:40]


def _mask(value):
    """Mask a secret, revealing only the last 4 characters."""
    if not value or value == 'EMPTY':
        return '(none)'
    if len(value) <= 4:
        return '****'
    return '****' + value[-4:]
