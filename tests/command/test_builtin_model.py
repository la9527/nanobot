from __future__ import annotations

from pathlib import Path

import pytest

from nanobot.bus.events import InboundMessage
from nanobot.command.builtin import build_help_text, cmd_model
from nanobot.command.router import CommandContext
from nanobot.config.schema import Config
from nanobot.model_targets import SESSION_MODEL_TARGET_KEY
from nanobot.session.manager import SessionManager


def _make_loop(tmp_path: Path, config: Config):
    sessions = SessionManager(tmp_path)

    class _Loop:
        def __init__(self):
            self.runtime_config = config
            self.sessions = sessions

        def get_available_model_targets(self):
            from nanobot.model_targets import build_model_targets

            return build_model_targets(self.runtime_config)

        def get_active_model_target_name(self, session):
            from nanobot.model_targets import get_active_model_target_name

            return get_active_model_target_name(self.runtime_config, session)

        def set_session_model_target(self, session, target_name: str):
            session.metadata[SESSION_MODEL_TARGET_KEY] = target_name
            self.sessions.save(session)

        def clear_session_model_target(self, session):
            session.metadata.pop(SESSION_MODEL_TARGET_KEY, None)
            self.sessions.save(session)

    return _Loop()


def _make_ctx(tmp_path: Path, config: Config, raw: str, args: str = "") -> CommandContext:
    loop = _make_loop(tmp_path, config)
    msg = InboundMessage(channel="cli", sender_id="u1", chat_id="direct", content=raw)
    session = loop.sessions.get_or_create(msg.session_key)
    return CommandContext(msg=msg, session=session, key=msg.session_key, raw=raw, args=args, loop=loop)


@pytest.mark.asyncio
async def test_cmd_model_lists_and_selects_named_target(tmp_path: Path) -> None:
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "model": "vllm/default-model",
                    "provider": "vllm",
                    "modelSelection": {
                        "targets": {
                            "fast-local": {
                                "kind": "provider_model",
                                "provider": "vllm",
                                "model": "local/fast-model",
                            }
                        }
                    },
                }
            }
        }
    )

    out = await cmd_model(_make_ctx(tmp_path, config, "/model list", args="list"))
    assert "`fast-local`" in out.content

    set_out = await cmd_model(_make_ctx(tmp_path, config, "/model fast-local", args="fast-local"))
    assert "Selected `fast-local`" in set_out.content


@pytest.mark.asyncio
async def test_cmd_model_shows_smart_router_target(tmp_path: Path) -> None:
    config = Config.model_validate(
        {
            "plugins": {
                "smartrouter": {
                    "enabled": True,
                    "local": {"provider": "vllm", "model": "mlx-community/Qwen3.6-35B-A3B-4bit"},
                    "mini": {"provider": "openrouter", "model": "openai/gpt-5.4-mini"},
                    "full": {"provider": "openrouter", "model": "openai/gpt-5.4"},
                }
            }
        }
    )

    out = await cmd_model(_make_ctx(tmp_path, config, "/model", args=""))
    assert "`smart-router`" in out.content
    assert "`smart-router-local`" in out.content
    assert "`smart-router-mini`" in out.content
    assert "`smart-router-full`" in out.content
    assert "vllm -> mlx-community/Qwen3.6-35B-A3B-4bit | smart-router forced local tier" in out.content
    assert "openrouter -> openai/gpt-5.4-mini | smart-router forced mini tier" in out.content


def test_build_help_text_mentions_model_command() -> None:
    assert "/model [name|list|clear] — Switch model target, list available targets, or clear the override." in build_help_text()
    assert "/usage [off|tokens|full] — Show or change the token usage detail level." in build_help_text()