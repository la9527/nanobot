from __future__ import annotations

from pathlib import Path

import pytest

from nanobot.bus.events import InboundMessage
from nanobot.command.builtin import build_help_text, cmd_local_llm
from nanobot.command.router import CommandContext, CommandRouter
from nanobot.config.schema import Config
from nanobot.session.manager import SessionManager


def _make_ctx(tmp_path: Path, raw: str, args: str = "") -> CommandContext:
    sessions = SessionManager(tmp_path)

    class _Loop:
        runtime_config = Config.model_validate({})

    loop = _Loop()
    loop.sessions = sessions

    msg = InboundMessage(channel="telegram", sender_id="u1", chat_id="direct", content=raw)
    session = sessions.get_or_create(msg.session_key)
    return CommandContext(msg=msg, session=session, key=msg.session_key, raw=raw, args=args, loop=loop)


class _FakeLocalLlmController:
    def status(self) -> dict:
        return {
            "default_target": "qwen36",
            "default_model": "mlx-community/Qwen3.6-35B-A3B-4bit",
            "default_api_base": "http://127.0.0.1:1246/v1",
            "targets": [
                {
                    "name": "qwen36",
                    "model": "mlx-community/Qwen3.6-35B-A3B-4bit",
                    "running": True,
                    "endpoint_ok": True,
                    "supports_vision": False,
                    "vision_check_ok": True,
                    "vision_check_message": "Only 'text' content type is supported.",
                    "is_default": True,
                },
                {
                    "name": "lfm2",
                    "model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
                    "running": False,
                    "endpoint_ok": False,
                    "supports_vision": False,
                    "vision_check_ok": False,
                    "vision_check_message": "endpoint unavailable",
                    "is_default": False,
                },
            ],
        }

    def run_action(self, action: str, target: str) -> dict:
        return {
            "ok": True,
            "action": action,
            "target": target,
            "message": f"{action} {target} completed",
            "requires_restart": action == "use",
        }


@pytest.mark.asyncio
async def test_cmd_local_llm_status_uses_shared_controller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("nanobot.local_llm_control.default_controller", lambda: _FakeLocalLlmController())

    out = await cmd_local_llm(_make_ctx(tmp_path, "/local-llm status", args="status"))

    assert "## Local LLM" in out.content
    assert "Default: `qwen36`" in out.content
    assert "qwen36" in out.content
    assert "endpoint ok" in out.content
    assert "vision unsupported" in out.content
    assert "Only 'text' content type is supported." in out.content
    assert "Use `/model smart-router-local`" in out.content


@pytest.mark.asyncio
async def test_cmd_local_llm_use_requires_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("nanobot.local_llm_control.default_controller", lambda: _FakeLocalLlmController())

    out = await cmd_local_llm(_make_ctx(tmp_path, "/local-llm use qwen36", args="use qwen36"))

    assert "Run `/local-llm confirm use qwen36`" in out.content


@pytest.mark.asyncio
async def test_cmd_local_llm_confirm_use_reports_restart_requirement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("nanobot.local_llm_control.default_controller", lambda: _FakeLocalLlmController())

    out = await cmd_local_llm(_make_ctx(tmp_path, "/local-llm confirm use qwen36", args="confirm use qwen36"))

    assert "use qwen36 completed" in out.content
    assert "Use `/restart` when ready." in out.content


def test_help_text_mentions_local_llm_command() -> None:
    assert "/local-llm [status|start|stop|restart|smoke|use|confirm] [lfm2|qwen35-base-mlx-4bit|qwen36] — Show or control local LLM runtime." in build_help_text()


def test_command_router_dispatches_local_llm_prefix() -> None:
    from nanobot.command.builtin import register_builtin_commands

    router = CommandRouter()
    register_builtin_commands(router)

    assert router.is_dispatchable_command("/local-llm status") is True
