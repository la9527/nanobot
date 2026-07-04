"""Tests for channel-specific tool policy overrides."""

from pathlib import Path
from unittest.mock import MagicMock

from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.filesystem import ReadFileTool
from nanobot.agent.tools.shell import ExecTool
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
                        "allowPatterns": [r"^echo\s+"],
                        "denyPatterns": [r"forbidden"],
                        "approvalPatterns": [r"^sudo\b"],
                    }
                }
            }
        },
        tools_data={"restrictToWorkspace": False},
    )

    tools = loop._build_effective_tools("telegram")
    exec_tool = tools.get("exec")

    assert isinstance(exec_tool, ExecTool)
    assert exec_tool.allowed_dirs == [str(approved_dir.resolve())]
    assert exec_tool.allow_patterns == [r"^echo\s+"]
    assert exec_tool.deny_patterns[0] == r"forbidden"
    assert exec_tool.approval_patterns == [r"^sudo\b"]


def test_no_channel_override_falls_back_to_global_policy(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, tools_data={"restrictToWorkspace": True})

    tools = loop._build_effective_tools("cli")
    exec_tool = tools.get("exec")
    read_tool = tools.get("read_file")

    assert isinstance(exec_tool, ExecTool)
    assert isinstance(read_tool, ReadFileTool)
    assert read_tool._allowed_dir == tmp_path.resolve()
