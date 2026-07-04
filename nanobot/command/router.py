"""Minimal command routing table for slash commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from nanobot.bus.events import InboundMessage, OutboundMessage
    from nanobot.session.manager import Session

Handler = Callable[["CommandContext"], Awaitable["OutboundMessage | None"]]


@dataclass
class CommandContext:
    """Everything a command handler needs to produce a response."""

    msg: InboundMessage
    session: Session | None
    key: str
    raw: str
    args: str = ""
    loop: Any = None


class CommandRouter:
    """Pure dict-based command dispatch.

    Three tiers checked in order:
      1. *priority* — exact-match commands handled before the dispatch lock
         (e.g. /stop, /restart).
      2. *exact* — exact-match commands handled inside the dispatch lock.
      3. *prefix* — longest-prefix-first match (e.g. "/team ").
    """

    def __init__(self) -> None:
        self._priority: dict[str, Handler] = {}
        self._exact: dict[str, Handler] = {}
        self._prefix: list[tuple[str, Handler]] = []

    def priority(self, cmd: str, handler: Handler) -> None:
        self._priority[cmd] = handler

    def exact(self, cmd: str, handler: Handler) -> None:
        self._exact[cmd] = handler

    def prefix(self, pfx: str, handler: Handler) -> None:
        self._prefix.append((pfx, handler))
        self._prefix.sort(key=lambda p: len(p[0]), reverse=True)

    def is_priority(self, text: str) -> bool:
        return self._normalize(text) in self._priority

    @staticmethod
    def _strip_mention(text: str) -> str:
        """Strip a Telegram '@botname' mention from a slash command, preserving case.

        Telegram group commands can arrive as '/status@mybot' or
        '/model@mybot smart-router'. We strip the bot mention so exact/prefix
        routing still matches, without touching the case of any following args.
        """
        raw = text.strip()
        if not raw.startswith("/"):
            return raw

        first, sep, rest = raw.partition(" ")
        if "@" in first:
            base, at, mention = first.partition("@")
            if at and mention and base.startswith("/"):
                first = base
        return first if not sep else f"{first}{sep}{rest}"

    @classmethod
    def _normalize(cls, text: str) -> str:
        """Mention-stripped, lowercased form used for case-insensitive command matching."""
        return cls._strip_mention(text).lower()

    def is_dispatchable_command(self, text: str) -> bool:
        """Check whether *text* matches any non-priority command tier (exact or prefix).

        Does NOT check priority tier.
        If this returns True, ``dispatch()`` is guaranteed to match a handler.
        """
        cmd = text.strip().lower()
        if cmd in self._exact:
            return True
        for pfx, _ in self._prefix:
            if cmd.startswith(pfx):
                return True
        return False

    async def dispatch_priority(self, ctx: CommandContext) -> OutboundMessage | None:
        """Dispatch a priority command. Called from run() without the lock."""
        handler = self._priority.get(self._normalize(ctx.raw))
        if handler:
            return await handler(ctx)
        return None

    async def dispatch(self, ctx: CommandContext) -> OutboundMessage | None:
        """Try exact, then prefix handlers. Returns None if unhandled."""
        stripped = self._strip_mention(ctx.raw)
        cmd = stripped.lower()

        if handler := self._exact.get(cmd):
            return await handler(ctx)

        for pfx, handler in self._prefix:
            if cmd.startswith(pfx):
                ctx.args = stripped[len(pfx):]
                return await handler(ctx)

        return None
