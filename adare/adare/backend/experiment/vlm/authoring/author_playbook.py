"""LLM-authored UI-action playbook harness.

An Ollama Cloud vision model is shown a screenshot of the target machine and
asked to author a robust ADARE **UI-action** playbook (``actions:`` only, no
``tests:``) for a natural-language goal. The harness then:

  author  -> validate (parse via ``parse_playbook``) -> replay-verify -> repair

The live VM steps (boot a dev session, capture a screenshot, replay a playbook)
are isolated behind clean functions and are fully **pluggable**: the loop takes
a ``replay_cb`` (and the CLI a ``--screenshot`` injection + ``--dry-run``) so the
author->validate path can be exercised with no VM. In Phase 4 the orchestrator
supplies the real replay callback because it serializes live VM access.

Model notes: the three cloud models are reasoning models; we strip
``<think>...</think>`` and extract the first ```yaml fenced block, tolerating
extra prose. Cloud reasoning is slow, so the HTTP read timeout is generous.

Run (author + validate only, no VM):

    PYTHONPATH=<worktree>/adare uv run --project <repo> python3 \
      -m adare.backend.experiment.vlm.authoring.author_playbook \
      --goal "open the File menu" --screenshot shot.png --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from base64 import b64encode
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
DEFAULT_SCHEMA = _HERE / 'schema_spec.md'
DEFAULT_PROMPT = _HERE / 'authoring_prompt.md'

DEFAULT_MODELS = ('kimi-k2.7-code:cloud', 'minimax-m3:cloud', 'glm-5.2:cloud')
OLLAMA_HOST = 'http://localhost:11434'
OLLAMA_READ_TIMEOUT = 180.0  # cloud reasoning can take 60-180s


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class AuthoringError(Exception):
    """Raised when the model output cannot be turned into a playbook."""


class OllamaError(Exception):
    """Raised when the Ollama daemon call fails."""


# Exceptions parse_playbook / cattrs / yaml raise on a bad playbook. We catch
# these specifically (never a bare ``Exception``) so validate() can report them.
def _validation_error_types() -> tuple[type[BaseException], ...]:
    types: list[type[BaseException]] = [
        ValueError, KeyError, TypeError, AttributeError, ImportError,
    ]
    try:
        import yaml
        types.append(yaml.YAMLError)
    except ImportError:  # pragma: no cover - yaml is a hard dep of the repo
        pass
    try:
        import cattrs.errors
        types.append(cattrs.errors.BaseValidationError)
    except ImportError:  # pragma: no cover
        pass
    return tuple(types)


# --------------------------------------------------------------------------- #
# Prompt / schema loading
# --------------------------------------------------------------------------- #
def extract_schema(schema_path: str | Path = DEFAULT_SCHEMA) -> str:
    """Return the action-vocabulary spec text the model must follow."""
    return Path(schema_path).read_text()


def _parse_prompt_sections(prompt_text: str) -> dict[str, str]:
    """Split ``authoring_prompt.md`` into its ``## SECTION`` bodies."""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in prompt_text.splitlines():
        heading = re.match(r'^##\s+(.*\S)\s*$', line)
        if heading:
            if current is not None:
                sections[current] = '\n'.join(buf).strip()
            current = heading.group(1).strip().upper()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = '\n'.join(buf).strip()
    return sections


def _strip_blockquote(text: str) -> str:
    """Drop leading ``> `` markers from a markdown blockquote section."""
    out = []
    for line in text.splitlines():
        out.append(re.sub(r'^>\s?', '', line))
    return '\n'.join(out).strip()


