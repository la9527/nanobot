from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus


def _make_loop(tmp_path: Path) -> AgentLoop:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation.max_tokens = 4096
    return AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
    )


@pytest.mark.asyncio
async def test_context_clear_drops_history_without_relogging_command(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    session = loop.sessions.get_or_create("telegram:8688817632")
    session.messages = [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
    ]
    session.metadata.update({
        "action_result": {"status": "blocked", "title": "Old task"},
        "approval_summary": {"status": "pending"},
        "calendar_create_approval": {"title": "old event"},
        "pending_user_turn": True,
        "_last_summary": {"text": "old summary", "last_active": "2026-05-03T00:00:00"},
    })
    loop.sessions.save(session)
    loop.auto_compact._summaries[session.key] = ("old summary", session.updated_at)

    response = await loop._process_message(InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="8688817632",
        content="/clear",
    ))

    assert response is not None
    assert "Cleared 2 stored message(s)" in response.content
    assert response.metadata["render_as"] == "text"
    restored = loop.sessions.read_session_file("telegram:8688817632")
    assert restored is not None
    assert restored["messages"] == []
    assert "action_result" not in restored["metadata"]
    assert "approval_summary" not in restored["metadata"]
    assert "calendar_create_approval" not in restored["metadata"]
    assert "pending_user_turn" not in restored["metadata"]
    assert "_last_summary" not in restored["metadata"]
    assert session.key not in loop.auto_compact._summaries


@pytest.mark.asyncio
@pytest.mark.skip(reason="/calendar command not yet ported (Task 11 mail/calendar command wiring, tracked in upgrade plan)")
async def test_slash_command_turn_is_persisted_for_webui_history(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="8688817632",
        content="/calendar",
    )

    response = await loop._process_message(msg)

    assert response is not None
    assert "## Calendar" in response.content
    restored = loop.sessions.read_session_file("telegram:8688817632")
    assert restored is not None
    assert [message["role"] for message in restored["messages"][-2:]] == ["user", "assistant"]
    assert restored["messages"][-2]["content"] == "/calendar"
    assert "## Calendar" in restored["messages"][-1]["content"]
    context_window = restored["metadata"].get("context_window")
    assert isinstance(context_window, dict)
    assert context_window.get("max_tokens") == loop.context_window_tokens
    assert context_window.get("status") in {"healthy", "warning", "critical"}


@pytest.mark.asyncio
async def test_priority_slash_command_inline_is_persisted_for_linked_telegram_history(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="8688817632",
        content="/status",
        metadata={"_webui_bridge": True},
        session_key_override="telegram:8688817632",
    )

    await loop._dispatch_command_inline(
        msg,
        msg.session_key,
        msg.content.strip(),
        loop.commands.dispatch_priority,
    )

    restored = loop.sessions.read_session_file("telegram:8688817632")
    assert restored is not None
    assert [message["role"] for message in restored["messages"][-2:]] == ["user", "assistant"]
    assert restored["messages"][-2]["content"] == "/status"
    assert "Target:" in restored["messages"][-1]["content"]
    context_window = restored["metadata"].get("context_window")
    assert isinstance(context_window, dict)
    assert context_window.get("max_tokens") == loop.context_window_tokens
    assert context_window.get("status") in {"healthy", "warning", "critical"}
