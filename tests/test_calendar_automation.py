from __future__ import annotations

import httpx
import pytest

from nanobot.automation.calendar import (
    CalendarAutomationSessionRunner,
    CalendarCreateRequest,
    N8NCalendarAutomationClient,
    N8NCalendarAutomationConfig,
)
from nanobot.session.manager import SessionManager


def _mock_client_factory(handler):
    class _Client:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            return await handler(url, json, headers)

    return _Client


@pytest.mark.asyncio
async def test_list_events_normalizes_calendar_summary_response(monkeypatch) -> None:
    async def _handler(url, json, headers):
        assert url == "http://127.0.0.1:5678/webhook/assistant-automation"
        assert json["message"] == "오늘 일정 요약해줘"
        return httpx.Response(
            200,
            json={
                "reply": "오늘 일정은 10:00 프로젝트 리뷰, 15:00 치과입니다.",
                "action": "calendar-summary",
                "count": 2,
                "events": [
                    {
                        "event_id": "event-1",
                        "title": "프로젝트 리뷰",
                        "start_at": "2026-05-01T10:00:00+09:00",
                        "end_at": "2026-05-01T11:00:00+09:00",
                    },
                    {
                        "event_id": "event-2",
                        "title": "치과",
                        "start_at": "2026-05-01T15:00:00+09:00",
                        "end_at": "2026-05-01T16:00:00+09:00",
                    },
                ],
            },
        )

    monkeypatch.setattr(
        "nanobot.automation.calendar.httpx.AsyncClient",
        _mock_client_factory(_handler),
    )

    client = N8NCalendarAutomationClient(
        N8NCalendarAutomationConfig(base_url="http://127.0.0.1:5678")
    )

    result = await client.list_events()

    assert result.status == "completed"
    assert result.details.total_candidates == 2
    assert "10:00 프로젝트 리뷰" in result.summary
    assert result.details.events[0].title == "프로젝트 리뷰"


@pytest.mark.asyncio
async def test_find_conflicts_marks_empty_window_as_available(monkeypatch) -> None:
    async def _handler(url, json, headers):
        return httpx.Response(
            200,
            json={
                "reply": "오늘 등록된 일정이 없습니다.",
                "action": "calendar-summary",
                "count": 0,
            },
        )

    monkeypatch.setattr(
        "nanobot.automation.calendar.httpx.AsyncClient",
        _mock_client_factory(_handler),
    )

    client = N8NCalendarAutomationClient(
        N8NCalendarAutomationConfig(base_url="http://127.0.0.1:5678")
    )
    today = "2026-05-01T15:00:00+09:00"
    today_end = "2026-05-01T16:00:00+09:00"

    result = await client.find_conflicts(start_at=today, end_at=today_end)

    assert result.status == "completed"
    assert result.details.available is True


@pytest.mark.asyncio
async def test_find_conflicts_detects_overlapping_structured_events(monkeypatch) -> None:
    async def _handler(url, json, headers):
        assert json["timeMin"].startswith("2026-05-02T00:00:00")
        assert json["timeMax"].startswith("2026-05-02T23:59:59")
        return httpx.Response(
            200,
            json={
                "reply": "5월 2일 일정은 15:30-16:30 치과입니다.",
                "action": "calendar-summary",
                "count": 1,
                "events": [
                    {
                        "event_id": "event-2",
                        "title": "치과",
                        "start_at": "2026-05-02T15:30:00+09:00",
                        "end_at": "2026-05-02T16:30:00+09:00",
                    }
                ],
            },
        )

    monkeypatch.setattr(
        "nanobot.automation.calendar.httpx.AsyncClient",
        _mock_client_factory(_handler),
    )

    client = N8NCalendarAutomationClient(
        N8NCalendarAutomationConfig(base_url="http://127.0.0.1:5678")
    )

    result = await client.find_conflicts(
        start_at="2026-05-02T15:00:00+09:00",
        end_at="2026-05-02T16:00:00+09:00",
    )

    assert result.status == "blocked"
    assert result.details.reason == "overlap_detected"
    assert result.details.conflicting_events[0].title == "치과"


