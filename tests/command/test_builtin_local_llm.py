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
            "smart_router_local_text_target": "qwen36",
            "smart_router_local_vision_target": "qwen3-vl-4b",
            "smart_router_local_image_ready": False,
            "smart_router_local_image_mode": "unavailable",
            "smart_router_local_image_message": "smart-router-local hybrid vision target `qwen3-vl-4b` unavailable: endpoint unavailable",
            "targets": [
                {
                    "name": "qwen36",
                    "model": "mlx-community/Qwen3.6-35B-A3B-4bit",
                    "running": True,
                    "endpoint_ok": True,
                    "supports_vision": False,
                    "vision_check_ok": True,
                    "vision_check_message": "Only 'text' content type is supported.",
                    "hybrid_vision_target": "qwen3-vl-4b",
                    "hybrid_vision_ready": False,
                    "hybrid_vision_check_message": "smart-router-local hybrid vision target `qwen3-vl-4b` unavailable: endpoint unavailable",
                    "management_mode": "on_demand",
                    "runtime_warming_up": False,
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
                    "management_mode": "manual",
                    "runtime_warming_up": False,
                    "is_default": False,
                },
                {
                    "name": "qwen3-vl-4b",
                    "model": "mlx-community/Qwen3-VL-4B-Instruct-4bit",
                    "running": True,
                    "endpoint_ok": True,
                    "supports_vision": True,
                    "vision_check_ok": True,
                    "vision_check_message": "vision probe passed",
                    "management_mode": "broker",
                    "holder_count": 2,
                    "holders": ["photo-ranker:pid-42", "smart-router-local"],
                    "runtime_warming_up": False,
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
    assert "hybrid vision unavailable" in out.content
    assert "on-demand" in out.content
    assert "broker" in out.content
    assert "holders: 2" in out.content
    assert "photo-ranker:pid-42, smart-router-local" in out.content
    assert "smart-router-local: smart-router-local hybrid vision target `qwen3-vl-4b` unavailable: endpoint unavailable" in out.content
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
    assert "/local-llm [status|start|stop|restart|smoke|use|confirm] [lfm2|lfm25-8b-a1b|qwen35-base-mlx-4bit|qwen36|qwen3-vl-4b|qwen3-vl-8b|lfm25-vl-1.6b|gemma4-e4b-current] — Show or control local LLM runtime." in build_help_text()


def test_command_router_dispatches_local_llm_prefix() -> None:
    from nanobot.command.builtin import register_builtin_commands

    router = CommandRouter()
    register_builtin_commands(router)

    assert router.is_dispatchable_command("/local-llm status") is True
