"""LLM-authored UI-action playbook harness.

See ``FLOW.md`` for the end-to-end flow. Public entry points:

- :func:`author` — call an Ollama Cloud model with a screenshot, get playbook YAML.
- :func:`validate` — parse authored YAML via ADARE's ``parse_playbook``.
- :func:`author_verify_repair_loop` — author -> validate -> replay -> repair.
- :func:`boot_session` / :func:`screenshot` / :func:`replay` — live dev-CLI steps.
"""

from .author_playbook import (
    AuthoringError,
    AuthoringOutcome,
    OllamaError,
    PromptTemplate,
    RoundResult,
    author,
    author_verify_repair_loop,
    boot_session,
    extract_schema,
    extract_yaml,
    replay,
    screenshot,
    validate,
)

__all__ = [
    'AuthoringError',
    'AuthoringOutcome',
    'OllamaError',
    'PromptTemplate',
    'RoundResult',
    'author',
    'author_verify_repair_loop',
    'boot_session',
    'extract_schema',
    'extract_yaml',
    'replay',
    'screenshot',
    'validate',
]
