"""Vision-LLM GUI automation: autonomous agent, playbook recorder, replay.

The agent (:class:`GuiAgent`) drives a running VM's GUI toward a natural-language
goal and records a reusable ADARE :class:`~adare.types.playbook.Playbook`. The
generated playbook then replays deterministically through the existing CV/OCR
engine (:func:`run_playbook`) with no LLM, falling back to the agent only to
self-heal a stale target. See the GUI-automated installation guide.
"""

from __future__ import annotations

from .agent import AgentRunResult, GuiAgent
from .client import VLMClient
from .exceptions import AgentError, PlaybookRecordingError, VLMError
from .mcp_server import GuiMcpServer
from .recorder import PlaybookRecorder
from .replay import ReplayResult, run_playbook
from .verify import CheckResult, run_acceptance_checks

__all__ = [
    'AgentError',
    'AgentRunResult',
    'CheckResult',
    'GuiAgent',
    'GuiMcpServer',
    'PlaybookRecorder',
    'PlaybookRecordingError',
    'ReplayResult',
    'VLMClient',
    'VLMError',
    'run_acceptance_checks',
    'run_playbook',
]
