"""Classify playbook ``command:`` actions for the host-side backend.

A host-side run has no process in the guest to execute shell commands. Each
command a playbook uses is classified (see docs/guide/hostside-backend):

(a) provisioning time   - belongs in the image/recipe (package installs, services)
(b) GUI user action     - should be done through the GUI like a real user
(c) offline injection   - a file effect that can be applied to the overlay before
                          first boot (create/remove/chmod/set times)
(d) needs a guest part  - anything else (processes, services, pipes, network)

This module recognises the small, common set of *file-effect* commands that
class (c) can express and turns them into :class:`StagedOp` values; everything
else is reported as unsupported with its class, never silently skipped.
"""

from __future__ import annotations

import posixpath
import re
import shlex
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from adare.backend.hostside.guestfs import StagedOp, normalize

CLASS_PROVISION = 'a'
CLASS_GUI = 'b'
CLASS_INJECT = 'c'
CLASS_GUEST = 'd'

_PROVISION = re.compile(
    r'\b(apt(-get)?|dpkg|dnf|yum|snap|flatpak|pip3?|npm|cargo|gem|curl|wget|unzip|tar|docker|podman|'
    r'systemctl|service|useradd|usermod|adduser)\b'
)
# A GUI user action is a command that *starts* with an application launcher.
_GUI = re.compile(
    r'^\s*(sudo\s+(-\S+\s+)*)?(xdg-open|gio\s+open|nautilus|gnome-text-editor|gedit|firefox|libreoffice|xdotool|wmctrl)\b'
)


@dataclass
class CommandPlan:
    """Result of classifying one command."""

    command: str
    category: str  # 'a' | 'b' | 'c' | 'd'
    ops: list[StagedOp] = field(default_factory=list)
    reason: str = ''

    @property
    def stageable(self) -> bool:
        return self.category == CLASS_INJECT and bool(self.ops)


def guest_tzinfo(timezone_name: str | None) -> tzinfo:
    """tzinfo for the guest's ``/etc/timezone`` content (UTC when unknown)."""
    if timezone_name:
        try:
            return ZoneInfo(timezone_name.strip())
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return UTC


def parse_touch_stamp(stamp: str, tz: tzinfo) -> float:
    """``touch -t [[CC]YY]MMDDhhmm[.ss]`` -> epoch seconds, in the guest's time zone."""
    main, _, secs = stamp.partition('.')
    if len(main) == 12:
        fmt = '%Y%m%d%H%M'
    elif len(main) == 10:
        yy = int(main[:2])
        main = ('19' if yy >= 69 else '20') + main
        fmt = '%Y%m%d%H%M'
    elif len(main) == 8:
        main = f'{datetime.now(tz).year}{main}'
        fmt = '%Y%m%d%H%M'
    else:
        raise ValueError(f'unsupported touch -t stamp {stamp!r}')
    dt = datetime.strptime(main, fmt).replace(tzinfo=tz)
    return (dt + timedelta(seconds=int(secs or 0))).timestamp()


