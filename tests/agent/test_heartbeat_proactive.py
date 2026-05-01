from __future__ import annotations

from datetime import datetime

from nanobot.heartbeat.proactive import (
    HeartbeatProactivePolicy,
    build_proactive_context,
    decide_heartbeat_target,
)


def test_build_proactive_context_includes_digest_sources() -> None:
    sessions = [
        {
            "key": "telegram:alpha",
            "metadata": {
                "task_summary": {
                    "title": "Mail send approval required",
                    "status": "waiting-approval",
                    "next_step_hint": "Review the pending approval request.",
                },
                "action_result": {
                    "domain": "mail",
                    "action": "list_messages",
                    "status": "completed",
                    "summary": "읽지 않은 중요 메일 2개가 있습니다.",
                },
            },
        },
        {
            "key": "websocket:beta",
            "metadata": {
                "task_summary": {
                    "title": "Resume calendar sync",
                    "status": "blocked",
                    "next_step_hint": "Reopen the interrupted session and continue the task.",
                },
                "action_result": {
                    "domain": "calendar",
                    "action": "list_events",
                    "status": "completed",
                    "summary": "오늘 일정은 14:00-14:30 Nanobot webui calendar validation입니다.",
                },
            },
        },
    ]

    context = build_proactive_context(sessions, max_digest_items=3)

    assert "Current proactive context:" in context
    assert "Waiting approvals:" in context
    assert "Blocked tasks:" in context
    assert "Recent calendar summary:" in context
    assert "Recent mail summary:" in context


def test_decide_heartbeat_target_prefers_recent_external_channel_outside_quiet_hours() -> None:
    sessions = [
        {
            "key": "telegram:chat-1",
            "metadata": {"owner_profile": {"timezone": "Asia/Seoul"}},
        },
        {
            "key": "websocket:76a4e3",
            "metadata": {"owner_profile": {"timezone": "Asia/Seoul"}},
        },
    ]

    decision = decide_heartbeat_target(
        sessions,
        {"telegram", "websocket"},
        policy=HeartbeatProactivePolicy(webui_first=True),
    )

    assert decision.channel == "telegram"
    assert decision.chat_id == "chat-1"
    assert decision.suppressed is False


def test_decide_heartbeat_target_prefers_webui_during_quiet_hours_when_available() -> None:
    sessions = [
        {
            "key": "telegram:chat-1",
            "metadata": {"owner_profile": {"timezone": "Asia/Seoul"}},
        },
        {
            "key": "websocket:76a4e3",
            "metadata": {"owner_profile": {"timezone": "Asia/Seoul"}},
        },
    ]

    decision = decide_heartbeat_target(
        sessions,
        {"telegram", "websocket"},
        policy=HeartbeatProactivePolicy(
            webui_first=True,
            quiet_hours_enabled=True,
            quiet_hours_start_local_time="22:30",
            quiet_hours_end_local_time="07:30",
            quiet_hours_allowed_channels=("websocket",),
        ),
        now=datetime.fromisoformat("2026-05-01T23:15:00+09:00"),
        fallback_timezone="Asia/Seoul",
    )

    assert decision.channel == "websocket"
    assert decision.chat_id == "76a4e3"
    assert decision.suppressed is False


def test_decide_heartbeat_target_suppresses_push_during_quiet_hours() -> None:
    sessions = [
        {
            "key": "telegram:chat-1",
            "metadata": {"owner_profile": {"timezone": "Asia/Seoul"}},
        }
    ]

    decision = decide_heartbeat_target(
        sessions,
        {"telegram"},
        policy=HeartbeatProactivePolicy(
            webui_first=True,
            quiet_hours_enabled=True,
            quiet_hours_start_local_time="22:30",
            quiet_hours_end_local_time="07:30",
            quiet_hours_allowed_channels=("websocket",),
        ),
        now=datetime.fromisoformat("2026-05-01T23:15:00+09:00"),
        fallback_timezone="Asia/Seoul",
    )

    assert decision.channel == "telegram"
    assert decision.chat_id == "chat-1"
    assert decision.suppressed is True
    assert decision.reason == "quiet_hours"


def test_decide_heartbeat_target_allows_webui_during_quiet_hours() -> None:
    sessions = [
        {
            "key": "websocket:76a4e3",
            "metadata": {"owner_profile": {"timezone": "Asia/Seoul"}},
        }
    ]

    decision = decide_heartbeat_target(
        sessions,
        {"websocket"},
        policy=HeartbeatProactivePolicy(
            webui_first=True,
            quiet_hours_enabled=True,
            quiet_hours_start_local_time="22:30",
            quiet_hours_end_local_time="07:30",
            quiet_hours_allowed_channels=("websocket",),
        ),
        now=datetime.fromisoformat("2026-05-01T23:15:00+09:00"),
        fallback_timezone="Asia/Seoul",
    )

    assert decision.channel == "websocket"
    assert decision.chat_id == "76a4e3"
    assert decision.suppressed is False