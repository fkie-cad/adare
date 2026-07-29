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
from .planning_agent import Plan, PlanningAgent, PlanStep
from .progress import AgentProgressReporter
from .recorder import PlaybookRecorder
from .replay import ReplayResult, run_playbook
from .text_author import TextAuthorDriver, parse_authored_line
from .verify import CheckResult, run_acceptance_checks

__all__ = [
    'AgentError',
    'AgentProgressReporter',
    'AgentRunResult',
    'CheckResult',
    'GuiAgent',
    'GuiMcpServer',
    'Plan',
    'PlanStep',
    'PlanningAgent',
    'PlaybookRecorder',
    'PlaybookRecordingError',
    'ReplayResult',
    'TextAuthorDriver',
    'VLMClient',
    'VLMError',
    'parse_authored_line',
    'run_acceptance_checks',
    'run_playbook',
]