@dataclass
class PromptTemplate:
    """The system/user/repair message templates parsed from the prompt file."""

    system: str
    user: str
    repair: str

    @classmethod
    def load(cls, prompt_path: str | Path = DEFAULT_PROMPT) -> PromptTemplate:
        sections = _parse_prompt_sections(Path(prompt_path).read_text())
        system = sections.get('SYSTEM PROMPT', '')
        user = _strip_blockquote(sections.get('USER MESSAGE (SENT ALONGSIDE THE ATTACHED SCREENSHOT)',
                                              sections.get('USER MESSAGE', '')))
        repair = _strip_blockquote(sections.get('REPAIR MESSAGE (APPENDED ON A RE-AUTHOR ROUND AFTER A FAILURE)',
                                                sections.get('REPAIR MESSAGE', '')))
        if not system:
            raise AuthoringError(f'No "## SYSTEM PROMPT" section in {prompt_path}')
        if not user:
            user = ('The attached image is the current screen (1920x1080). Author the '
                    'UI-action playbook that accomplishes the GOAL. Output only one '
                    '```yaml block.')
        if not repair:
            repair = 'Your previous playbook FAILED:\n```\n{prior_failure}\n```\nFix the cause. Output only one ```yaml block.'
        return cls(system=system, user=user, repair=repair)


# --------------------------------------------------------------------------- #
# Model output parsing
# --------------------------------------------------------------------------- #
def strip_think(text: str) -> str:
    """Remove ``<think>...</think>`` reasoning spans from model output."""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)


def extract_yaml(text: str) -> str:
    """Return the first fenced YAML block, tolerating surrounding prose."""
    cleaned = strip_think(text)
    match = re.search(r'```ya?ml\s*\n(.*?)```', cleaned, re.DOTALL | re.IGNORECASE)
    if match is None:
        match = re.search(r'```\s*\n(.*?)```', cleaned, re.DOTALL)
    if match is None:
        raise AuthoringError('No fenced YAML block found in model output')
    block = match.group(1).strip()
    if not block:
        raise AuthoringError('Fenced YAML block was empty')
    return block


# --------------------------------------------------------------------------- #
# Ollama Cloud call (localhost daemon, /api/chat)
# --------------------------------------------------------------------------- #
def build_messages(
    template: PromptTemplate,
    goal: str,
    schema: str,
    screenshot_b64: str,
    prior_failure: str | None = None,
) -> list[dict]:
    """Assemble the system + user messages (screenshot attached as image)."""
    system = template.system.replace('{schema_spec}', schema).replace('{goal}', goal)
    user_text = template.user
    if prior_failure:
        user_text = user_text + '\n\n' + template.repair.replace('{prior_failure}', prior_failure)
    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user_text, 'images': [screenshot_b64]},
    ]


def ollama_chat(
    model: str,
    messages: list[dict],
    *,
    host: str = OLLAMA_HOST,
    read_timeout: float = OLLAMA_READ_TIMEOUT,
) -> str:
    """POST to the local Ollama daemon ``/api/chat`` and return the reply text."""
    payload = json.dumps({'model': model, 'stream': False, 'messages': messages}).encode('utf-8')
    req = urllib.request.Request(
        f'{host.rstrip("/")}/api/chat',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=read_timeout) as resp:
            body = resp.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        raise OllamaError(f'Ollama HTTP {exc.code}: {exc.reason}') from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        raise OllamaError(f'Ollama request failed ({model}): {exc}') from exc

    try:
        obj = json.loads(body)
    except json.JSONDecodeError as exc:
        raise OllamaError(f'Ollama returned non-JSON: {body[:200]!r}') from exc

    if obj.get('error'):
        raise OllamaError(f'Ollama error for {model}: {obj["error"]}')
    content = (obj.get('message') or {}).get('content', '')
    if not content:
        raise OllamaError(f'Ollama returned empty content for {model}: {body[:200]!r}')
    return content


def author(
    model: str,
    goal: str,
    screenshot_b64: str,
    schema: str,
    *,
    template: PromptTemplate | None = None,
    prior_failure: str | None = None,
    host: str = OLLAMA_HOST,
    read_timeout: float = OLLAMA_READ_TIMEOUT,
) -> str:
    """Author a playbook: call the model, return the parsed ``actions:`` YAML.

    Raises :class:`OllamaError` on transport failure and :class:`AuthoringError`
    if no YAML block can be extracted from the reply.
    """
    template = template or PromptTemplate.load()
    messages = build_messages(template, goal, schema, screenshot_b64, prior_failure)
    log.info('Authoring with model=%s (repair=%s)', model, bool(prior_failure))
    reply = ollama_chat(model, messages, host=host, read_timeout=read_timeout)
    yaml_text = extract_yaml(reply)
    log.info('Model %s produced a %d-char YAML block', model, len(yaml_text))
    return yaml_text


