from types import SimpleNamespace

import click


def register(cli, AliasedGroup, exec_with_error_printing):
    """Register `adare vlm` commands (GUI-automation vision-LLM provider config)."""

    @cli.group(name='vlm', cls=AliasedGroup)
    def vlm():
        """Configure the GUI-automation vision-LLM (used by `dev agent`/`record`/`author`)."""
        pass

    @vlm.command()
    @click.argument('target', required=False)
    @click.option('--api-key', default=None,
                  help='Ollama Cloud API key (from ollama.com/settings/keys), when '
                       'creating from the ollama-cloud preset.')
    @click.option('--base-url', default=None, help='Override the preset endpoint URL.')
    @click.option('--model', default=None, help='Override the preset model id.')
    @click.option('--name', default=None,
                  help='Name for the profile created from a preset (default: cloud/local).')
    @click.option('--no-verify', is_flag=True,
                  help='Skip the live endpoint/token check when creating a keyed profile.')
    def use(target, api_key, base_url, model, name, no_verify):
        """Switch VLM profile — interactively, by name, or from a preset.

        With no TARGET, shows a numbered menu of saved profiles (active marked)
        plus "+ new" entries. TARGET may be an existing profile name to activate,
        or a preset keyword to create+activate a new profile:

          ollama-cloud  https://ollama.com/v1  gemma4:31b  (normalized_1000)
          local         http://localhost:8000/v1  Qwen/Qwen2-VL-7B-Instruct  (absolute)

        An env var (ADARE_VLLM_*) still overrides the active profile for one run.

        Examples:
            adare vlm use                                  # interactive picker
            adare vlm use cloud-235b                       # activate a saved profile
            adare vlm use ollama-cloud --api-key <key>     # create + activate
            adare vlm use ollama-cloud --name cloud-alt --model gemma4:31b --api-key <key>
        """
        from adare.cli.vlm import exec_vlm_use
        args = SimpleNamespace(target=target, api_key=api_key or None,
                               base_url=base_url, model=model, name=name, no_verify=no_verify)
        exec_with_error_printing(exec_vlm_use, args)

    @vlm.command()
    @click.option('--no-verify', is_flag=True,
                  help='Skip the live endpoint/token check for a keyed profile.')
    def create(no_verify):
        """Create a profile with a guided menu (provider, model, key, ...).

        Walks through: provider (Ollama Cloud / local / custom OpenAI-compatible)
        -> endpoint URL -> model (pick-list or custom) -> coordinate space
        (custom only) -> API key -> profile name. Saves and activates it, then
        live-checks the endpoint + token for keyed providers (--no-verify skips).
        """
        from adare.cli.vlm import exec_vlm_create
        exec_with_error_printing(exec_vlm_create, SimpleNamespace(no_verify=no_verify))

    @vlm.command(name='list')
    def list_():
        """List saved VLM profiles (active one marked)."""
        from adare.cli.vlm import exec_vlm_list
        exec_with_error_printing(exec_vlm_list, SimpleNamespace())

    @vlm.command()
    @click.argument('name')
    @click.option('--no-activate', is_flag=True,
                  help='Save the profile without making it active.')
    def save(name, no_activate):
        """Snapshot the currently-effective config as profile NAME."""
        from adare.cli.vlm import exec_vlm_save
        exec_with_error_printing(exec_vlm_save, SimpleNamespace(name=name, no_activate=no_activate))

    @vlm.command(name='rm')
    @click.argument('name')
    def rm(name):
        """Delete the profile NAME."""
        from adare.cli.vlm import exec_vlm_remove
        exec_with_error_printing(exec_vlm_remove, SimpleNamespace(name=name))

    @vlm.command()
    def show():
        """Show the resolved VLM config and where each value comes from."""
        from adare.cli.vlm import exec_vlm_show
        exec_with_error_printing(exec_vlm_show, SimpleNamespace())

    # Convenience aliases.
    vlm.add_alias('ls', 'list')
    vlm.add_alias('remove', 'rm')
