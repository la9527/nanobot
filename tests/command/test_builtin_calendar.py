from __future__ import annotations

from pathlib import Path

import pytest

from nanobot.automation_results import (
    CalendarCreateEventDetails,
    CalendarCreateEventResult,
    CalendarEventPreview,
    CalendarEventSummary,
    CalendarFindConflictsDetails,
    CalendarFindConflictsResult,
    CalendarListEventsDetails,
    CalendarListEventsResult,
)
from nanobot.bus.events import InboundMessage
from nanobot.command.builtin import build_help_text, cmd_calendar, register_builtin_commands
from nanobot.command.router import CommandContext, CommandRouter
from nanobot.session.manager import SessionManager


class _Runner:
    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []

    async def list_events(self, session_key: str):
        self.calls.append(("today", (session_key,), {}))
        return CalendarListEventsResult(
            action_id="calendar-list-1",
            status="completed",
            title="Calendar summary ready",
            summary="오늘 일정은 10:00 프로젝트 리뷰, 15:00 치과입니다.",
            details=CalendarListEventsDetails(
                window_label="today",
                summary_text="오늘 일정은 10:00 프로젝트 리뷰, 15:00 치과입니다.",
                total_candidates=2,
                events=[
                    CalendarEventSummary(
                        event_id="event-1",
                        title="프로젝트 리뷰",
                        start_at="2026-05-01T10:00:00+09:00",
                        end_at="2026-05-01T11:00:00+09:00",
                    )
                ],
            ),
        )

    async def find_conflicts(self, session_key: str, **kwargs):
        self.calls.append(("check", (session_key,), kwargs))
        return CalendarFindConflictsResult(
            action_id="calendar-conflicts-1",
            status="completed",
            title="No conflicts found",
            summary="Today's calendar window is empty, so the requested slot looks available.",
            details=CalendarFindConflictsDetails(
                requested_start_at=kwargs["start_at"],
                requested_end_at=kwargs["end_at"],
                available=True,
                checked_window_label="today",
            ),
        )

    async def request_create_approval(self, session_key: str, request):
        self.calls.append(("create", (session_key, request), {}))
        return CalendarCreateEventResult(
            action_id="calendar-create-approval-1",
            status="waiting_approval",
            title="Calendar create approval required",
            summary="Approval required before creating '치과'.",
            next_step="Approve or deny the pending calendar create request.",
            details=CalendarCreateEventDetails(
                preview=CalendarEventPreview(
                    title=request.title,
                    start_at=request.start_at,
                    end_at=request.end_at,
                    location=request.location,
                    description=request.description,
                ),
            ),
        )

    async def approve_create(self, session_key: str):
        self.calls.append(("approve", (session_key,), {}))
        return CalendarCreateEventResult(
            action_id="calendar-create-1",
            status="completed",
            title="Calendar event created",
            summary="5.2. 15:00부터 5.2. 16:00까지 치과 일정을 생성했습니다.",
            details=CalendarCreateEventDetails(
                event_id="event-123",
                preview=CalendarEventPreview(
                    title="치과",
                    start_at="2026-05-02T15:00:00+09:00",
                    end_at="2026-05-02T16:00:00+09:00",
                    description="정기 검진",
                ),
            ),
        )

    async def deny_create(self, session_key: str):
        self.calls.append(("deny", (session_key,), {}))
        return CalendarCreateEventResult(
            action_id="calendar-create-denied-1",
            status="rejected",
            title="Calendar create cancelled",
            summary="The pending calendar create request was cancelled.",
            details=CalendarCreateEventDetails(
                preview=CalendarEventPreview(
                    title="치과",
                    start_at="2026-05-02T15:00:00+09:00",
                    end_at="2026-05-02T16:00:00+09:00",
                ),
            ),
        )