# --------------------------------------------------------------------------- #
# Validation (parse via ADARE's parse_playbook)
# --------------------------------------------------------------------------- #
def validate(playbook_yaml: str) -> tuple[bool, str | None]:
    """Write ``playbook_yaml`` to a temp file and parse it via ADARE.

    Returns ``(True, None)`` on a clean parse, else ``(False, error_message)``.
    Import of ``parse_playbook`` is deferred so the module imports without the
    full ADARE runtime present.
    """
    from adare.types.playbook import parse_playbook

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile('w', suffix='.yml', delete=False) as handle:
            handle.write(playbook_yaml)
            tmp_path = Path(handle.name)
        parse_playbook(tmp_path)
        return True, None
    except _validation_error_types() as exc:
        return False, f'{type(exc).__name__}: {exc}'
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Live VM steps (real dev CLI) — pluggable so the loop runs without a VM
# --------------------------------------------------------------------------- #
def boot_session(
    environment: str,
    *,
    project: str | None = None,
    adare_bin: str = 'adare',
    timeout: float = 600.0,
) -> str:
    """Boot a dev session (``adare dev start -e <env>``); return its session id.

    The orchestrator normally owns the live session; this is provided for
    completeness / standalone use.
    """
    cmd = [adare_bin, 'dev', 'start', '-e', environment]
    if project:
        cmd += ['-p', project]
    log.info('Booting dev session: %s', ' '.join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    out = proc.stdout + proc.stderr
    match = re.search(r'Dev session started:\s*(\S+)', out)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f'dev start failed (rc={proc.returncode}):\n{out[-800:]}')
    session_id = match.group(1).strip()
    log.info('Dev session started: %s', session_id)
    return session_id


def screenshot(
    session_id: str | None = None,
    *,
    search_root: str | Path | None = None,
    adare_bin: str = 'adare',
    timeout: float = 120.0,
) -> str:
    """Capture the current screen (1920x1080) and return it as base64 PNG.

    There is no ``adare dev screenshot`` subcommand, so this drives the QMP
    screendump through a single-action ``screenshot`` playbook via
    ``adare dev playbook`` (the sanctioned route — ``dev action`` / ``dev state``
    are known-broken) and then reads back the newest PNG written under
    ``reporting/screenshots/`` beneath ``search_root``.

    Because the exact run directory depends on the live session, the orchestrator
    typically overrides screenshot capture with its own session-aware callback
    (it already holds the executor). This default is the standalone fallback;
    ``--screenshot <path>`` injects a screenshot instead (used for VM-less runs).
    """
    root = Path(search_root) if search_root else Path.cwd()
    existing = {p: p.stat().st_mtime for p in root.rglob('reporting/screenshots/*.png')}

    one_action = 'settings:\n  idle: 0.5\nactions:\n  - screenshot:\n      name: authoring_capture\n'
    cmd = [adare_bin, 'dev', 'playbook', '--stdin']
    if session_id:
        cmd += ['-s', session_id]
    log.info('Capturing screenshot via one-action playbook: %s', ' '.join(cmd))
    proc = subprocess.run(cmd, input=one_action, capture_output=True, text=True,
                          timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f'screenshot playbook failed (rc={proc.returncode}):\n'
                           f'{(proc.stdout + proc.stderr)[-800:]}')

    candidates = [p for p in root.rglob('reporting/screenshots/*.png')
                  if p not in existing or p.stat().st_mtime > existing[p]]
    if not candidates:
        raise RuntimeError(f'No new screenshot found under {root}/**/reporting/screenshots/')
    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    log.info('Captured screenshot: %s', newest)
    return b64encode(newest.read_bytes()).decode('ascii')


