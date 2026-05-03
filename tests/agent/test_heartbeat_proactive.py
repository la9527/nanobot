from __future__ import annotations

from datetime import datetime

from nanobot.heartbeat.proactive import (
    HeartbeatProactivePolicy,
    build_proactive_context,
    decide_heartbeat_target,
    should_suppress_repeated_proactive_delivery,
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
                    "title": "Calendar credentials need attention",
                    "status": "blocked",
                    "next_step_hint": "Reconnect Google Calendar credentials in n8n.",
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


def test_build_proactive_context_ignores_closed_approval_rejections() -> None:
    sessions = [
        {
            "key": "telegram:alpha",
            "metadata": {
                "task_summary": {
                    "title": "Calendar create cancelled",
                    "status": "blocked",
                    "next_step_hint": "Review the proposed event and request approval again when ready.",
                },
                "action_result": {
                    "domain": "calendar",
                    "action": "create_event",
                    "status": "rejected",
                    "title": "Calendar create cancelled",
                    "summary": "The pending calendar create request was cancelled.",
                    "error": {"code": "approval_rejected"},
                },
            },
        }
    ]

    context = build_proactive_context(sessions, max_digest_items=3)

    assert context == ""


def test_build_proactive_context_ignores_generic_interrupted_session_followups() -> None:
    sessions = [
        {
            "key": "api:primary-user",
            "metadata": {
                "task_summary": {
                    "title": "API session follow-up",
                    "status": "blocked",
                    "origin_channel": "api",
                    "next_step_hint": "Reopen the interrupted session and continue the task.",
                }
            },
        },
        {
            "key": "websocket:browser",
            "metadata": {
                "task_summary": {
                    "title": "API 세션 후속 작업 2건이 대기",
                    "status": "blocked",
                    "origin_channel": "websocket",
                    "next_step_hint": "Reopen the interrupted session and continue the task.",
                }
            },
        },
    ]

    context = build_proactive_context(sessions, max_digest_items=3)

    assert context == ""


def test_build_proactive_context_keeps_actionable_blocked_tasks() -> None:
    sessions = [
        {
            "key": "telegram:alpha",
            "metadata": {
                "task_summary": {
                    "title": "Calendar credentials need attention",
                    "status": "blocked",
                    "origin_channel": "telegram",
                    "next_step_hint": "Reconnect Google Calendar credentials in n8n.",
                }
            },
        }
    ]

    context = build_proactive_context(sessions, max_digest_items=3)

    assert "Blocked tasks:" in context
    assert "Calendar credentials need attention" in context


def test_should_suppress_repeated_proactive_delivery_for_same_summary() -> None:
    previous = {
        "status": "delivered",
        "category": "briefing",
        "summary": "가장 시급한 작업은 없습니다.",
    }

    assert should_suppress_repeated_proactive_delivery(
        previous,
        response="가장 시급한 작업은 없습니다.",
        category="briefing",
    )


def test_should_keep_new_proactive_delivery_when_summary_changes() -> None:
    previous = {
        "status": "delivered",
        "category": "briefing",
        "summary": "가장 시급한 작업은 없습니다.",
    }

    assert not should_suppress_repeated_proactive_delivery(
        previous,
        response="승인 대기 중인 캘린더 수정 요청이 있습니다.",
        category="briefing",
    )


def test_should_continue_suppressing_after_duplicate_suppression() -> None:
    previous = {
        "status": "suppressed",
        "suppressed_reason": "duplicate",
        "category": "briefing",
        "summary": "가장 시급한 작업은 없습니다.",
    }

    assert should_suppress_repeated_proactive_delivery(
        previous,
        response="가장 시급한 작업은 없습니다.",
        category="briefing",
    )


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