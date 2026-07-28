"""Build-time provisioning: expand, validate, and hash ``recipe.provision``.

Pure module by design — it imports no QEMU code and touches no filesystem, so it
is the primary seam for testing the provisioning contract without booting a VM.
Everything that actually talks to a guest lives in
:mod:`adare.hypervisor.qemu.vm_creator.provision_creator`.

Three jobs:

* :func:`expand_provision` — turn the declared ``list[ProvisionStep]`` (single
  commands and ``for_each`` groups) into the flat, ordered
  ``list[ProvisionCommand]`` that will actually be executed, with ``{{ item }}``
  rendered and ``shell: auto`` resolved.
* :func:`resolve_shell` — decide the concrete interpreter for a guest platform.
* :func:`provision_identity` — project the expanded list into the dicts folded
  into the recipe hash.

Hashing the **expanded** list rather than the YAML is deliberate: refactoring 16
literal steps into a ``for_each`` that expands identically must NOT invalidate a
cached disk, while reordering the items must.
"""

import logging

import attrs
from jinja2 import Environment as JinjaEnvironment
from jinja2 import StrictUndefined, TemplateError

from adare.types.environment import ProvisionCommand, ProvisionStep

log = logging.getLogger(__name__)

# Fields rendered through the per-item template. `description` is included for
# operator legibility even though it is excluded from the hash.
_TEMPLATED_FIELDS = ('name', 'description', 'command', 'verify', 'cwd')

# StrictUndefined is a correctness requirement, not a preference. With Jinja's
# default Undefined, a typo like `{{ version }}` instead of `{{ item }}` renders
# to the empty string and produces a plausible-but-wrong disk — e.g. a download
# URL missing its version segment, installed under a directory named
# "Autopsy-". A silently wrong 51 GB disk is the one failure mode the recipe
# model cannot tolerate, so an unknown variable is a hard error.
_JINJA = JinjaEnvironment(undefined=StrictUndefined, autoescape=False)

_SHELLS_BY_PLATFORM = {
    'windows': frozenset({'powershell', 'cmd'}),
    'linux': frozenset({'bash'}),
}


class ProvisionSchemaError(ValueError):
    """A ``recipe.provision`` block is malformed or cannot be expanded.

    Raised *before* any disk build starts, so a schema mistake never costs a
    multi-hour Windows install.
    """


def resolve_shell(shell: str, platform: str) -> str:
    """Resolve a declared ``shell`` to a concrete interpreter for *platform*.

    ``auto`` → ``powershell`` on Windows, ``bash`` elsewhere. An explicit shell
    that the guest platform cannot run is an error rather than a silent
    substitution: ``shell: cmd`` on Linux means the author had a different guest
    in mind, and quietly running the text through bash would be worse than
    failing.

    Raises:
        ProvisionSchemaError: If *shell* is not available on *platform*.
    """
    # Platform is validated BEFORE the `auto` shortcut: otherwise an unsupported
    # platform silently resolves `auto` to bash and the failure surfaces much
    # later, as a guest-exec error, on a platform provisioning cannot serve at all.
    allowed = _SHELLS_BY_PLATFORM.get(platform)
    if allowed is None:
        raise ProvisionSchemaError(
            f"build-time provisioning is not supported for platform {platform!r}"
        )
    if shell == 'auto':
        return 'powershell' if platform == 'windows' else 'bash'
    if shell not in allowed:
        raise ProvisionSchemaError(
            f"shell {shell!r} is not available on a {platform!r} guest "
            f"(available: {', '.join(sorted(allowed))})"
        )
    return shell


def _render(template_text: str, item: str, *, step_name: str, field: str) -> str:
    """Render one template field for one ``for_each`` item.

    Raises:
        ProvisionSchemaError: On any Jinja error, naming the step and the field so
            the author does not have to guess which of six strings was wrong.
    """
    try:
        return _JINJA.from_string(template_text).render(item=item)
    except TemplateError as e:
        raise ProvisionSchemaError(
            f"provision step {step_name!r}: could not render {field!r} for "
            f"item {item!r}: {e}. Only {{{{ item }}}} is available inside a "
            f"for_each group."
        ) from e


