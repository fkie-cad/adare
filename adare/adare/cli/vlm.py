"""CLI handlers for `adare vlm` — configure the GUI-automation vision-LLM.

Persists the provider choice (base URL, model, coordinate space, API key) to
``~/.adare/config.json`` so ``dev agent`` / ``dev record`` / ``dev author`` and
self-heal pick it up without per-shell env vars. Environment variables still
override the saved config for a single run (see ``config/server._cfg``).
"""

import logging

from adare.config import userconfig
from adare.console import console, print_error_message, print_success_message

log = logging.getLogger(__name__)

# Env-var names are also the config-file keys (the store is flat + self-documenting).
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

# Per-provider presets applied by `vlm use` (overridable by --base-url/--model).
_PRESETS = {
    'ollama-cloud': {
        _BASE_URL: 'https://ollama.com/v1',
        _MODEL: 'qwen3-vl:235b-cloud',
        _COORD: 'normalized_1000',
    },
    'local': {
        _BASE_URL: 'http://localhost:8000/v1',
        _MODEL: 'Qwen/Qwen2-VL-7B-Instruct',
        _COORD: 'absolute',
    },
}


def exec_vlm_use(arguments):
    """Persist a VLM provider preset to ~/.adare/config.json (chmod 600)."""
    provider = getattr(arguments, 'provider', None)
    preset = _PRESETS.get(provider)
    if preset is None:
        print_error_message(
            title=f"Unknown provider: {provider}",
            next_steps=[f'Choose one of: {", ".join(sorted(_PRESETS))}'],
        )
        exit(1)

    base_url = getattr(arguments, 'base_url', None) or preset[_BASE_URL]
    model = getattr(arguments, 'model', None) or preset[_MODEL]
    values = {_BASE_URL: base_url, _MODEL: model, _COORD: preset[_COORD]}

    if provider == 'ollama-cloud':
        api_key = getattr(arguments, 'api_key', None)
        if not api_key:
            print_error_message(
                title='Ollama Cloud needs an API key',
                next_steps=['Pass it: adare vlm use ollama-cloud --api-key <key>',
                            'Get one at https://ollama.com/settings/keys'],
            )
            exit(1)
        values[_API_KEY] = api_key
        userconfig.set_values(values)
    else:  # local — no key needed; drop any saved one
        userconfig.set_values(values)
        userconfig.unset([_API_KEY])

    print_success_message(
        title=f'VLM provider set to {provider}',
        location=str(userconfig.path()),
        next_steps=[f'Model: {model}  ({base_url}, coords: {preset[_COORD]})',
                    'Verify the endpoint: adare vm gui-doctor',
                    'Inspect the resolved config: adare vlm show'],
    )


def exec_vlm_show(arguments):
    """Print the resolved VLM config with each value's source."""
    from rich.table import Table

    table = Table(title='Resolved VLM configuration', title_style='bold', show_lines=False)
    table.add_column('Setting', style='cyan', no_wrap=True)
    table.add_column('Value')
    table.add_column('Source', style='dim')

    for name in (_BASE_URL, _MODEL, _COORD, _API_KEY):
        value, source = _resolved(name)
        shown = _mask(value) if name == _API_KEY else value
        table.add_row(name, shown, source)

    console.print(table)
    console.print(f'Config file: {userconfig.path()}', style='dim')


def _resolved(name):
    """Return (value, source) for a key: env > config-file > default.

    Mirrors config/server._cfg's ``or`` semantics — an empty string falls through
    to the next source — so the reported source matches what the app actually uses.
    """
    import os
    if os.environ.get(name):
        return os.environ[name], 'env'
    file_value = userconfig.get(name)
    if file_value:
        return file_value, 'config-file'
    return _DEFAULTS[name], 'default'


def _mask(value):
    """Mask a secret, revealing only the last 4 characters."""
    if not value or value == 'EMPTY':
        return '(none)'
    if len(value) <= 4:
        return '****'
    return '****' + value[-4:]