def replay(
    playbook_path: str | Path,
    *,
    session_id: str | None = None,
    restore: bool = False,
    adare_bin: str = 'adare',
    timeout: float = 1800.0,
) -> tuple[bool, str]:
    """Replay a playbook file (``adare dev playbook -f``); return (ok, output)."""
    cmd = [adare_bin, 'dev', 'playbook', '-f', str(playbook_path)]
    if session_id:
        cmd += ['-s', session_id]
    if restore:
        cmd += ['--restore']
    log.info('Replaying playbook: %s', ' '.join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    out = proc.stdout + proc.stderr
    ok = proc.returncode == 0 and 'completed with errors' not in out.lower()
    return ok, out


def load_screenshot_b64(path: str | Path) -> str:
    """Read a PNG file and return base64 with no ``data:`` prefix."""
    return b64encode(Path(path).read_bytes()).decode('ascii')


# --------------------------------------------------------------------------- #
# author -> validate -> replay-verify -> repair loop
# --------------------------------------------------------------------------- #
@dataclass
class RoundResult:
    model: str
    round: int
    valid: bool
    replayed: bool
    passing: bool
    error: str | None = None
    playbook_yaml: str | None = None


@dataclass
class AuthoringOutcome:
    """Aggregate result of the author/verify/repair loop across models."""

    rounds: list[RoundResult] = field(default_factory=list)
    best_yaml: str | None = None
    best_model: str | None = None
    best_passing: bool = False  # True if the best playbook also replayed cleanly

    @property
    def succeeded(self) -> bool:
        return self.best_yaml is not None


def author_verify_repair_loop(
    goal: str,
    models: list[str],
    rounds: int,
    screenshot_b64: str,
    schema: str,
    *,
    template: PromptTemplate | None = None,
    replay_cb=None,
    host: str = OLLAMA_HOST,
    read_timeout: float = OLLAMA_READ_TIMEOUT,
) -> AuthoringOutcome:
    """Try each model in order; per model, author -> validate -> (replay) -> repair.

    ``replay_cb(playbook_yaml) -> (ok, output)`` is the pluggable live-replay
    step. When ``None`` (the default, and the VM-less path) a playbook that
    parses is treated as the best available result; a valid **and** replayed
    playbook always outranks a merely-valid one. The orchestrator injects a
    ``replay_cb`` that writes the YAML into the experiment dir and calls
    :func:`replay` against the live session.
    """
    template = template or PromptTemplate.load()
    outcome = AuthoringOutcome()

    for model in models:
        prior_failure: str | None = None
        for rnd in range(1, rounds + 1):
            try:
                yaml_text = author(model, goal, screenshot_b64, schema,
                                   template=template, prior_failure=prior_failure,
                                   host=host, read_timeout=read_timeout)
            except (OllamaError, AuthoringError) as exc:
                log.warning('[%s round %d] author failed: %s', model, rnd, exc)
                outcome.rounds.append(RoundResult(model, rnd, False, False, False, str(exc)))
                prior_failure = f'The model call/parse failed: {exc}'
                continue

            ok, err = validate(yaml_text)
            log.info('[%s round %d] validate: %s%s', model, rnd,
                     'OK' if ok else 'FAIL', f' ({err})' if err else '')
            if not ok:
                outcome.rounds.append(RoundResult(model, rnd, False, False, False, err, yaml_text))
                prior_failure = err
                continue

            # Valid. Record as best-so-far unless a passing one already exists.
            if outcome.best_yaml is None or (not outcome.best_passing):
                outcome.best_yaml, outcome.best_model = yaml_text, model

            if replay_cb is None:
                outcome.rounds.append(RoundResult(model, rnd, True, False, False, None, yaml_text))
                break  # valid is the best we can assert without a VM; next model

            replay_ok, replay_out = replay_cb(yaml_text)
            log.info('[%s round %d] replay: %s', model, rnd, 'PASS' if replay_ok else 'FAIL')
            outcome.rounds.append(RoundResult(model, rnd, True, True, replay_ok,
                                              None if replay_ok else replay_out, yaml_text))
            if replay_ok:
                outcome.best_yaml, outcome.best_model, outcome.best_passing = yaml_text, model, True
                return outcome  # valid + passing: done
            prior_failure = replay_out

    return outcome


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='author_playbook',
        description='LLM-authored UI-action playbook harness (Ollama Cloud + ADARE).',
    )
    parser.add_argument('--goal', required=True, help='Natural-language task the playbook must accomplish')
    parser.add_argument('--models', default=','.join(DEFAULT_MODELS),
                        help='Comma-separated Ollama Cloud model tags, in preference order')
    parser.add_argument('--rounds', type=int, default=3, help='Max author/repair rounds per model')
    parser.add_argument('--schema', default=str(DEFAULT_SCHEMA), help='Path to schema_spec.md')
    parser.add_argument('--prompt', default=str(DEFAULT_PROMPT), help='Path to authoring_prompt.md')
    parser.add_argument('--screenshot', help='Inject a screenshot PNG (skips live capture)')
    parser.add_argument('--out', help='Write the best playbook YAML to this path')
    parser.add_argument('--host', default=OLLAMA_HOST, help='Ollama daemon base URL')
    parser.add_argument('--read-timeout', type=float, default=OLLAMA_READ_TIMEOUT,
                        help='HTTP read timeout for cloud reasoning (seconds)')
    # Live VM options (ignored under --dry-run)
    parser.add_argument('--environment', help='Environment to boot a dev session (--boot)')
    parser.add_argument('--project', help='Project name/path for the dev session')
    parser.add_argument('--session', help='Existing dev session id to use for capture/replay')
    parser.add_argument('--boot', action='store_true', help='Boot a dev session first')
    parser.add_argument('--replay', action='store_true', help='Verify each valid playbook by replaying it live')
    parser.add_argument('--search-root', help='Root to locate captured screenshots (default: cwd)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Skip all VM steps; requires --screenshot. Author + validate only.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Debug logging')
    return parser


