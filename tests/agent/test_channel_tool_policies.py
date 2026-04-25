"""Tests for channel-specific tool policy overrides."""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.filesystem import ReadFileTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.config.schema import ChannelsConfig, ToolsConfig


def _make_loop(
    tmp_path: Path,
    *,
    channels_data: dict | None = None,
    tools_data: dict | None = None,
) -> AgentLoop:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    channels = ChannelsConfig.model_validate(channels_data or {})
    tools = ToolsConfig.model_validate(tools_data or {})
    return AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
        channels_config=channels,
        tools_config=tools,
        exec_config=tools.exec,
        restrict_to_workspace=tools.restrict_to_workspace,
    )


def test_channel_override_can_disable_workspace_restriction(tmp_path: Path) -> None:
    loop = _make_loop(
        tmp_path,
        channels_data={
            "websocket": {"tools": {"restrictToWorkspace": False}},
            "telegram": {"tools": {"restrictToWorkspace": True}},
        },
        tools_data={"restrictToWorkspace": True},
    )

    websocket_policy = loop._resolve_tool_policy("websocket")
    telegram_policy = loop._resolve_tool_policy("telegram")

    assert websocket_policy["restrict_to_workspace"] is False
    assert telegram_policy["restrict_to_workspace"] is True


def test_channel_override_replaces_filesystem_allowed_dirs(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    approved_dir = tmp_path / "approved"
    approved_dir.mkdir()

    loop = _make_loop(
        tmp_path,
        channels_data={
            "telegram": {
                "tools": {
                    "filesystem": {"allowedDirs": [str(approved_dir)]},
                }
            }
        },
        tools_data={
            "restrictToWorkspace": False,
            "filesystem": {"allowedDirs": [str(docs_dir)]},
        },
    )

    tools = loop._build_effective_tools("telegram")
    read_tool = tools.get("read_file")

    assert isinstance(read_tool, ReadFileTool)
    assert read_tool._allowed_dir == approved_dir.resolve()


def test_channel_override_replaces_exec_policy(tmp_path: Path) -> None:
    approved_dir = tmp_path / "approved"
    approved_dir.mkdir()

    loop = _make_loop(
        tmp_path,
        channels_data={
            "telegram": {
                "tools": {
                    "exec": {
                        "allowedDirs": [str(approved_dir)],
                        "allowPatterns": [r"^echo\\s+"],
                        "denyPatterns": [r"forbidden"],
                        "approvalPatterns": [r"^sudo\\b"],
                    }
                }
            }
        },
        tools_data={"restrictToWorkspace": False},
    )

    tools = loop._build_effective_tools("telegram")
    exec_tool = tools.get("exec")

    assert isinstance(exec_tool, ExecTool)
    assert exec_tool.allowed_dirs == [str(approved_dir)]
    assert exec_tool.allow_patterns == [r"^echo\\s+"]
    assert exec_tool.deny_patterns[-1] == r"forbidden"
    assert exec_tool.approval_patterns == [r"^sudo\\b"]


@pytest.mark.asyncio
async def test_tool_approval_prompt_round_trip(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    pending: asyncio.Queue[InboundMessage] = asyncio.Queue()
    await pending.put(InboundMessage(
        channel="websocket",
        sender_id="user-1",
        chat_id="chat-1",
        content="yes",
        timestamp=datetime.now(),
    ))

    approved, reason = await loop._request_tool_approval(
        channel="websocket",
        chat_id="chat-1",
        message_id=None,
        pending_queue=pending,
        tool_name="exec",
        tool_call_id="call-1",
        prompt="Approval required before running this command.",
        params={"command": "rm -rf build"},
    )

    outbound = await loop.bus.consume_outbound()
    assert approved is True
    assert reason is None
    assert outbound.metadata["_tool_approval"] is True
    assert outbound.metadata["tool_name"] == "exec"


def test_parse_tool_approval_response_supports_yes_and_no(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    assert loop._parse_tool_approval_response("yes") is True
    assert loop._parse_tool_approval_response("승인") is True
    assert loop._parse_tool_approval_response("no") is False
    assert loop._parse_tool_approval_response("취소") is False
    assert loop._parse_tool_approval_response("maybe") is None


def test_telegram_tool_approval_prompt_is_compact(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    prompt = loop._format_tool_approval_prompt(
        channel="telegram",
        prompt="Approval required before running this command.\nWorking directory: /tmp/demo\nCommand: sudo rm -rf /tmp/demo\nReply yes to run it or no to block it.",
        params={"command": "sudo rm -rf /tmp/demo"},
    )

    assert prompt.startswith("Approval required for a high-risk command.")
    assert "Working directory" not in prompt
    assert "sudo rm -rf /tmp/demo" in prompt
    assert prompt.endswith("Reply yes to run or no to block.")