@pytest.mark.asyncio
async def test_find_conflicts_blocks_when_legacy_summary_has_count_but_no_events(monkeypatch) -> None:
    async def _handler(url, json, headers):
        return httpx.Response(
            200,
            json={
                "reply": "5월 2일 일정은 15:30-16:30 치과입니다.",
                "action": "calendar-summary",
                "count": 1,
            },
        )

    monkeypatch.setattr(
        "nanobot.automation.calendar.httpx.AsyncClient",
        _mock_client_factory(_handler),
    )

    client = N8NCalendarAutomationClient(
        N8NCalendarAutomationConfig(base_url="http://127.0.0.1:5678")
    )

    result = await client.find_conflicts(
        start_at="2026-05-02T15:00:00+09:00",
        end_at="2026-05-02T16:00:00+09:00",
    )

    assert result.status == "blocked"
    assert result.details.reason == "structured_conflict_data_unavailable"


@pytest.mark.asyncio
async def test_create_event_normalizes_success_response(monkeypatch) -> None:
    async def _handler(url, json, headers):
        assert url == "http://127.0.0.1:5678/webhook/assistant-calendar-create"
        assert json["title"] == "치과"
        return httpx.Response(
            200,
            json={
                "reply": "5.2. 15:00부터 5.2. 16:00까지 치과 일정을 생성했습니다.",
                "action": "calendar-create",
                "event_id": "event-123",
            },
        )

    monkeypatch.setattr(
        "nanobot.automation.calendar.httpx.AsyncClient",
        _mock_client_factory(_handler),
    )

    client = N8NCalendarAutomationClient(
        N8NCalendarAutomationConfig(base_url="http://127.0.0.1:5678")
    )
    result = await client.create_event(
        CalendarCreateRequest(
            title="치과",
            start_at="2026-05-02T15:00:00+09:00",
            end_at="2026-05-02T16:00:00+09:00",
            description="정기 검진",
        )
    )

    assert result.status == "completed"
    assert result.details.event_id == "event-123"


@pytest.mark.asyncio
async def test_session_runner_persists_calendar_create_approval_and_approval_summary(tmp_path) -> None:
    class _Client:
        async def create_event(self, request):
            raise AssertionError("create_event should not be called during approval request")

        async def list_events(self, **kwargs):
            raise AssertionError("list_events is not used in this test")

        async def find_conflicts(self, **kwargs):
            raise AssertionError("find_conflicts is not used in this test")

        def _action_id(self, prefix: str) -> str:
            return f"{prefix}-test"

    runner = CalendarAutomationSessionRunner(SessionManager(tmp_path), _Client())

    result = await runner.request_create_approval(
        "websocket:calendar-demo",
        CalendarCreateRequest(
            title="치과",
            start_at="2026-05-02T15:00:00+09:00",
            end_at="2026-05-02T16:00:00+09:00",
            description="정기 검진",
        ),
    )

    restored = runner.sessions.read_session_file("websocket:calendar-demo")

    assert result.status == "waiting_approval"
    assert restored is not None
    assert restored["metadata"]["approval_summary"]["status"] == "pending"
    assert restored["metadata"]["action_result"]["action"] == "create_event"
    assert restored["metadata"]["calendar_create_approval"]["title"] == "치과"
    pending = restored["metadata"]["calendar_pending_interaction"]
    assert pending["kind"] == "create_approval"
    assert pending["status"] == "pending"
    assert pending["buttons"] == [["승인", "취소"]]
    assert pending["request"]["title"] == "치과"


@pytest.mark.asyncio
async def test_session_runner_deny_without_pending_does_not_create_event(tmp_path) -> None:
    class _Client:
        async def create_event(self, request):
            raise AssertionError("create_event should not be called when cancelling without pending approval")

        async def list_events(self, **kwargs):
            raise AssertionError("list_events is not used in this test")

        async def find_conflicts(self, **kwargs):
            raise AssertionError("find_conflicts is not used in this test")

        def _action_id(self, prefix: str) -> str:
            return f"{prefix}-test"

    runner = CalendarAutomationSessionRunner(SessionManager(tmp_path), _Client())

    result = await runner.deny_create("websocket:calendar-demo")
    restored = runner.sessions.read_session_file("websocket:calendar-demo")

    assert result.status == "blocked"
    assert "no pending calendar create approval to cancel" in result.summary
    assert restored is not None
    assert restored["metadata"]["action_result"]["action_id"] == "calendar-create-no-pending-cancel-test"