class CommandPlanner:
    """Turns resolved shell commands into :class:`StagedOp` lists."""

    #: Commands that only act on running processes: moot before first boot.
    NOOP_PROGRAMS = frozenset({'pkill', 'killall', 'kill'})

    def __init__(
        self,
        uid: int = 1000,
        gid: int = 1000,
        tz: tzinfo | None = None,
        now: float = 0.0,
        users: dict[str, tuple[int, int]] | None = None,
    ):
        self.uid = uid
        self.gid = gid
        self.tz = tz or UTC
        self.now = now
        self.users = {'root': (0, 0), **(users or {})}

    def plan(self, command: str, *, shell: bool = False, admin: bool = False, cwd: str | None = None) -> CommandPlan:
        """Classify ``command``; ``&&`` chains are planned segment by segment."""
        text = command.strip()
        if _PROVISION.search(text):
            return CommandPlan(
                text, CLASS_PROVISION, reason='package/service/user management belongs in the image recipe'
            )
        if _GUI.search(text):
            return CommandPlan(text, CLASS_GUI, reason='launching an application is a GUI user action')
        owner = (0, 0) if admin else (self.uid, self.gid)
        ops: list[StagedOp] = []
        notes: list[str] = []
        for segment in _split_and(text):
            plan = self._plan_segment(segment, owner, cwd, ops)
            if plan.category != CLASS_INJECT:
                return CommandPlan(text, plan.category, reason=f'{plan.reason} (in: {segment.strip()[:80]})')
            ops.extend(plan.ops)
            if plan.reason:
                notes.append(plan.reason)
        return CommandPlan(text, CLASS_INJECT, ops, reason='; '.join(notes))

    def _plan_segment(
        self, segment: str, owner: tuple[int, int], cwd: str | None, prior: list[StagedOp]
    ) -> CommandPlan:
        text = segment.strip()
        if text.startswith('(') and text.endswith(')'):
            text = text[1:-1].strip()
        # "<cmd> || true": the fallback only matters when <cmd> fails; judge <cmd>
        if '||' in text:
            text = text.split('||', 1)[0].strip()
        if re.match(r'(echo|printf)\b', text) and '$(' in text:
            # command substitution cannot run offline; harmless only when the output is merely printed
            if re.search(r'>>?\s*[^\s"\'$()]+\s*$', text):
                return CommandPlan(text, CLASS_GUEST, reason='command substitution written to a file')
            return CommandPlan(text, CLASS_INJECT, reason='echo with substitution only prints (no file effect)')
        try:
            tokens = shlex.split(text)
        except ValueError as e:
            return CommandPlan(text, CLASS_GUEST, reason=f'unparseable shell syntax ({e})')
        if not tokens:
            return CommandPlan(text, CLASS_GUEST, reason='empty command')
        split = _split_redirect(tokens)
        if split is None:
            return CommandPlan(text, CLASS_GUEST, reason='redirect not at the end, or a pipe / ; in the command')
        tokens, redirect = split
        return self._dispatch(text, tokens, redirect, owner, cwd, prior)

    def _dispatch(self, text, tokens, redirect, owner, cwd, prior) -> CommandPlan:
        prog, args = posixpath.basename(tokens[0]), tokens[1:]
        if prog in self.NOOP_PROGRAMS:
            return CommandPlan(text, CLASS_INJECT, reason=f'{prog}: no process exists before first boot (no-op)')
        if prog in ('echo', 'cat') and redirect is None:
            return CommandPlan(text, CLASS_INJECT, reason=f'{prog} without redirect only prints (no file effect)')
        try:
            if prog == 'chown':
                return self._plan_chown(text, args, prior, cwd)
            handler = getattr(self, f'_plan_{prog}', None)
            if handler is None:
                return CommandPlan(text, CLASS_GUEST, reason=f"'{prog}' needs a process in the guest")
            return cast(CommandPlan, handler(text, args, redirect, owner, cwd))
        except ValueError as e:
            return CommandPlan(text, CLASS_GUEST, reason=str(e))

    def _plan_chown(self, text: str, args: list[str], prior: list[StagedOp], cwd: str | None) -> CommandPlan:
        """``chown [-R] user[:group] path``: re-owns staged paths (it cannot touch base-image files)."""
        recursive = any(a.startswith('-') and 'R' in a for a in args)
        operands = [a for a in args if not a.startswith('-')]
        if len(operands) < 2:
            raise ValueError('chown without operands')
        user, _, group = operands[0].partition(':')
        if user not in self.users or (group and group not in self.users):
            raise ValueError(f'chown to unknown user/group {operands[0]!r}')
        uid = self.users[user][0]
        gid = self.users[group][1] if group else self.users[user][1]
        for target in operands[1:]:
            base = self._abs(target, cwd)
            hit = [op for op in prior if op.path == base or (recursive and op.path.startswith(base.rstrip('/') + '/'))]
            if not hit:
                raise ValueError(f'chown {base}: not a path staged by this plan (base-image ownership is not changed)')
            for op in hit:
                op.uid, op.gid = uid, gid
        return CommandPlan(text, CLASS_INJECT, reason='chown applied to staged paths')

    # -- handlers ----------------------------------------------------------------

    def _abs(self, path: str, cwd: str | None) -> str:
        if not path.startswith('/'):
            if not cwd:
                raise ValueError(f'relative path {path!r} without cwd')
            path = posixpath.join(cwd, path)
        return normalize(path)

    def _plan_echo(self, text, args, redirect, owner, cwd) -> CommandPlan:
        if redirect is None:
            raise ValueError('echo without a redirect has no file effect')
        if redirect[0] == '>>':
            raise ValueError('append (>>) needs the existing content; not stageable')
        newline, escapes = True, False
        while args and re.fullmatch(r'-[neE]+', args[0]):
            newline &= 'n' not in args[0]
            escapes = ('e' in args[0]) or (escapes and 'E' not in args[0])
            args = args[1:]
        body = ' '.join(args)
        if escapes:
            body = _decode_escapes(body)
        return self._write_plan(text, redirect[1], (body + ('\n' if newline else '')).encode(), owner, cwd)

    def _plan_printf(self, text, args, redirect, owner, cwd) -> CommandPlan:
        """``printf 'literal with \\n escapes' > file`` (no conversions: those need runtime values)."""
        if redirect is None or redirect[0] != '>':
            raise ValueError('printf without a plain redirect has no file effect')
        if len(args) != 1 or re.search(r'%[^%]', args[0]):
            raise ValueError('printf with conversions/arguments is not stageable')
        return self._write_plan(text, redirect[1], _decode_escapes(args[0].replace('%%', '%')).encode(), owner, cwd)

    def _write_plan(self, text, target, data: bytes, owner, cwd) -> CommandPlan:
        path = self._abs(target, cwd)
        return CommandPlan(
            text,
            CLASS_INJECT,
            [
                StagedOp(
                    'write',
                    path,
                    content=data,
                    mode=0o644,
                    uid=owner[0],
                    gid=owner[1],
                    mtime=self.now or None,
                    source=text,
                )
            ],
        )

    def _plan_rm(self, text, args, redirect, owner, cwd) -> CommandPlan:
        files = [a for a in args if not a.startswith('-')]
        flags = ''.join(a[1:] for a in args if a.startswith('-'))
        if not files:
            raise ValueError('rm without operands')
        if 'r' in flags or 'R' in flags:
            raise ValueError('recursive rm is not stageable (directory trees)')
        return CommandPlan(text, CLASS_INJECT, [StagedOp('remove', self._abs(f, cwd), source=text) for f in files])

    def _plan_mkdir(self, text, args, redirect, owner, cwd) -> CommandPlan:
        dirs = [a for a in args if not a.startswith('-')]
        if not dirs:
            raise ValueError('mkdir without operands')
        return CommandPlan(
            text,
            CLASS_INJECT,
            [StagedOp('mkdir', self._abs(d, cwd), mode=0o755, uid=owner[0], gid=owner[1], source=text) for d in dirs],
        )

    def _plan_chmod(self, text, args, redirect, owner, cwd) -> CommandPlan:
        operands = [a for a in args if not a.startswith('-')]
        if len(operands) < 2 or not re.fullmatch(r'[0-7]{3,4}', operands[0]):
            raise ValueError('only octal chmod is stageable')
        mode = int(operands[0], 8)
        return CommandPlan(
            text, CLASS_INJECT, [StagedOp('chmod', self._abs(f, cwd), mode=mode, source=text) for f in operands[1:]]
        )

    def _plan_touch(self, text, args, redirect, owner, cwd) -> CommandPlan:
        atime_only = mtime_only = False
        stamp = None
        files = []
        it = iter(args)
        for a in it:
            if a == '-t':
                stamp = next(it, None)
            elif a.startswith('-') and a[1:] and set(a[1:]) <= {'a', 'm', 'c'}:
                atime_only |= 'a' in a
                mtime_only |= 'm' in a
            elif a.startswith('-'):
                raise ValueError(f'touch option {a!r} is not stageable')
            else:
                files.append(a)
        if not files:
            raise ValueError('touch without operands')
        when = parse_touch_stamp(stamp, self.tz) if stamp else (self.now or None)
        if when is None:
            raise ValueError('touch without -t needs the current guest time')
        both = not (atime_only or mtime_only)
        ops = []
        for f in files:
            ops.append(
                StagedOp(
                    'set_time',
                    self._abs(f, cwd),
                    atime=when if (atime_only or both) else None,
                    mtime=when if (mtime_only or both) else None,
                    source=text,
                )
            )
        return CommandPlan(text, CLASS_INJECT, ops)


