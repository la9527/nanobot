from __future__ import annotations

from pathlib import Path

import pytest

from nanobot.bus.events import InboundMessage
from nanobot.command.builtin import build_help_text, cmd_usage
from nanobot.command.router import CommandContext
from nanobot.response_status import SESSION_RESPONSE_FOOTER_MODE_KEY
from nanobot.session.manager import SessionManager


def _make_loop(tmp_path: Path):
    sessions = SessionManager(tmp_path)

    class _Loop:
        def __init__(self):
            self.sessions = sessions

        def get_response_footer_mode(self, session):
            from nanobot.response_status import normalize_response_footer_mode

            return normalize_response_footer_mode(
                session.metadata.get(SESSION_RESPONSE_FOOTER_MODE_KEY)
            )

        def set_response_footer_mode(self, session, mode: str):
            if mode == "off":
                session.metadata.pop(SESSION_RESPONSE_FOOTER_MODE_KEY, None)
            else:
                session.metadata[SESSION_RESPONSE_FOOTER_MODE_KEY] = mode
            self.sessions.save(session)

        def build_response_status(self, session):
            return {
                "model": "smart-router",
                "active_target": "smart-router",
                "usage": {"prompt_tokens": 120, "completion_tokens": 24, "total_tokens": 144},
                "context_tokens_estimate": 2048,
                "context_window_tokens": 65536,
                "footer_mode": self.get_response_footer_mode(session),
            }

    return _Loop()


def _make_ctx(tmp_path: Path, raw: str, args: str = "") -> CommandContext:
    loop = _make_loop(tmp_path)
    msg = InboundMessage(channel="cli", sender_id="u1", chat_id="direct", content=raw)
    session = loop.sessions.get_or_create(msg.session_key)
    return CommandContext(msg=msg, session=session, key=msg.session_key, raw=raw, args=args, loop=loop)


@pytest.mark.asyncio
async def test_cmd_usage_sets_full_mode(tmp_path: Path) -> None:
    out = await cmd_usage(_make_ctx(tmp_path, "/usage full", args="full"))

    assert "Selected `full`" in out.content
    assert "Status: model=smart-router" in out.content
    assert out.metadata == {"render_as": "text"}


@pytest.mark.asyncio
async def test_cmd_usage_clears_mode_with_off(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, "/usage tokens", args="tokens")
    await cmd_usage(ctx)

    clear_ctx = _make_ctx(tmp_path, "/usage off", args="off")
    out = await cmd_usage(clear_ctx)

    assert "Selected `off`" in out.content
    assert "will not include a status footer" in out.content
    assert clear_ctx.session.metadata.get(SESSION_RESPONSE_FOOTER_MODE_KEY) is None


def test_build_help_text_mentions_usage_command() -> None:
    assert "/usage — Show or change the reply footer mode" in build_help_text()