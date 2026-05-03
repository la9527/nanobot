from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field

from nanobot.automation_results import (
    ActionFailure,
    ActionReferences,
    ActionVisibility,
    CalendarCreateEventDetails,
    CalendarCreateEventResult,
    CalendarDeleteEventDetails,
    CalendarDeleteEventResult,
    CalendarEventPreview,
    CalendarEventSummary,
    CalendarFindConflictsDetails,
    CalendarFindConflictsResult,
    CalendarListEventsDetails,
    CalendarListEventsResult,
    CalendarUpdateEventDetails,
    CalendarUpdateEventResult,
)
from nanobot.i18n import translate as _t
from nanobot.session.manager import SessionManager


CALENDAR_CREATE_APPROVAL_METADATA_KEY = "calendar_create_approval"
CALENDAR_UPDATE_APPROVAL_METADATA_KEY = "calendar_update_approval"
CALENDAR_DELETE_APPROVAL_METADATA_KEY = "calendar_delete_approval"
CALENDAR_PENDING_INTERACTION_METADATA_KEY = "calendar_pending_interaction"


class _CalendarAutomationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class N8NCalendarAutomationConfig(_CalendarAutomationModel):
    base_url: str
    webhook_token: str | None = None
    summary_path: str = "webhook/assistant-automation"
    create_path: str = "webhook/assistant-calendar-create"
    update_path: str = "webhook/assistant-calendar-update"
    delete_path: str = "webhook/assistant-calendar-delete"
    timeout_s: float = 20.0
    timezone: str = "Asia/Seoul"
    locale: str = "ko-KR"

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
    ) -> "N8NCalendarAutomationConfig | None":
        scope = os.environ if env is None else env
        base_url = str(scope.get("N8N_BASE_URL") or scope.get("N8N_EDITOR_BASE_URL") or "").strip()
        if not base_url:
            return None
        return cls(
            base_url=base_url,
            webhook_token=str(scope.get("N8N_WEBHOOK_TOKEN") or "").strip() or None,
            summary_path=str(scope.get("N8N_WEBHOOK_PATH") or "webhook/assistant-automation").strip(),
            create_path=str(scope.get("N8N_CALENDAR_CREATE_WEBHOOK_PATH") or "webhook/assistant-calendar-create").strip(),
            update_path=str(scope.get("N8N_CALENDAR_UPDATE_WEBHOOK_PATH") or "webhook/assistant-calendar-update").strip(),
            delete_path=str(scope.get("N8N_CALENDAR_DELETE_WEBHOOK_PATH") or "webhook/assistant-calendar-delete").strip(),
            timezone=str(scope.get("CALENDAR_TIMEZONE") or "Asia/Seoul").strip() or "Asia/Seoul",
            locale=str(scope.get("CALENDAR_LOCALE") or scope.get("NANOBOT_LOCALE") or "ko-KR").strip() or "ko-KR",
        )


class CalendarCreateRequest(_CalendarAutomationModel):
    title: str = Field(min_length=1)
    start_at: str = Field(min_length=1)
    end_at: str = Field(min_length=1)
    description: str | None = None
    location: str | None = None


class CalendarUpdateRequest(_CalendarAutomationModel):
    search_title: str = Field(min_length=1)
    new_title: str | None = None
    start_at: str = Field(min_length=1)
    end_at: str = Field(min_length=1)
    search_time_min: str = Field(min_length=1)
    search_time_max: str = Field(min_length=1)
    event_id: str | None = None


class CalendarDeleteRequest(_CalendarAutomationModel):
    search_title: str = Field(min_length=1)
    search_time_min: str = Field(min_length=1)
    search_time_max: str = Field(min_length=1)
    event_id: str | None = None