def _make_ctx(tmp_path: Path, raw: str) -> CommandContext:
    sessions = SessionManager(tmp_path)
    runner = _Runner()

    class _Loop:
        def __init__(self):
            self.sessions = sessions
            self.calendar_automation_runner = runner

    loop = _Loop()
    msg = InboundMessage(channel="cli", sender_id="u1", chat_id="direct", content=raw)
    session = loop.sessions.get_or_create(msg.session_key)
    return CommandContext(msg=msg, session=session, key=msg.session_key, raw=raw, loop=loop)


def _make_router_ctx(tmp_path: Path, raw: str, *, session_key: str = "cli:direct") -> CommandContext:
    sessions = SessionManager(tmp_path)
    runner = _Runner()

    class _Loop:
        def __init__(self):
            self.sessions = sessions
            self.calendar_automation_runner = runner

    loop = _Loop()
    msg = InboundMessage(channel="cli", sender_id="u1", chat_id="direct", content=raw, session_key_override=session_key)
    session = loop.sessions.get_or_create(session_key)
    return CommandContext(msg=msg, session=session, key=session_key, raw=raw, loop=loop)


@pytest.mark.asyncio
async def test_cmd_calendar_today_uses_runner(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, "/calendar today")

    out = await cmd_calendar(ctx)

    assert "Calendar summary ready" in out.content
    assert "10:00 프로젝트 리뷰" in out.content
    assert ctx.loop.calendar_automation_runner.calls[0][0] == "today"


@pytest.mark.asyncio
async def test_cmd_calendar_create_requests_approval(tmp_path: Path) -> None:
    ctx = _make_ctx(
        tmp_path,
        '/calendar create --title "치과" --start 2026-05-02T15:00:00+09:00 --end 2026-05-02T16:00:00+09:00 --details "정기 검진"',
    )

    out = await cmd_calendar(ctx)

    assert "Calendar create approval required" in out.content
    call = ctx.loop.calendar_automation_runner.calls[0]
    request = call[1][1]
    assert call[0] == "create"
    assert request.title == "치과"
    assert request.description == "정기 검진"


@pytest.mark.asyncio
async def test_cmd_calendar_create_prompts_for_missing_required_fields(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, '/calendar create --details "정기 검진"')

    out = await cmd_calendar(ctx)

    assert "Calendar create needs a title" in out.content
    assert out.buttons == [["취소"]]
    pending = ctx.session.metadata["calendar_create_input"]
    assert pending["expected_field"] == "title"
    assert pending["description"] == "정기 검진"


@pytest.mark.asyncio
async def test_calendar_pending_input_interceptor_collects_missing_values(tmp_path: Path) -> None:
    router = CommandRouter()
    register_builtin_commands(router)
    session_key = "cli:direct"
    create_ctx = _make_router_ctx(tmp_path, '/calendar create --details "정기 검진"', session_key=session_key)

    first = await router.dispatch(create_ctx)
    assert first is not None
    assert "Calendar create needs a title" in first.content

    title_ctx = _make_router_ctx(tmp_path, '치과', session_key=session_key)
    second = await router.dispatch(title_ctx)
    assert second is not None
    assert "Calendar create needs a start time" in second.content

    start_ctx = _make_router_ctx(tmp_path, '2026-05-02T15:00:00+09:00', session_key=session_key)
    third = await router.dispatch(start_ctx)
    assert third is not None
    assert "Calendar create needs an end time" in third.content

    end_ctx = _make_router_ctx(tmp_path, '2026-05-02T16:00:00+09:00', session_key=session_key)
    final = await router.dispatch(end_ctx)
    assert final is not None
    assert "Calendar create approval required" in final.content
    assert end_ctx.loop.calendar_automation_runner.calls[-1][0] == "create"


@pytest.mark.asyncio
async def test_cmd_calendar_approve_uses_runner(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, "/calendar approve")

    out = await cmd_calendar(ctx)

    assert "Calendar event created" in out.content
    assert "치과" in out.content
    assert ctx.loop.calendar_automation_runner.calls[0][0] == "approve"


def test_build_help_text_mentions_calendar_command() -> None:
    assert "/calendar — Run Calendar pilot read, check, and create approval actions" in build_help_text()