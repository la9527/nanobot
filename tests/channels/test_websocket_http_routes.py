"""End-to-end tests for the embedded webui's HTTP routes on the WebSocket channel."""

import asyncio
import functools
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from nanobot.bus.events import OutboundMessage
from nanobot.channels.websocket import WebSocketChannel
from nanobot.session.manager import Session, SessionManager

_PORT = 29900


def _ch(
    bus: Any,
    *,
    session_manager: SessionManager | None = None,
    static_dist_path: Path | None = None,
    port: int = _PORT,
    **extra: Any,
) -> WebSocketChannel:
    cfg: dict[str, Any] = {
        "enabled": True,
        "allowFrom": ["*"],
        "host": "127.0.0.1",
        "port": port,
        "path": "/",
        "websocketRequiresToken": False,
    }
    cfg.update(extra)
    return WebSocketChannel(
        cfg,
        bus,
        session_manager=session_manager,
        static_dist_path=static_dist_path,
    )


@pytest.fixture()
def bus() -> MagicMock:
    b = MagicMock()
    b.publish_inbound = AsyncMock()
    return b


async def _http_get(
    url: str, headers: dict[str, str] | None = None
) -> httpx.Response:
    return await asyncio.to_thread(
        functools.partial(httpx.get, url, headers=headers or {}, timeout=5.0)
    )


def _seed_session(workspace: Path, key: str = "websocket:test") -> SessionManager:
    sm = SessionManager(workspace)
    s = Session(key=key)
    s.add_message("user", "hi")
    s.add_message("assistant", "hello back")
    sm.save(s)
    return sm


def _seed_many(workspace: Path, keys: list[str]) -> SessionManager:
    sm = SessionManager(workspace)
    for k in keys:
        s = Session(key=k)
        s.add_message("user", f"hi from {k}")
        sm.save(s)
    return sm


