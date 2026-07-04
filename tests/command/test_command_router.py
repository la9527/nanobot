from __future__ import annotations

import pytest

from nanobot.command.router import CommandContext, CommandRouter


@pytest.mark.asyncio
async def test_priority_command_accepts_telegram_bot_mention() -> None:
    router = CommandRouter()
    called = {"ok": False}

    async def handler(ctx: CommandContext):
        called["ok"] = True
        return "ok"

    router.priority("/status", handler)
    ctx = CommandContext(msg=None, session=None, key="k", raw="/status@la9527bot")

    result = await router.dispatch_priority(ctx)

    assert result == "ok"
    assert called["ok"] is True


@pytest.mark.asyncio
async def test_exact_command_accepts_telegram_bot_mention() -> None:
    router = CommandRouter()

    async def handler(ctx: CommandContext):
        return "ok"

    router.exact("/usage", handler)
    ctx = CommandContext(msg=None, session=None, key="k", raw="/usage@la9527bot")

    result = await router.dispatch(ctx)

    assert result == "ok"


@pytest.mark.asyncio
async def test_prefix_command_strips_bot_mention_from_args() -> None:
    router = CommandRouter()
    captured = {"args": ""}

    async def handler(ctx: CommandContext):
        captured["args"] = ctx.args
        return "ok"

    router.prefix("/model ", handler)
    ctx = CommandContext(
        msg=None,
        session=None,
        key="k",
        raw="/model@la9527bot smart-router",
    )

    result = await router.dispatch(ctx)

    assert result == "ok"
    assert captured["args"] == "smart-router"
