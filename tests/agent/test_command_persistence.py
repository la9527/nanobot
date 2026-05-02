from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus


def _make_loop(tmp_path: Path) -> AgentLoop:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    return AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
    )


@pytest.mark.asyncio
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