class N8NCalendarAutomationClient:
    """Direct n8n-backed Google Calendar automation seam for the phase-1 calendar pilot."""

    def __init__(self, config: N8NCalendarAutomationConfig):
        self.config = config

    async def list_events(
        self,
        *,
        message: str | None = None,
        channel: str = "websocket",
        session_id: str | None = None,
        user_id: str | None = None,
        time_min: str | None = None,
        time_max: str | None = None,
        window_label: str | None = None,
    ) -> CalendarListEventsResult:
        action_id = self._action_id("calendar-list")
        try:
            payload = await self._post_json(
                self.config.summary_path,
                {
                    "message": message or _t("calendar.webhook.summary_request", locale=self.config.locale),
                    "channel": channel,
                    "session_id": session_id,
                    "user_id": user_id,
                    "timezone": self.config.timezone,
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "window_label": window_label,
                },
            )
        except httpx.HTTPError as exc:
            return self._list_failure_result(action_id, exc)

        reply = self._coerce_text(payload.get("reply")) if isinstance(payload, dict) else None
        count = self._coerce_int(payload.get("count")) if isinstance(payload, dict) else None
        events = self._parse_event_summaries(payload.get("events")) if isinstance(payload, dict) else []
        has_events = bool(count)
        summary = reply or _t("calendar.webhook.summary_unavailable", locale=self.config.locale)
        return CalendarListEventsResult(
            action_id=action_id,
            status="completed",
            title="Calendar summary ready" if has_events else "No events found",
            summary=summary,
            next_step="Review the schedule before planning a new event." if has_events else None,
            visibility=ActionVisibility(
                surfaces=["thread", "sidebar"],
                badge="Calendar",
                inline_status=summary,
                linked_summary=summary,
            ),
            details=CalendarListEventsDetails(
                window_label=window_label or self._default_window_label(time_min, time_max),
                summary_text=summary,
                total_candidates=count or 0,
                events=events,
            ),
        )

    async def find_conflicts(
        self,
        *,
        start_at: str,
        end_at: str,
        message: str | None = None,
        channel: str = "websocket",
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> CalendarFindConflictsResult:
        requested_start = self._parse_datetime(start_at)
        requested_end = self._parse_datetime(end_at)
        window_start, window_end, window_label = self._day_window_for_datetime(requested_start)
        list_result = await self.list_events(
            message=message,
            channel=channel,
            session_id=session_id,
            user_id=user_id,
            time_min=window_start.isoformat(),
            time_max=window_end.isoformat(),
            window_label=window_label,
        )
        if list_result.status != "completed":
            return CalendarFindConflictsResult(
                action_id=self._action_id("calendar-conflicts"),
                status="blocked",
                title="Conflict check unavailable",
                summary=list_result.summary,
                next_step="Review the calendar connection or retry the conflict check.",
                visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Calendar blocked"),
                details=CalendarFindConflictsDetails(
                    requested_start_at=start_at,
                    requested_end_at=end_at,
                    available=False,
                    checked_window_label=window_label,
                    reason="calendar_list_unavailable",
                    total_candidates=list_result.details.total_candidates,
                ),
                error=list_result.error,
            )

        if (list_result.details.total_candidates or 0) > 0 and not list_result.details.events:
            return CalendarFindConflictsResult(
                action_id=self._action_id("calendar-conflicts"),
                status="blocked",
                title="Conflict check needs structured events",
                summary="The current calendar summary response does not include structured event times yet.",
                next_step="Update the assistant-automation workflow so it returns an events array, then retry the conflict check.",
                visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Conflict blocked"),
                details=CalendarFindConflictsDetails(
                    requested_start_at=start_at,
                    requested_end_at=end_at,
                    available=False,
                    checked_window_label=window_label,
                    reason="structured_conflict_data_unavailable",
                    total_candidates=list_result.details.total_candidates,
                    conflicting_events=[],
                ),
                error=ActionFailure(
                    code="executor_unavailable",
                    message="Structured event times are missing from the calendar summary webhook response.",
                    retryable=False,
                ),
            )

        conflicts = self._find_overlapping_events(
            requested_start,
            requested_end,
            list_result.details.events,
        )
        if not conflicts:
            return CalendarFindConflictsResult(
                action_id=self._action_id("calendar-conflicts"),
                status="completed",
                title="No conflicts found",
                summary=f"No overlapping events were found in the {window_label} calendar window.",
                next_step="Request calendar create approval when you are ready.",
                visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Slot available"),
                details=CalendarFindConflictsDetails(
                    requested_start_at=start_at,
                    requested_end_at=end_at,
                    available=True,
                    checked_window_label=window_label,
                    reason="no_conflicts_found",
                    total_candidates=list_result.details.total_candidates or 0,
                    conflicting_events=[],
                ),
            )

        conflict_titles = ", ".join(event.title for event in conflicts[:3])
        extra = "" if len(conflicts) <= 3 else _t("calendar.conflict.extra_count", locale=self.config.locale, count=len(conflicts) - 3)
        return CalendarFindConflictsResult(
            action_id=self._action_id("calendar-conflicts"),
            status="blocked",
            title="Conflicts found",
            summary=f"The requested slot overlaps with {conflict_titles}{extra}.",
            next_step="Choose a different time or continue only after reviewing the conflicting events.",
            visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Conflict found"),
            details=CalendarFindConflictsDetails(
                requested_start_at=start_at,
                requested_end_at=end_at,
                available=False,
                checked_window_label=window_label,
                reason="overlap_detected",
                total_candidates=list_result.details.total_candidates,
                conflicting_events=conflicts,
            ),
            error=ActionFailure(
                code="invalid_input",
                message="The requested slot overlaps with existing calendar events.",
                retryable=False,
            ),
        )

    async def create_event(self, request: CalendarCreateRequest) -> CalendarCreateEventResult:
        action_id = self._action_id("calendar-create")
        preview = CalendarEventPreview(
            title=request.title,
            start_at=request.start_at,
            end_at=request.end_at,
            location=request.location,
            description=request.description,
        )
        try:
            payload = await self._post_json(
                self.config.create_path,
                {
                    "title": request.title,
                    "start_at": request.start_at,
                    "end_at": request.end_at,
                    "message": request.description or "",
                    "location": request.location or "",
                },
            )
        except httpx.HTTPError as exc:
            return self._create_failure_result(action_id, preview, exc)

        payload_failure = self._payload_failure(payload)
        if payload_failure is not None:
            return CalendarCreateEventResult(
                action_id=action_id,
                status="blocked" if payload_failure.code in {"authentication_needed", "not_found"} else "failed",
                title="Calendar create failed",
                summary=payload_failure.message,
                visibility=ActionVisibility(surfaces=["thread"], badge="Calendar failed"),
                details=CalendarCreateEventDetails(preview=preview),
                error=payload_failure,
            )

        event_id = self._coerce_text(payload.get("event_id")) if isinstance(payload, dict) else None
        summary = self._coerce_text(payload.get("reply")) if isinstance(payload, dict) else None
        return CalendarCreateEventResult(
            action_id=action_id,
            status="completed",
            title="Calendar event created",
            summary=summary or f"Created calendar event '{request.title}'.",
            visibility=ActionVisibility(
                surfaces=["thread", "sidebar", "linked_session"],
                badge="Calendar created",
                inline_status="Calendar event created",
                linked_summary=request.title,
            ),
            references=ActionReferences(message_id=event_id),
            details=CalendarCreateEventDetails(event_id=event_id, preview=preview),
        )

    async def update_event(self, request: CalendarUpdateRequest, target: CalendarEventSummary | None = None) -> CalendarUpdateEventResult:
        action_id = self._action_id("calendar-update")
        preview = CalendarEventPreview(
            title=request.new_title or request.search_title,
            start_at=request.start_at,
            end_at=request.end_at,
        )
        try:
            payload = await self._post_json(
                self.config.update_path,
                {
                    "search_title": request.search_title,
                    "new_title": request.new_title or request.search_title,
                    "start_at": request.start_at,
                    "end_at": request.end_at,
                    "search_time_min": request.search_time_min,
                    "search_time_max": request.search_time_max,
                    "event_id": request.event_id or "",
                },
            )
        except httpx.HTTPError as exc:
            return self._update_failure_result(action_id, preview, target, exc)

        payload_failure = self._payload_failure(payload)
        if payload_failure is not None:
            return CalendarUpdateEventResult(
                action_id=action_id,
                status="blocked" if payload_failure.code in {"authentication_needed", "not_found"} else "failed",
                title="Calendar update failed",
                summary=payload_failure.message,
                visibility=ActionVisibility(surfaces=["thread"], badge="Calendar failed"),
                details=CalendarUpdateEventDetails(target=target, preview=preview),
                error=payload_failure,
            )

        event_id = self._coerce_text(payload.get("event_id")) if isinstance(payload, dict) else None
        summary = self._coerce_text(payload.get("reply")) if isinstance(payload, dict) else None
        return CalendarUpdateEventResult(
            action_id=action_id,
            status="completed",
            title="Calendar event updated",
            summary=summary or f"Updated calendar event '{request.search_title}'.",
            visibility=ActionVisibility(
                surfaces=["thread", "sidebar", "linked_session"],
                badge="Calendar updated",
                inline_status="Calendar event updated",
                linked_summary=request.search_title,
            ),
            references=ActionReferences(message_id=event_id or request.event_id),
            details=CalendarUpdateEventDetails(event_id=event_id or request.event_id, target=target, preview=preview),
        )

    async def delete_event(self, request: CalendarDeleteRequest, target: CalendarEventSummary) -> CalendarDeleteEventResult:
        action_id = self._action_id("calendar-delete")
        try:
            payload = await self._post_json(
                self.config.delete_path,
                {
                    "search_title": request.search_title,
                    "search_time_min": request.search_time_min,
                    "search_time_max": request.search_time_max,
                    "event_id": request.event_id or "",
                    "timezone": self.config.timezone,
                },
            )
        except httpx.HTTPError as exc:
            return self._delete_failure_result(action_id, target, exc)

        payload_failure = self._payload_failure(payload)
        if payload_failure is not None:
            return CalendarDeleteEventResult(
                action_id=action_id,
                status="blocked" if payload_failure.code in {"authentication_needed", "not_found"} else "failed",
                title="Calendar delete failed",
                summary=payload_failure.message,
                visibility=ActionVisibility(surfaces=["thread"], badge="Calendar failed"),
                details=CalendarDeleteEventDetails(target=target),
                error=payload_failure,
            )

        event_id = self._coerce_text(payload.get("event_id")) if isinstance(payload, dict) else None
        summary = self._coerce_text(payload.get("reply")) if isinstance(payload, dict) else None
        return CalendarDeleteEventResult(
            action_id=action_id,
            status="completed",
            title="Calendar event deleted",
            summary=summary or f"Deleted calendar event '{target.title}'.",
            visibility=ActionVisibility(
                surfaces=["thread", "sidebar", "linked_session"],
                badge="Calendar deleted",
                inline_status="Calendar event deleted",
                linked_summary=target.title,
            ),
            references=ActionReferences(message_id=event_id or request.event_id),
            details=CalendarDeleteEventDetails(event_id=event_id or request.event_id, target=target),
        )

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.config.webhook_token:
            headers["Authorization"] = f"Bearer {self.config.webhook_token}"
        url = self._build_url(path)
        async with httpx.AsyncClient(timeout=self.config.timeout_s) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.is_error:
                request = response.request or httpx.Request("POST", url)
                raise httpx.HTTPStatusError(
                    f"Calendar automation webhook returned HTTP {response.status_code}",
                    request=request,
                    response=response,
                )
        body = response.json()
        return body if isinstance(body, dict) else {"reply": str(body)}

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _list_failure_result(
        self,
        action_id: str,
        exc: httpx.HTTPError,
    ) -> CalendarListEventsResult:
        failure = self._map_http_error(exc)
        return CalendarListEventsResult(
            action_id=action_id,
            status="blocked" if failure.code == "authentication_needed" else "failed",
            title="Calendar summary unavailable",
            summary=failure.message,
            visibility=ActionVisibility(surfaces=["thread"], badge="Calendar failed"),
            details=CalendarListEventsDetails(window_label="today", total_candidates=0),
            error=failure,
        )

    def _create_failure_result(
        self,
        action_id: str,
        preview: CalendarEventPreview,
        exc: httpx.HTTPError,
    ) -> CalendarCreateEventResult:
        failure = self._map_http_error(exc)
        return CalendarCreateEventResult(
            action_id=action_id,
            status="blocked" if failure.code == "authentication_needed" else "failed",
            title="Calendar create failed",
            summary=failure.message,
            visibility=ActionVisibility(surfaces=["thread"], badge="Calendar failed"),
            details=CalendarCreateEventDetails(preview=preview),
            error=failure,
        )

    def _update_failure_result(
        self,
        action_id: str,
        preview: CalendarEventPreview,
        target: CalendarEventSummary | None,
        exc: httpx.HTTPError,
    ) -> CalendarUpdateEventResult:
        failure = self._map_http_error(exc)
        return CalendarUpdateEventResult(
            action_id=action_id,
            status="blocked" if failure.code == "authentication_needed" else "failed",
            title="Calendar update failed",
            summary=failure.message,
            visibility=ActionVisibility(surfaces=["thread"], badge="Calendar failed"),
            details=CalendarUpdateEventDetails(target=target, preview=preview),
            error=failure,
        )

    def _delete_failure_result(
        self,
        action_id: str,
        target: CalendarEventSummary,
        exc: httpx.HTTPError,
    ) -> CalendarDeleteEventResult:
        failure = self._map_http_error(exc)
        return CalendarDeleteEventResult(
            action_id=action_id,
            status="blocked" if failure.code == "authentication_needed" else "failed",
            title="Calendar delete failed",
            summary=failure.message,
            visibility=ActionVisibility(surfaces=["thread"], badge="Calendar failed"),
            details=CalendarDeleteEventDetails(target=target),
            error=failure,
        )

    def _map_http_error(self, exc: httpx.HTTPError) -> ActionFailure:
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            if status_code in {401, 403}:
                return ActionFailure(
                    code="authentication_needed",
                    message="Google Calendar credentials need attention before this action can continue.",
                    retryable=False,
                )
            if status_code == 404:
                return ActionFailure(
                    code="executor_unavailable",
                    message="The calendar automation webhook is not available.",
                    retryable=False,
                )
            if status_code == 429:
                return ActionFailure(
                    code="rate_limited",
                    message="The calendar automation endpoint is rate limited right now.",
                    retryable=True,
                )
            return ActionFailure(
                code="service_unavailable",
                message="The calendar automation endpoint could not complete the request.",
                retryable=status_code >= 500,
                detail=f"HTTP {status_code}",
            )
        if isinstance(exc, httpx.TimeoutException):
            return ActionFailure(
                code="service_unavailable",
                message="The calendar automation endpoint timed out.",
                retryable=True,
            )
        return ActionFailure(
            code="service_unavailable",
            message="The calendar automation endpoint is temporarily unavailable.",
            retryable=True,
        )

    def _payload_failure(self, payload: dict[str, Any]) -> ActionFailure | None:
        action = self._coerce_text(payload.get("action")) if isinstance(payload, dict) else None
        if not action or not (action.endswith("-error") or action.endswith("-not-found")):
            return None
        message = (
            self._coerce_text(payload.get("reply"))
            or self._coerce_text(payload.get("error"))
            or "Google Calendar workflow execution failed."
        )
        if action.endswith("-not-found"):
            return ActionFailure(code="not_found", message=message, retryable=False)
        if bool(payload.get("needs_reconnect")):
            return ActionFailure(code="authentication_needed", message=message, retryable=False)
        return ActionFailure(code="service_unavailable", message=message, retryable=True)

    def _action_id(self, prefix: str) -> str:
        from uuid import uuid4

        return f"{prefix}-{uuid4().hex[:10]}"

    def _coerce_text(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _coerce_int(self, value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _local_date_label(self, value: str) -> str:
        try:
            return datetime.fromisoformat(value).date().isoformat()
        except ValueError:
            return value[:10]

    def _default_window_label(self, time_min: str | None, time_max: str | None) -> str:
        if time_min:
            return self._local_date_label(time_min)
        if time_max:
            return self._local_date_label(time_max)
        return "today"

    def _parse_datetime(self, value: str) -> datetime:
        normalized = value.strip().replace(" ", "T")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(self.config.timezone))
        return parsed

    def _day_window_for_datetime(self, value: datetime) -> tuple[datetime, datetime, str]:
        local = value.astimezone(ZoneInfo(self.config.timezone))
        day_start = datetime.combine(local.date(), time.min, tzinfo=local.tzinfo)
        day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
        return day_start, day_end, local.date().isoformat()

    def _parse_event_summaries(self, value: Any) -> list[CalendarEventSummary]:
        if not isinstance(value, list):
            return []
        events: list[CalendarEventSummary] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            try:
                events.append(CalendarEventSummary(
                    event_id=self._coerce_text(item.get("event_id") or item.get("id")),
                    title=self._coerce_text(item.get("title") or item.get("summary")) or _t("calendar.event.untitled", locale=self.config.locale),
                    start_at=self._coerce_text(item.get("start_at")) or "",
                    end_at=self._coerce_text(item.get("end_at")) or "",
                    all_day=bool(item.get("all_day")),
                    location=self._coerce_text(item.get("location")),
                ))
            except Exception:
                continue
        return [event for event in events if event.start_at and event.end_at]

    def _find_overlapping_events(
        self,
        requested_start: datetime,
        requested_end: datetime,
        events: list[CalendarEventSummary],
    ) -> list[CalendarEventSummary]:
        overlaps: list[CalendarEventSummary] = []
        for event in events:
            try:
                event_start = self._parse_datetime(event.start_at)
                event_end = self._parse_datetime(event.end_at)
            except ValueError:
                continue
            if event_start < requested_end and requested_start < event_end:
                overlaps.append(event)
        return overlaps


class CalendarAutomationSessionRunner:
    """Persist calendar automation results onto a Nanobot session."""

    def __init__(self, sessions: SessionManager, client: N8NCalendarAutomationClient):
        self.sessions = sessions
        self.client = client

    async def list_events(self, session_key: str) -> CalendarListEventsResult:
        result = await self.client.list_events(
            channel=self._channel_from_session_key(session_key),
            session_id=session_key,
            user_id="primary-user",
        )
        self._persist_result(session_key, result)
        return result

    async def find_conflicts(
        self,
        session_key: str,
        *,
        start_at: str,
        end_at: str,
    ) -> CalendarFindConflictsResult:
        result = await self.client.find_conflicts(
            start_at=start_at,
            end_at=end_at,
            channel=self._channel_from_session_key(session_key),
            session_id=session_key,
            user_id="primary-user",
        )
        self._persist_result(session_key, result)
        return result

    async def request_create_approval(
        self,
        session_key: str,
        request: CalendarCreateRequest,
    ) -> CalendarCreateEventResult:
        preview = CalendarEventPreview(
            title=request.title,
            start_at=request.start_at,
            end_at=request.end_at,
            location=request.location,
            description=request.description,
        )
        result = CalendarCreateEventResult(
            action_id=self.client._action_id("calendar-create-approval"),
            status="waiting_approval",
            title="Calendar create approval required",
            summary=f"Approval required before creating '{request.title}'.",
            next_step="Approve or deny the pending calendar create request.",
            visibility=ActionVisibility(
                surfaces=["thread", "sidebar", "linked_session"],
                badge="Approval pending",
                inline_status="Calendar create approval pending",
                linked_summary=request.title,
                approval_summary="Calendar create approval pending",
            ),
            details=CalendarCreateEventDetails(preview=preview),
            error=ActionFailure(
                code="approval_needed",
                message="Approval is required before creating this calendar event.",
                retryable=True,
            ),
        )
        session = self.sessions.get_or_create(session_key)
        session.metadata[CALENDAR_CREATE_APPROVAL_METADATA_KEY] = request.model_dump(mode="json")
        pending_updated_at = datetime.now(timezone.utc).isoformat()
        locale = self._locale()
        session.metadata[CALENDAR_PENDING_INTERACTION_METADATA_KEY] = {
            "id": result.action_id,
            "kind": "create_approval",
            "status": "pending",
            "question": result.summary,
            "buttons": [[
                _t("calendar.buttons.approve", locale=locale),
                _t("calendar.buttons.cancel", locale=locale),
            ]],
            "request": request.model_dump(mode="json"),
            "created_at": pending_updated_at,
            "updated_at": pending_updated_at,
        }
        self.sessions.set_action_result(session, result)
        self.sessions.set_approval_summary(
            session,
            {
                "status": "pending",
                "channel": self._channel_from_session_key(session_key),
                "tool_name": "calendar.create_event",
                "tool_call_id": result.action_id,
                "message_id": None,
                "prompt_preview": self._approval_prompt(request),
            },
        )
        session.add_message("assistant", result.summary)
        self.sessions.save(session)
        return result

    def _locale(self) -> str:
        config = getattr(self.client, "config", None)
        locale = getattr(config, "locale", None)
        return str(locale or "ko-KR")

    async def approve_create(self, session_key: str) -> CalendarCreateEventResult:
        request = self._pending_create_request(session_key)
        if request is None:
            return self._persist_ephemeral_result(
                session_key,
                CalendarCreateEventResult(
                    action_id=self.client._action_id("calendar-create-no-pending"),
                    status="blocked",
                    title="No pending calendar approval",
                    summary="There is no pending calendar create approval in this session.",
                    next_step="Request calendar create approval first.",
                    visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Calendar blocked"),
                    details=CalendarCreateEventDetails(
                        preview=CalendarEventPreview(title="(Untitled)", start_at="", end_at=""),
                    ),
                    error=ActionFailure(
                        code="not_found",
                        message="No pending calendar approval is available.",
                        retryable=False,
                    ),
                ),
            )
        result = await self.client.create_event(request)
        session = self.sessions.get_or_create(session_key)
        session.metadata.pop(CALENDAR_CREATE_APPROVAL_METADATA_KEY, None)
        session.metadata.pop(CALENDAR_PENDING_INTERACTION_METADATA_KEY, None)
        self.sessions.clear_approval_summary(session)
        self.sessions.set_action_result(session, result)
        session.add_message("assistant", result.summary)
        self.sessions.save(session)
        return result

    async def deny_create(self, session_key: str) -> CalendarCreateEventResult:
        request = self._pending_create_request(session_key)
        if request is None:
            return self._persist_ephemeral_result(
                session_key,
                CalendarCreateEventResult(
                    action_id=self.client._action_id("calendar-create-no-pending-cancel"),
                    status="blocked",
                    title="No pending calendar approval",
                    summary="There is no pending calendar create approval to cancel in this session.",
                    next_step="Request calendar create approval first.",
                    visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Calendar blocked"),
                    details=CalendarCreateEventDetails(
                        preview=CalendarEventPreview(title="(Untitled)", start_at="", end_at=""),
                    ),
                    error=ActionFailure(
                        code="not_found",
                        message="No pending calendar approval is available.",
                        retryable=False,
                    ),
                ),
            )
        preview = CalendarEventPreview(
            title=request.title,
            start_at=request.start_at,
            end_at=request.end_at,
            location=request.location,
            description=request.description,
        )
        result = CalendarCreateEventResult(
            action_id=self.client._action_id("calendar-create-denied"),
            status="rejected",
            title="Calendar create cancelled",
            summary="The pending calendar create request was cancelled.",
            next_step="Review the proposed event and request approval again when ready.",
            visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Calendar cancelled"),
            details=CalendarCreateEventDetails(preview=preview),
            error=ActionFailure(
                code="approval_rejected",
                message="The pending calendar create request was cancelled.",
                retryable=False,
            ),
        )
        session = self.sessions.get_or_create(session_key)
        session.metadata.pop(CALENDAR_CREATE_APPROVAL_METADATA_KEY, None)
        session.metadata.pop(CALENDAR_PENDING_INTERACTION_METADATA_KEY, None)
        self.sessions.clear_approval_summary(session)
        self.sessions.set_action_result(session, result)
        session.add_message("assistant", result.summary)
        self.sessions.save(session)
        return result

    async def request_update_approval(
        self,
        session_key: str,
        request: CalendarUpdateRequest,
        target: CalendarEventSummary | None = None,
    ) -> CalendarUpdateEventResult:
        preview = CalendarEventPreview(
            title=request.new_title or request.search_title,
            start_at=request.start_at,
            end_at=request.end_at,
        )
        result = CalendarUpdateEventResult(
            action_id=self.client._action_id("calendar-update-approval"),
            status="waiting_approval",
            title="Calendar update approval required",
            summary=f"Approval required before updating '{request.search_title}'.",
            next_step="Approve or deny the pending calendar update request.",
            visibility=ActionVisibility(
                surfaces=["thread", "sidebar", "linked_session"],
                badge="Approval pending",
                inline_status="Calendar update approval pending",
                linked_summary=request.search_title,
                approval_summary="Calendar update approval pending",
            ),
            details=CalendarUpdateEventDetails(event_id=request.event_id, target=target, preview=preview),
            error=ActionFailure(
                code="approval_needed",
                message="Approval is required before updating this calendar event.",
                retryable=True,
            ),
        )
        session = self.sessions.get_or_create(session_key)
        session.metadata[CALENDAR_UPDATE_APPROVAL_METADATA_KEY] = {
            "request": request.model_dump(mode="json"),
            "target": target.model_dump(mode="json") if target is not None else None,
        }
        pending_updated_at = datetime.now(timezone.utc).isoformat()
        locale = self._locale()
        session.metadata[CALENDAR_PENDING_INTERACTION_METADATA_KEY] = {
            "id": result.action_id,
            "kind": "update_approval",
            "status": "pending",
            "question": result.summary,
            "buttons": [[
                _t("calendar.buttons.approve", locale=locale),
                _t("calendar.buttons.cancel", locale=locale),
            ]],
            "request": request.model_dump(mode="json"),
            "target": target.model_dump(mode="json") if target is not None else None,
            "created_at": pending_updated_at,
            "updated_at": pending_updated_at,
        }
        self.sessions.set_action_result(session, result)
        self.sessions.set_approval_summary(session, {
            "status": "pending",
            "channel": self._channel_from_session_key(session_key),
            "tool_name": "calendar.update_event",
            "tool_call_id": result.action_id,
            "message_id": None,
            "prompt_preview": self._update_approval_prompt(request),
        })
        session.add_message("assistant", result.summary)
        self.sessions.save(session)
        return result

    async def request_delete_approval(
        self,
        session_key: str,
        request: CalendarDeleteRequest,
        target: CalendarEventSummary,
    ) -> CalendarDeleteEventResult:
        result = CalendarDeleteEventResult(
            action_id=self.client._action_id("calendar-delete-approval"),
            status="waiting_approval",
            title="Calendar delete approval required",
            summary=f"Approval required before deleting '{target.title}'.",
            next_step="Approve or deny the pending calendar delete request.",
            visibility=ActionVisibility(
                surfaces=["thread", "sidebar", "linked_session"],
                badge="Approval pending",
                inline_status="Calendar delete approval pending",
                linked_summary=target.title,
                approval_summary="Calendar delete approval pending",
            ),
            details=CalendarDeleteEventDetails(event_id=request.event_id, target=target),
            error=ActionFailure(
                code="approval_needed",
                message="Approval is required before deleting this calendar event.",
                retryable=True,
            ),
        )
        session = self.sessions.get_or_create(session_key)
        session.metadata[CALENDAR_DELETE_APPROVAL_METADATA_KEY] = {
            "request": request.model_dump(mode="json"),
            "target": target.model_dump(mode="json"),
        }
        pending_updated_at = datetime.now(timezone.utc).isoformat()
        locale = self._locale()
        session.metadata[CALENDAR_PENDING_INTERACTION_METADATA_KEY] = {
            "id": result.action_id,
            "kind": "delete_approval",
            "status": "pending",
            "question": result.summary,
            "buttons": [[
                _t("calendar.buttons.approve", locale=locale),
                _t("calendar.buttons.cancel", locale=locale),
            ]],
            "request": request.model_dump(mode="json"),
            "target": target.model_dump(mode="json"),
            "created_at": pending_updated_at,
            "updated_at": pending_updated_at,
        }
        self.sessions.set_action_result(session, result)
        self.sessions.set_approval_summary(session, {
            "status": "pending",
            "channel": self._channel_from_session_key(session_key),
            "tool_name": "calendar.delete_event",
            "tool_call_id": result.action_id,
            "message_id": None,
            "prompt_preview": self._delete_approval_prompt(target),
        })
        session.add_message("assistant", result.summary)
        self.sessions.save(session)
        return result

    async def approve_update(self, session_key: str) -> CalendarUpdateEventResult:
        pending = self._pending_update_request(session_key)
        if pending is None:
            return self._persist_ephemeral_result(session_key, self._no_pending_update_result())
        request, target = pending
        result = await self.client.update_event(request, target)
        session = self.sessions.get_or_create(session_key)
        session.metadata.pop(CALENDAR_UPDATE_APPROVAL_METADATA_KEY, None)
        session.metadata.pop(CALENDAR_PENDING_INTERACTION_METADATA_KEY, None)
        self.sessions.clear_approval_summary(session)
        self.sessions.set_action_result(session, result)
        session.add_message("assistant", result.summary)
        self.sessions.save(session)
        return result

    async def approve_delete(self, session_key: str) -> CalendarDeleteEventResult:
        pending = self._pending_delete_request(session_key)
        if pending is None:
            return self._persist_ephemeral_result(session_key, self._no_pending_delete_result())
        request, target = pending
        result = await self.client.delete_event(request, target)
        session = self.sessions.get_or_create(session_key)
        session.metadata.pop(CALENDAR_DELETE_APPROVAL_METADATA_KEY, None)
        session.metadata.pop(CALENDAR_PENDING_INTERACTION_METADATA_KEY, None)
        self.sessions.clear_approval_summary(session)
        self.sessions.set_action_result(session, result)
        session.add_message("assistant", result.summary)
        self.sessions.save(session)
        return result

    async def deny_update(self, session_key: str) -> CalendarUpdateEventResult:
        pending = self._pending_update_request(session_key)
        if pending is None:
            return self._persist_ephemeral_result(session_key, self._no_pending_update_result(cancel=True))
        request, target = pending
        preview = CalendarEventPreview(title=request.new_title or request.search_title, start_at=request.start_at, end_at=request.end_at)
        result = CalendarUpdateEventResult(
            action_id=self.client._action_id("calendar-update-denied"),
            status="rejected",
            title="Calendar update cancelled",
            summary="The pending calendar update request was cancelled.",
            next_step="Request the update again if you still want to change the event.",
            visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Calendar cancelled"),
            details=CalendarUpdateEventDetails(event_id=request.event_id, target=target, preview=preview),
            error=ActionFailure(code="approval_rejected", message="The pending calendar update request was cancelled."),
        )
        session = self.sessions.get_or_create(session_key)
        session.metadata.pop(CALENDAR_UPDATE_APPROVAL_METADATA_KEY, None)
        session.metadata.pop(CALENDAR_PENDING_INTERACTION_METADATA_KEY, None)
        self.sessions.clear_approval_summary(session)
        self.sessions.set_action_result(session, result)
        session.add_message("assistant", result.summary)
        self.sessions.save(session)
        return result

    async def deny_delete(self, session_key: str) -> CalendarDeleteEventResult:
        pending = self._pending_delete_request(session_key)
        if pending is None:
            return self._persist_ephemeral_result(session_key, self._no_pending_delete_result(cancel=True))
        request, target = pending
        result = CalendarDeleteEventResult(
            action_id=self.client._action_id("calendar-delete-denied"),
            status="rejected",
            title="Calendar delete cancelled",
            summary="The pending calendar delete request was cancelled.",
            next_step="Request the delete again if you still want to remove the event.",
            visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Calendar cancelled"),
            details=CalendarDeleteEventDetails(event_id=request.event_id, target=target),
            error=ActionFailure(code="approval_rejected", message="The pending calendar delete request was cancelled."),
        )
        session = self.sessions.get_or_create(session_key)
        session.metadata.pop(CALENDAR_DELETE_APPROVAL_METADATA_KEY, None)
        session.metadata.pop(CALENDAR_PENDING_INTERACTION_METADATA_KEY, None)
        self.sessions.clear_approval_summary(session)
        self.sessions.set_action_result(session, result)
        session.add_message("assistant", result.summary)
        self.sessions.save(session)
        return result

    def _persist_result(
        self,
        session_key: str,
        result: CalendarListEventsResult | CalendarFindConflictsResult | CalendarCreateEventResult | CalendarUpdateEventResult | CalendarDeleteEventResult,
    ) -> None:
        session = self.sessions.get_or_create(session_key)
        self.sessions.set_action_result(session, result)
        if result.summary:
            session.add_message("assistant", result.summary)
        self.sessions.save(session)

    def _persist_ephemeral_result(self, session_key: str, result):
        self._persist_result(session_key, result)
        return result

    def _pending_create_request(self, session_key: str) -> CalendarCreateRequest | None:
        session = self.sessions.get_or_create(session_key)
        payload = session.metadata.get(CALENDAR_CREATE_APPROVAL_METADATA_KEY)
        if not isinstance(payload, dict):
            return None
        try:
            return CalendarCreateRequest.model_validate(payload)
        except Exception:
            return None

    def _pending_update_request(self, session_key: str) -> tuple[CalendarUpdateRequest, CalendarEventSummary | None] | None:
        session = self.sessions.get_or_create(session_key)
        payload = session.metadata.get(CALENDAR_UPDATE_APPROVAL_METADATA_KEY)
        if not isinstance(payload, dict):
            return None
        request_payload = payload.get("request")
        if not isinstance(request_payload, dict):
            return None
        try:
            request = CalendarUpdateRequest.model_validate(request_payload)
            target_payload = payload.get("target")
            target = CalendarEventSummary.model_validate(target_payload) if isinstance(target_payload, dict) else None
            return request, target
        except Exception:
            return None

    def _pending_delete_request(self, session_key: str) -> tuple[CalendarDeleteRequest, CalendarEventSummary] | None:
        session = self.sessions.get_or_create(session_key)
        payload = session.metadata.get(CALENDAR_DELETE_APPROVAL_METADATA_KEY)
        if not isinstance(payload, dict):
            return None
        request_payload = payload.get("request")
        target_payload = payload.get("target")
        if not isinstance(request_payload, dict) or not isinstance(target_payload, dict):
            return None
        try:
            return CalendarDeleteRequest.model_validate(request_payload), CalendarEventSummary.model_validate(target_payload)
        except Exception:
            return None

    def _no_pending_update_result(self, *, cancel: bool = False) -> CalendarUpdateEventResult:
        return CalendarUpdateEventResult(
            action_id=self.client._action_id("calendar-update-no-pending-cancel" if cancel else "calendar-update-no-pending"),
            status="blocked",
            title="No pending calendar update approval",
            summary="There is no pending calendar update approval in this session.",
            next_step="Request calendar update approval first.",
            visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Calendar blocked"),
            details=CalendarUpdateEventDetails(preview=CalendarEventPreview(title="(Untitled)", start_at="", end_at="")),
            error=ActionFailure(code="not_found", message="No pending calendar update approval is available."),
        )

    def _no_pending_delete_result(self, *, cancel: bool = False) -> CalendarDeleteEventResult:
        return CalendarDeleteEventResult(
            action_id=self.client._action_id("calendar-delete-no-pending-cancel" if cancel else "calendar-delete-no-pending"),
            status="blocked",
            title="No pending calendar delete approval",
            summary="There is no pending calendar delete approval in this session.",
            next_step="Request calendar delete approval first.",
            visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Calendar blocked"),
            details=CalendarDeleteEventDetails(target=CalendarEventSummary(title="(Untitled)", start_at="", end_at="")),
            error=ActionFailure(code="not_found", message="No pending calendar delete approval is available."),
        )

    @staticmethod
    def _channel_from_session_key(session_key: str) -> str:
        return session_key.split(":", 1)[0] if ":" in session_key else "websocket"

    @staticmethod
    def _approval_prompt(request: CalendarCreateRequest) -> str:
        return (
            "Approval required before creating this calendar event. "
            f"Title: {request.title}. Start: {request.start_at}. End: {request.end_at}. "
            "Use /calendar approve to create it or /calendar deny to cancel."
        )

    @staticmethod
    def _update_approval_prompt(request: CalendarUpdateRequest) -> str:
        return (
            "Approval required before updating this calendar event. "
            f"Title: {request.search_title}. New start: {request.start_at}. New end: {request.end_at}. "
            "Use /calendar approve to update it or /calendar deny to cancel."
        )

    @staticmethod
    def _delete_approval_prompt(target: CalendarEventSummary) -> str:
        return (
            "Approval required before deleting this calendar event. "
            f"Title: {target.title}. Start: {target.start_at}. End: {target.end_at}. "
            "Use /calendar approve to delete it or /calendar deny to cancel."
        )