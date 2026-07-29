"""Exceptions for the GUI-automation vision-LLM engine."""

from __future__ import annotations


class VLMError(Exception):
    """A vLLM request failed or returned an unusable response."""


class AgentError(Exception):
    """The GUI agent could not complete its goal (budget tripped, stalled, etc.)."""


class PlaybookRecordingError(Exception):
    """The recorder could not produce a valid playbook artifact."""