def _split_redirect(tokens: list[str]) -> tuple[list[str], tuple[str, str] | None] | None:
    """Split one trailing ``> path`` / ``>> path`` off the tokens; None when the shape is not stageable."""
    if ';' in tokens or '|' in tokens:
        return None
    for sym in ('>>', '>'):
        if sym in tokens:
            idx = tokens.index(sym)
            if idx != len(tokens) - 2:
                return None
            return tokens[:idx], (sym, tokens[-1])
    return tokens, None


def _decode_escapes(text: str) -> str:
    """Backslash escapes as ``echo -e`` / ``printf`` read them (``\\n``, ``\\t``, ``\\\\``)."""
    return text.replace('\\\\', '\x00').replace('\\n', '\n').replace('\\t', '\t').replace('\x00', '\\')


def _split_and(text: str) -> list[str]:
    """Split on top-level ``&&`` (outside quotes and parentheses)."""
    parts, buf, depth, quote = [], [], 0, ''
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ''
        elif ch in '\'"':
            quote = ch
            buf.append(ch)
        elif ch == '(':
            depth += 1
            buf.append(ch)
        elif ch == ')':
            depth -= 1
            buf.append(ch)
        elif depth == 0 and text.startswith('&&', i):
            parts.append(''.join(buf))
            buf = []
            i += 1
        else:
            buf.append(ch)
        i += 1
    parts.append(''.join(buf))
    return [p for p in parts if p.strip()]