def _render_command(command: ProvisionCommand, item: str | None,
                    platform: str) -> ProvisionCommand:
    """Return a copy of *command* with templates rendered and shell resolved.

    With ``item is None`` (no ``for_each``) nothing is templated — a literal
    ``{{`` in a command must survive untouched when there is no item to
    substitute.
    """
    values = {}
    if item is not None:
        # Render `name` first and report every later failure against the RENDERED
        # name: an error naming 'autopsy-{{ item }}-install' makes the operator
        # work out which of 16 iterations failed, while 'autopsy-4.12.0-install'
        # says it outright.
        label = _render(command.name, item, step_name=command.name, field='name')
        values['name'] = label
        for field in _TEMPLATED_FIELDS:
            if field == 'name':
                continue
            text = getattr(command, field)
            if text:
                values[field] = _render(text, item, step_name=label, field=field)
        if command.log_files:
            values['log_files'] = [
                _render(path, item, step_name=label, field='log_files')
                for path in command.log_files
            ]

    values['shell'] = resolve_shell(command.shell, platform)
    return ProvisionCommand(
        name=values.get('name', command.name),
        command=values.get('command', command.command),
        description=values.get('description', command.description),
        cwd=values.get('cwd', command.cwd),
        shell=values['shell'],
        allow_exit_codes=list(command.allow_exit_codes),
        verify=values.get('verify', command.verify),
        log_files=values.get('log_files', list(command.log_files)),
        timeout_minutes=command.timeout_minutes,
        reboot=command.reboot,
    )


def _step_commands(step: ProvisionStep) -> list[ProvisionCommand]:
    """Normalize a step to its command list (single-command shorthand → one item).

    ``ProvisionStep`` mirrors the YAML faithfully — it never rewrites its own
    fields — so the shorthand is unfolded here instead, giving every downstream
    caller exactly one shape to handle.

    A nested command with no ``description`` of its own inherits the group's. In
    practice the description belongs on the group ("Autopsy {{ item }}") while the
    individual steps are mechanical (download / install / cleanup), so without
    this the progress line for every nested step would be blank.
    """
    if step.steps:
        if not step.description:
            return list(step.steps)
        return [
            command if command.description
            else attrs.evolve(command, description=step.description)
            for command in step.steps
        ]
    return [ProvisionCommand(
        name=step.name,
        command=step.command,
        description=step.description,
        cwd=step.cwd,
        shell=step.shell,
        allow_exit_codes=list(step.allow_exit_codes),
        verify=step.verify,
        log_files=list(step.log_files),
        timeout_minutes=step.timeout_minutes,
        reboot=step.reboot,
    )]


def expand_provision(steps: list[ProvisionStep], platform: str) -> list[ProvisionCommand]:
    """Expand declared provision steps into the flat ordered execution list.

    Group ordering is *group-major*: a ``for_each`` group replays all of its
    ``steps`` for item 1, then all of them for item 2, and so on — so a
    download/install/cleanup triple stays adjacent per item and the temp file is
    gone before the next download starts.

    Args:
        steps: The declared ``recipe.provision`` list.
        platform: Guest platform (``'windows'`` / ``'linux'``), used to resolve
            ``shell: auto`` and to reject an impossible explicit shell.

    Returns:
        Flat list of :class:`ProvisionCommand` with every template rendered and
        every ``shell`` a concrete interpreter (never ``'auto'``).

    Raises:
        ProvisionSchemaError: On a render failure, an impossible shell, an empty
            command, or a duplicate expanded name.
    """
    expanded: list[ProvisionCommand] = []
    for step in steps:
        commands = _step_commands(step)
        items: list[str | None] = list(step.for_each) if step.for_each else [None]
        for item in items:
            for command in commands:
                rendered = _render_command(command, item, platform)
                if not rendered.command.strip():
                    raise ProvisionSchemaError(
                        f"provision step {rendered.name!r} expanded to an empty command"
                    )
                expanded.append(rendered)

    # Names are the error identity, the host-log label and the progress line, so
    # duplicates would make a failure report ambiguous about which step failed.
    # This is also the practical guard against forgetting `{{ item }}` in a
    # for_each step's `name` — 16 identical names instead of 16 distinct ones.
    seen: set[str] = set()
    for command in expanded:
        if command.name in seen:
            raise ProvisionSchemaError(
                f"duplicate provision step name after expansion: {command.name!r}. "
                f"Inside a for_each group, include {{{{ item }}}} in each step's "
                f"'name' so the expanded names stay unique."
            )
        seen.add(command.name)

    return expanded


def provision_identity(commands: list[ProvisionCommand]) -> list[dict]:
    """Project expanded commands into the dicts folded into the recipe hash.

    ``description`` and ``log_files`` are deliberately EXCLUDED: neither can
    affect the produced disk, and a typo in prose or a wrong log path must not
    cost a multi-hour rebuild. Note this is asymmetric with the ``post_install``
    projection in :func:`adare.backend.vm.recipe._recipe_identity`, which *does*
    fold ``description`` — that predates this module and changing it would move
    every existing recipe hash, forcing full rebuilds of already-built disks.

    Everything else is included, including ``timeout_minutes`` and ``reboot``:
    they change how the build runs, and a build that succeeded never needs its
    timeout retuned anyway.
    """
    return [
        {
            'name': command.name,
            'command': command.command,
            'cwd': command.cwd,
            'shell': command.shell,
            'allow_exit_codes': list(command.allow_exit_codes),
            'verify': command.verify,
            'timeout_minutes': command.timeout_minutes,
            'reboot': command.reboot,
        }
        for command in commands
    ]