def _obtain_screenshot(args) -> str:
    if args.screenshot:
        return load_screenshot_b64(args.screenshot)
    if args.dry_run:
        raise SystemExit('--dry-run requires --screenshot (no live capture in dry-run)')
    return screenshot(session_id=args.session, search_root=args.search_root)


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(levelname)s %(name)s: %(message)s',
    )

    models = [m.strip() for m in args.models.split(',') if m.strip()]
    schema = extract_schema(args.schema)
    template = PromptTemplate.load(args.prompt)

    session_id = args.session
    if args.boot and not args.dry_run:
        if not args.environment:
            raise SystemExit('--boot requires --environment')
        session_id = boot_session(args.environment, project=args.project)

    screenshot_b64 = _obtain_screenshot(args)

    replay_cb = None
    if args.replay and not args.dry_run:
        def replay_cb(playbook_yaml: str):  # noqa: E306 - small closure
            with tempfile.NamedTemporaryFile('w', suffix='.yml', delete=False) as handle:
                handle.write(playbook_yaml)
                path = handle.name
            try:
                return replay(path, session_id=session_id)
            finally:
                Path(path).unlink(missing_ok=True)

    outcome = author_verify_repair_loop(
        args.goal, models, args.rounds, screenshot_b64, schema,
        template=template, replay_cb=replay_cb,
        host=args.host, read_timeout=args.read_timeout,
    )

    print('\n=== authoring summary ===')
    for r in outcome.rounds:
        flags = f"valid={r.valid} replayed={r.replayed} passing={r.passing}"
        print(f'  {r.model} round {r.round}: {flags}'
              + (f' | {r.error}' if r.error else ''))
    print(f'best model: {outcome.best_model}  passing: {outcome.best_passing}')

    if outcome.best_yaml and args.out:
        Path(args.out).write_text(outcome.best_yaml)
        print(f'wrote best playbook -> {args.out}')

    return 0 if outcome.succeeded else 1


if __name__ == '__main__':
    sys.exit(main())
