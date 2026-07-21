from types import SimpleNamespace

import click


def register(cli, AliasedGroup, exec_with_error_printing):
    """Register `adare vlm` commands (GUI-automation vision-LLM provider config)."""

    @cli.group(name='vlm', cls=AliasedGroup)
    def vlm():
        """Configure the GUI-automation vision-LLM (used by `dev agent`/`record`/`author`)."""
        pass

    @vlm.command()
    @click.argument('provider', type=click.Choice(['ollama-cloud', 'local']))
    @click.option('--api-key', default=None,
                  help='Ollama Cloud API key (from ollama.com/settings/keys). '
                       'Prompted for if omitted.')
    @click.option('--base-url', default=None,
                  help='Override the preset endpoint URL.')
    @click.option('--model', default=None,
                  help='Override the preset model id.')
    def use(provider, api_key, base_url, model):
        """Persist a VLM provider to ~/.adare/config.json (chmod 600).

        Presets (override with --base-url / --model):
          ollama-cloud  https://ollama.com/v1  qwen3-vl:235b-cloud  (coords: normalized_1000)
          local         http://localhost:8000/v1  Qwen/Qwen2-VL-7B-Instruct  (coords: absolute)

        An env var (ADARE_VLLM_*) still overrides the saved config for a single run.

        Examples:
            adare vlm use ollama-cloud --api-key <key>
            adare vlm use ollama-cloud            # prompts for the key
            adare vlm use local
        """
        if provider == 'ollama-cloud' and not api_key:
            api_key = click.prompt('Ollama Cloud API key', hide_input=True, default='',
                                   show_default=False)
        from adare.cli.vlm import exec_vlm_use
        args = SimpleNamespace(provider=provider, api_key=api_key or None,
                               base_url=base_url, model=model)
        exec_with_error_printing(exec_vlm_use, args)

    @vlm.command()
    def show():
        """Show the resolved VLM config and where each value comes from."""
        from adare.cli.vlm import exec_vlm_show
        exec_with_error_printing(exec_vlm_show, SimpleNamespace())