@pytest.mark.asyncio
async def test_bootstrap_returns_token_for_localhost(
    bus: MagicMock, tmp_path: Path
) -> None:
    sm = _seed_session(tmp_path)
    channel = _ch(bus, session_manager=sm, port=29901)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        resp = await _http_get("http://127.0.0.1:29901/webui/bootstrap")
        assert resp.status_code == 200
        body = resp.json()
        assert body["token"].startswith("nbwt_")
        assert body["ws_path"] == "/"
        assert body["expires_in"] > 0
        assert isinstance(body.get("model_name"), str)
        assert isinstance(body.get("model_targets"), list)
        assert any(row.get("name") == "default" for row in body["model_targets"])
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_bootstrap_resolves_env_backed_model_target_strings(
    bus: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sm = _seed_session(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "defaults": {
                        "model": "${LOCAL_LLM_MODEL}",
                        "provider": "vllm",
                        "modelSelection": {
                            "targets": {
                                "local-llm": {
                                    "kind": "provider_model",
                                    "provider": "vllm",
                                    "model": "${LOCAL_LLM_MODEL}",
                                    "description": "current local runtime (${LOCAL_LLM_MODEL})",
                                }
                            }
                        },
                    }
                },
                "plugins": {
                    "smartrouter": {
                        "enabled": True,
                        "local": {"provider": "vllm", "model": "${LOCAL_LLM_MODEL}"},
                        "mini": {"provider": "openrouter", "model": "openai/gpt-5.4-mini"},
                        "full": {"provider": "openrouter", "model": "openai/gpt-5.4"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LOCAL_LLM_MODEL", "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0")
    monkeypatch.setattr("nanobot.config.loader._current_config_path", config_path)

    channel = _ch(bus, session_manager=sm, port=29914)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        resp = await _http_get("http://127.0.0.1:29914/webui/bootstrap")
        assert resp.status_code == 200
        body = resp.json()
        rows = {row["name"]: row for row in body["model_targets"]}
        assert rows["local-llm"]["model"] == "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0"
        assert rows["local-llm"]["description"] == "current local runtime (LiquidAI/LFM2-24B-A2B-GGUF:Q4_0)"
        assert rows["smart-router-local"]["description"] == (
            "smart-router forced local tier (LiquidAI/LFM2-24B-A2B-GGUF:Q4_0)"
        )
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_settings_route_resolves_env_backed_local_model_and_preserves_config(
    bus: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sm = _seed_session(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "defaults": {
                        "model": "${LOCAL_LLM_MODEL}",
                        "provider": "vllm",
                    }
                },
                "providers": {
                    "vllm": {
                        "apiBase": "http://127.0.0.1:8000/v1"
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LOCAL_LLM_MODEL", "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0")
    monkeypatch.setattr("nanobot.config.loader._current_config_path", config_path)

    channel = _ch(bus, session_manager=sm, port=29915)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        boot = await _http_get("http://127.0.0.1:29915/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        settings = await _http_get("http://127.0.0.1:29915/api/settings", headers=auth)
        assert settings.status_code == 200
        body = settings.json()
        assert body["agent"]["model"] == "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0"
        assert body["agent"]["configured_model"] == "${LOCAL_LLM_MODEL}"
        assert body["agent"]["provider"] == "vllm"
        assert body["agent"]["resolved_provider"] == "vllm"
        assert body["agent"]["model_locked"] is True
        assert body["agent"]["provider_locked"] is True

        updated = await _http_get(
            "http://127.0.0.1:29915/api/settings/update?model=openai%2Fgpt-5.4&provider=openai",
            headers=auth,
        )
        assert updated.status_code == 200
        updated_body = updated.json()
        assert updated_body["agent"]["model"] == "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0"
        assert updated_body["agent"]["provider"] == "vllm"
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved["agents"]["defaults"]["model"] == "${LOCAL_LLM_MODEL}"
        assert saved["agents"]["defaults"]["provider"] == "vllm"
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_session_model_target_routes_round_trip(
    bus: MagicMock, tmp_path: Path
) -> None:
    sm = _seed_session(tmp_path, key="websocket:model-chat")
    channel = _ch(bus, session_manager=sm, port=29911)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        boot = await _http_get("http://127.0.0.1:29911/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        current = await _http_get(
            "http://127.0.0.1:29911/api/sessions/websocket:model-chat/model-target",
            headers=auth,
        )
        assert current.status_code == 200
        assert isinstance(current.json()["active_target"], str)

        selected = await _http_get(
            "http://127.0.0.1:29911/api/sessions/websocket:model-chat/model-target/default/select",
            headers=auth,
        )
        assert selected.status_code == 200
        assert isinstance(selected.json()["active_target"], str)
        session = sm.get_or_create("websocket:model-chat")
        assert session.metadata.get("model_target") == "default"

        cleared = await _http_get(
            "http://127.0.0.1:29911/api/sessions/websocket:model-chat/model-target/clear",
            headers=auth,
        )
        assert cleared.status_code == 200
        session = sm.get_or_create("websocket:model-chat")
        assert "model_target" not in session.metadata
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_session_model_target_routes_reject_unknown_target(
    bus: MagicMock, tmp_path: Path
) -> None:
    sm = _seed_session(tmp_path, key="websocket:model-chat")
    channel = _ch(bus, session_manager=sm, port=29912)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        boot = await _http_get("http://127.0.0.1:29912/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        resp = await _http_get(
            "http://127.0.0.1:29912/api/sessions/websocket:model-chat/model-target/not-a-real-target/select",
            headers=auth,
        )
        assert resp.status_code == 404
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_sessions_routes_require_bearer_token(
    bus: MagicMock, tmp_path: Path
) -> None:
    sm = _seed_session(tmp_path, key="websocket:abc")
    channel = _ch(bus, session_manager=sm, port=29902)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        # Unauthenticated → 401.
        deny = await _http_get("http://127.0.0.1:29902/api/sessions")
        assert deny.status_code == 401

        # Mint a token via bootstrap, then call the API with it.
        boot = await _http_get("http://127.0.0.1:29902/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        listing = await _http_get("http://127.0.0.1:29902/api/sessions", headers=auth)
        assert listing.status_code == 200
        keys = [s["key"] for s in listing.json()["sessions"]]
        assert "websocket:abc" in keys
        # Server stays an opaque source: filesystem paths must not leak to the wire.
        assert all("path" not in s for s in listing.json()["sessions"])
        assert all(isinstance(s.get("active_target"), str) for s in listing.json()["sessions"])
        continuity = listing.json()["sessions"][0]["metadata"]["continuity"]
        assert continuity["canonical_owner_id"] == "primary-user"
        assert continuity["channel_kind"] == "websocket"
        assert continuity["external_identity"] == "local-webui"
        assert continuity["trust_level"] == "trusted"

        msgs = await _http_get(
            "http://127.0.0.1:29902/api/sessions/websocket:abc/messages",
            headers=auth,
        )
        assert msgs.status_code == 200
        body = msgs.json()
        assert body["key"] == "websocket:abc"
        assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
        assert body["metadata"]["continuity"]["canonical_owner_id"] == "primary-user"
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_sessions_list_only_returns_websocket_sessions_by_default(
    bus: MagicMock, tmp_path: Path
) -> None:
    # Seed a realistic multi-channel disk state: CLI, Slack, Lark and
    # websocket sessions all live in the same ``sessions/`` directory.
    sm = _seed_many(
        tmp_path,
        [
            "cli:direct",
            "slack:C123",
            "lark:oc_abc",
            "telegram:12345",
            "telegram:-1001:topic:42",
            "websocket:alpha",
            "websocket:beta",
        ],
    )
    channel = _ch(bus, session_manager=sm, port=29906)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        boot = await _http_get("http://127.0.0.1:29906/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        listing = await _http_get(
            "http://127.0.0.1:29906/api/sessions", headers=auth
        )
        assert listing.status_code == 200
        rows = listing.json()["sessions"]
        keys = {s["key"] for s in rows}
        assert keys == {
            "telegram:12345",
            "telegram:-1001:topic:42",
            "websocket:alpha",
            "websocket:beta",
        }
        continuity = {
            row["key"]: row["metadata"]["continuity"]["external_identity"]
            for row in rows
        }
        assert continuity["telegram:12345"] == "12345"
        assert continuity["telegram:-1001:topic:42"] == "-1001"
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_session_messages_route_reads_telegram_sessions(
    bus: MagicMock, tmp_path: Path
) -> None:
    sm = _seed_session(tmp_path, key="telegram:12345")
    channel = _ch(bus, session_manager=sm, port=29925)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        boot = await _http_get("http://127.0.0.1:29925/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        msgs = await _http_get(
            "http://127.0.0.1:29925/api/sessions/telegram%3A12345/messages",
            headers=auth,
        )
        assert msgs.status_code == 200
        assert msgs.json()["key"] == "telegram:12345"
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_session_message_envelope_publishes_telegram_inbound(
    bus: MagicMock, tmp_path: Path
) -> None:
    sm = _seed_session(tmp_path, key="telegram:-1001:topic:42")
    channel = _ch(bus, session_manager=sm, port=29926)

    class DummyConn:
        remote_address = ("127.0.0.1", 9999)

    conn = DummyConn()

    await channel._dispatch_envelope(
        conn,
        "browser-client",
        {
            "type": "session_message",
            "session_key": "telegram:-1001:topic:42",
            "content": "reply from webui",
        },
    )

    bus.publish_inbound.assert_awaited_once()
    msg = bus.publish_inbound.await_args.args[0]
    assert msg.channel == "telegram"
    assert msg.chat_id == "-1001"
    assert msg.session_key_override == "telegram:-1001:topic:42"
    assert msg.metadata["message_thread_id"] == 42
    assert msg.content == "reply from webui"


@pytest.mark.asyncio
async def test_websocket_memory_correction_message_updates_memory_and_replies(
    bus: MagicMock, tmp_path: Path,
) -> None:
    sm = _seed_session(tmp_path, key="websocket:memory-chat")
    channel = _ch(bus, session_manager=sm, port=29928)

    class DummyConn:
        remote_address = ("127.0.0.1", 9999)

        def __init__(self) -> None:
            self.sent: list[str] = []

        async def send(self, raw: str) -> None:
            self.sent.append(raw)

    conn = DummyConn()

    await channel._dispatch_envelope(
        conn,
        "browser-client",
        {
            "type": "message",
            "chat_id": "memory-chat",
            "content": "기억해\n내용: Telegram 채널을 우선 사용한다\n현재 task: memory correction\n저장 위치: memory/MEMORY.md",
        },
    )

    bus.publish_inbound.assert_not_awaited()
    memory_text = (tmp_path / "memory" / "MEMORY.md").read_text(encoding="utf-8")
    assert "- Telegram 채널을 우선 사용한다" in memory_text
    payload = json.loads(conn.sent[-1])
    assert payload["event"] == "message"
    assert payload["text"] == "memory/MEMORY.md 에 반영했어요: Telegram 채널을 우선 사용한다"


@pytest.mark.asyncio
async def test_bridged_memory_correction_updates_user_profile_without_bus_publish(
    bus: MagicMock, tmp_path: Path,
) -> None:
    sm = _seed_session(tmp_path, key="telegram:-1001:topic:42")
    channel = _ch(bus, session_manager=sm, port=29929)

    class DummyConn:
        remote_address = ("127.0.0.1", 9999)

    await channel._dispatch_envelope(
        DummyConn(),
        "browser-client",
        {
            "type": "session_message",
            "session_key": "telegram:-1001:topic:42",
            "content": "이건 기본 선호가 아님\n수정할 기본 선호: 답변 길이는 기본적으로 간결하게 유지\n현재 task: owner defaults\n저장 위치: USER.md",
        },
    )

    bus.publish_inbound.assert_not_awaited()
    user_text = (tmp_path / "USER.md").read_text(encoding="utf-8")
    assert "- 답변 길이는 기본적으로 간결하게 유지" in user_text
    data = sm.read_session_file("telegram:-1001:topic:42")
    assert data is not None
    assert data["messages"][-1]["role"] == "assistant"
    assert data["messages"][-1]["content"] == (
        "USER.md 기본 선호 보정 항목에 추가했어요: 답변 길이는 기본적으로 간결하게 유지"
    )


@pytest.mark.asyncio
async def test_send_marks_remote_user_echo_kind_for_webui_mirrors(
    bus: MagicMock, tmp_path: Path
) -> None:
    sm = _seed_session(tmp_path, key="telegram:12345")
    channel = _ch(bus, session_manager=sm, port=29927)

    class DummyConn:
        remote_address = ("127.0.0.1", 9999)

        def __init__(self) -> None:
            self.sent: list[str] = []

        async def send(self, raw: str) -> None:
            self.sent.append(raw)

    conn = DummyConn()
    channel._attach(conn, "telegram:12345")

    await channel.send(
        OutboundMessage(
            channel="websocket",
            chat_id="telegram:12345",
            content="fresh telegram push",
            metadata={"_remote_user_echo": True},
        )
    )

    assert conn.sent
    payload = json.loads(conn.sent[-1])
    assert payload["event"] == "message"
    assert payload["chat_id"] == "telegram:12345"
    assert payload["kind"] == "remote_user"
    assert payload["text"] == "fresh telegram push"


@pytest.mark.asyncio
async def test_sessions_list_uses_session_model_target_override(
        bus: MagicMock, tmp_path: Path
) -> None:
        sm = _seed_session(tmp_path, key="websocket:alpha")
        session = sm.get_or_create("websocket:alpha")
        session.metadata["model_target"] = "default"
        sm.save(session)
        channel = _ch(bus, session_manager=sm, port=29913)
        server_task = asyncio.create_task(channel.start())
        await asyncio.sleep(0.3)
        try:
            boot = await _http_get("http://127.0.0.1:29913/webui/bootstrap")
            token = boot.json()["token"]
            auth = {"Authorization": f"Bearer {token}"}

            listing = await _http_get("http://127.0.0.1:29913/api/sessions", headers=auth)
            assert listing.status_code == 200
            row = listing.json()["sessions"][0]
            assert row["key"] == "websocket:alpha"
            assert row["active_target"] == "default"
        finally:
            await channel.stop()
            await server_task


@pytest.mark.asyncio
async def test_sessions_list_exposes_pending_approval_summary(
    bus: MagicMock, tmp_path: Path
) -> None:
    sm = _seed_session(tmp_path, key="telegram:12345")
    session = sm.get_or_create("telegram:12345")
    session.metadata["approval_summary"] = {
        "status": "pending",
        "channel": "telegram",
        "tool_name": "exec",
        "tool_call_id": "call-1",
        "prompt_preview": "Approval required for a high-risk command.",
    }
    sm.save(session)
    channel = _ch(bus, session_manager=sm, port=29916)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        boot = await _http_get("http://127.0.0.1:29916/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        listing = await _http_get("http://127.0.0.1:29916/api/sessions", headers=auth)
        assert listing.status_code == 200
        row = listing.json()["sessions"][0]
        assert row["metadata"]["approval_summary"]["status"] == "pending"
        assert row["metadata"]["approval_summary"]["tool_name"] == "exec"
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_same_owner_sessions_keep_approval_visibility_on_linked_row(
    bus: MagicMock, tmp_path: Path
) -> None:
    sm = _seed_many(tmp_path, ["websocket:alpha", "telegram:12345"])
    telegram_session = sm.get_or_create("telegram:12345")
    telegram_session.metadata["approval_summary"] = {
        "status": "pending",
        "channel": "telegram",
        "tool_name": "exec",
        "tool_call_id": "call-1",
        "prompt_preview": "Approval required for a high-risk command.",
    }
    sm.save(telegram_session)

    channel = _ch(bus, session_manager=sm, port=29917)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        boot = await _http_get("http://127.0.0.1:29917/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        listing = await _http_get("http://127.0.0.1:29917/api/sessions", headers=auth)
        assert listing.status_code == 200
        rows = {row["key"]: row for row in listing.json()["sessions"]}

        assert rows["websocket:alpha"]["metadata"]["continuity"]["canonical_owner_id"] == "primary-user"
        assert rows["telegram:12345"]["metadata"]["continuity"]["canonical_owner_id"] == "primary-user"
        assert rows["telegram:12345"]["metadata"]["approval_summary"]["status"] == "pending"
        assert rows["websocket:alpha"]["metadata"].get("approval_summary") is None
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_sessions_list_keeps_enough_metadata_for_owner_aggregate_derivation(
    bus: MagicMock, tmp_path: Path
) -> None:
    sm = _seed_many(tmp_path, ["websocket:alpha", "telegram:12345", "websocket:beta"])

    telegram_session = sm.get_or_create("telegram:12345")
    telegram_session.metadata["continuity"] = {
        "canonical_owner_id": "primary-user",
        "channel_kind": "telegram",
        "external_identity": "12345",
        "trust_level": "linked",
    }
    telegram_session.metadata["approval_summary"] = {
        "status": "pending",
        "channel": "telegram",
        "tool_name": "exec",
        "tool_call_id": "call-1",
        "prompt_preview": "Approval required for a high-risk command.",
    }
    sm.save(telegram_session)

    channel = _ch(bus, session_manager=sm, port=29918)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        boot = await _http_get("http://127.0.0.1:29918/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        listing = await _http_get("http://127.0.0.1:29918/api/sessions", headers=auth)
        assert listing.status_code == 200
        rows = listing.json()["sessions"]

        owner_rows = [
            row
            for row in rows
            if row["metadata"]["continuity"]["canonical_owner_id"] == "primary-user"
        ]
        approval_pending_count = sum(
            1
            for row in owner_rows
            if row["metadata"].get("approval_summary", {}).get("status") == "pending"
        )
        linked_external_rows = [
            row for row in owner_rows if row["key"] != "websocket:alpha" and not row["key"].startswith("websocket:")
        ]

        assert {row["key"] for row in owner_rows} == {
            "websocket:alpha",
            "telegram:12345",
            "websocket:beta",
        }
        assert approval_pending_count == 1
        assert [row["key"] for row in linked_external_rows] == ["telegram:12345"]
        assert linked_external_rows[0]["updated_at"] is not None
        assert linked_external_rows[0]["metadata"]["approval_summary"]["tool_name"] == "exec"
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_sessions_list_exposes_minimal_task_summary_backbone(
    bus: MagicMock, tmp_path: Path
) -> None:
    (tmp_path / "USER.md").write_text(
        """# User Profile

## Basic Information

- **Timezone**: Asia/Seoul
- **Language**: ko-KR

## Preferences

### Communication Style

- [x] Technical
- [ ] Professional

### Response Length

- [x] Brief and concise
- [ ] Detailed explanations
""",
        encoding="utf-8",
    )
    sm = _seed_many(tmp_path, ["websocket:alpha", "telegram:12345", "websocket:beta"])

    telegram_session = sm.get_or_create("telegram:12345")
    telegram_session.metadata["approval_summary"] = {
        "status": "pending",
        "channel": "telegram",
        "tool_name": "exec",
        "tool_call_id": "call-1",
        "prompt_preview": "Approve sending the summary email.",
    }
    sm.save(telegram_session)

    blocked_session = sm.get_or_create("websocket:beta")
    blocked_session.metadata["pending_user_turn"] = True
    blocked_session.metadata["runtime_checkpoint"] = {
        "phase": "awaiting_tools",
        "iteration": 0,
        "model": "smart-router",
    }
    sm.save(blocked_session)

    proactive_session = sm.get_or_create("telegram:12345")
    proactive_session.metadata["proactive_summary"] = {
        "status": "suppressed",
        "category": "briefing",
        "title": "Morning briefing ready",
        "summary": "오늘 일정 1개와 승인 대기 1개가 있습니다.",
        "target_channel": "telegram",
        "suppressed_reason": "quiet_hours",
        "updated_at": "2026-05-01T06:00:00Z",
    }
    sm.save(proactive_session)

    channel = _ch(bus, session_manager=sm, port=29919)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        boot = await _http_get("http://127.0.0.1:29919/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        listing = await _http_get("http://127.0.0.1:29919/api/sessions", headers=auth)
        assert listing.status_code == 200
        rows = {row["key"]: row for row in listing.json()["sessions"]}

        approval_task = rows["telegram:12345"]["metadata"]["task_summary"]
        assert approval_task["task_id"] == "session:telegram:12345"
        assert approval_task["canonical_owner_id"] == "primary-user"
        assert approval_task["status"] == "waiting-approval"
        assert approval_task["title"] == "Approve sending the summary email."
        assert approval_task["origin_channel"] == "telegram"
        assert approval_task["origin_session_key"] == "telegram:12345"
        assert approval_task["next_step_hint"] == "Review the pending approval request."

        proactive_summary = rows["telegram:12345"]["metadata"]["proactive_summary"]
        assert proactive_summary["status"] == "suppressed"
        assert proactive_summary["category"] == "briefing"
        assert proactive_summary["title"] == "Morning briefing ready"
        assert proactive_summary["target_channel"] == "telegram"

        blocked_task = rows["websocket:beta"]["metadata"]["task_summary"]
        assert blocked_task["task_id"] == "session:websocket:beta"
        assert blocked_task["status"] == "blocked"
        assert blocked_task["origin_channel"] == "websocket"
        assert blocked_task["next_step_hint"] == "Reopen the interrupted session and continue the task."

        completed_task = rows["websocket:alpha"]["metadata"]["task_summary"]
        assert completed_task["task_id"] == "session:websocket:alpha"
        assert completed_task["status"] == "completed"
        assert completed_task["canonical_owner_id"] == "primary-user"
        assert completed_task["updated_at"] is not None

        owner_profile = rows["websocket:alpha"]["metadata"]["owner_profile"]
        assert owner_profile["canonical_owner_id"] == "primary-user"
        assert owner_profile["preferred_language"] == "ko-KR"
        assert owner_profile["timezone"] == "Asia/Seoul"
        assert owner_profile["response_tone"] == "technical"
        assert owner_profile["response_length"] == "brief"

        memory_boundary = rows["websocket:alpha"]["metadata"]["memory_boundary"]
        assert memory_boundary["owner_profile"] == "USER.md"
        assert memory_boundary["project_memory"] == "memory/MEMORY.md"
        assert memory_boundary["session_state"] == "session.metadata"
        assert memory_boundary["raw_history"] == "memory/history.jsonl"

        memory_correction = rows["websocket:alpha"]["metadata"]["memory_correction"]
        assert memory_correction["actions"][0]["code"] == "remember"
        assert memory_correction["actions"][0]["phrase"] == "기억해"
        assert memory_correction["actions"][1]["code"] == "forget"
        assert memory_correction["actions"][2]["code"] == "not-default"
        assert memory_correction["actions"][3]["code"] == "project-complete"
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_session_delete_removes_file(bus: MagicMock, tmp_path: Path) -> None:
    sm = _seed_session(tmp_path, key="websocket:doomed")
    channel = _ch(bus, session_manager=sm, port=29903)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        boot = await _http_get("http://127.0.0.1:29903/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        path = sm._get_session_path("websocket:doomed")
        assert path.exists()
        resp = await _http_get(
            "http://127.0.0.1:29903/api/sessions/websocket:doomed/delete",
            headers=auth,
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert not path.exists()
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_session_routes_accept_percent_encoded_websocket_keys(
    bus: MagicMock, tmp_path: Path
) -> None:
    sm = _seed_session(tmp_path, key="websocket:encoded-key")
    channel = _ch(bus, session_manager=sm, port=29910)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        boot = await _http_get("http://127.0.0.1:29910/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        msgs = await _http_get(
            "http://127.0.0.1:29910/api/sessions/websocket%3Aencoded-key/messages",
            headers=auth,
        )
        assert msgs.status_code == 200
        assert msgs.json()["key"] == "websocket:encoded-key"

        path = sm._get_session_path("websocket:encoded-key")
        assert path.exists()
        deleted = await _http_get(
            "http://127.0.0.1:29910/api/sessions/websocket%3Aencoded-key/delete",
            headers=auth,
        )
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True
        assert not path.exists()
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_session_routes_reject_non_websocket_keys(
    bus: MagicMock, tmp_path: Path
) -> None:
    sm = _seed_many(
        tmp_path,
        [
            "websocket:kept",
            "cli:direct",
            "slack:C123",
        ],
    )
    channel = _ch(bus, session_manager=sm, port=29909)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        boot = await _http_get("http://127.0.0.1:29909/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        # The webui list already hides non-websocket sessions; handcrafted URLs
        # should hit the same boundary rather than exposing or deleting them.
        msgs = await _http_get(
            "http://127.0.0.1:29909/api/sessions/cli:direct/messages",
            headers=auth,
        )
        assert msgs.status_code == 404

        doomed = sm._get_session_path("slack:C123")
        assert doomed.exists()
        deny_delete = await _http_get(
            "http://127.0.0.1:29909/api/sessions/slack:C123/delete",
            headers=auth,
        )
        assert deny_delete.status_code == 404
        assert doomed.exists()
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_session_routes_reject_invalid_key(
    bus: MagicMock, tmp_path: Path
) -> None:
    sm = _seed_session(tmp_path)
    channel = _ch(bus, session_manager=sm, port=29904)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        boot = await _http_get("http://127.0.0.1:29904/webui/bootstrap")
        token = boot.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        # Invalid characters in the key -> regex match fails -> 404
        # (route doesn't match, falls through to channel 404).
        resp = await _http_get(
            "http://127.0.0.1:29904/api/sessions/bad%20key/messages",
            headers=auth,
        )
        assert resp.status_code in {400, 404}
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_static_serves_index_when_dist_present(
    bus: MagicMock, tmp_path: Path
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>nbweb</title>")
    (dist / "favicon.svg").write_text("<svg/>")
    sm = _seed_session(tmp_path / "ws_state")
    channel = _ch(bus, session_manager=sm, static_dist_path=dist, port=29905)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        # Bare ``GET /`` is a browser opening the app: it must return the SPA
        # index.html, not the WS-upgrade handler's 401/426.
        root = await _http_get("http://127.0.0.1:29905/")
        assert root.status_code == 200
        assert "nbweb" in root.text
        asset = await _http_get("http://127.0.0.1:29905/favicon.svg")
        assert asset.status_code == 200
        assert "<svg" in asset.text
        # Unknown SPA route falls back to index.html.
        spa = await _http_get("http://127.0.0.1:29905/sessions/abc")
        assert spa.status_code == 200
        assert "nbweb" in spa.text
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_static_rejects_path_traversal(
    bus: MagicMock, tmp_path: Path
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("ok")
    secret = tmp_path / "secret.txt"
    secret.write_text("classified")
    channel = _ch(bus, static_dist_path=dist, port=29906)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        resp = await _http_get("http://127.0.0.1:29906/../secret.txt")
        # Normalized by httpx into /secret.txt → falls back to index.html, not 'classified'.
        assert "classified" not in resp.text
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_unknown_route_returns_404(bus: MagicMock) -> None:
    channel = _ch(bus, port=29907)
    server_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.3)
    try:
        resp = await _http_get("http://127.0.0.1:29907/api/unknown")
        assert resp.status_code == 404
    finally:
        await channel.stop()
        await server_task


@pytest.mark.asyncio
async def test_api_token_pool_purges_expired(bus: MagicMock, tmp_path: Path) -> None:
    sm = _seed_session(tmp_path)
    channel = _ch(bus, session_manager=sm, port=29908)
    # Don't start a server — directly inject and validate.
    import time as _time
    channel._api_tokens["expired"] = _time.monotonic() - 1
    channel._api_tokens["live"] = _time.monotonic() + 60

    class _FakeReq:
        path = "/api/sessions"
        headers = {"Authorization": "Bearer expired"}

    assert channel._check_api_token(_FakeReq()) is False

    class _LiveReq:
        path = "/api/sessions"
        headers = {"Authorization": "Bearer live"}

    assert channel._check_api_token(_LiveReq()) is True
