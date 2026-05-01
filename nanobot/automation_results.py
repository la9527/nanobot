from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ACTION_RESULT_STATUSES = (
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "rejected",
    "blocked",
)
DEFAULT_ACTION_RESULT_STATUS = "completed"

ACTION_FAILURE_CODES = (
    "approval_needed",
    "approval_rejected",
    "authentication_needed",
    "invalid_input",
    "not_found",
    "service_unavailable",
    "executor_unavailable",
    "rate_limited",
    "unknown_failure",
)
DEFAULT_ACTION_FAILURE_CODE = "unknown_failure"

ACTION_VISIBILITY_SURFACES = (
    "thread",
    "sidebar",
    "linked_session",
    "external_channel",
)
DEFAULT_ACTION_VISIBILITY_SURFACE = "thread"


def normalize_action_result_status(value: Any) -> str:
    status = str(value or DEFAULT_ACTION_RESULT_STATUS).strip().lower()
    if status not in ACTION_RESULT_STATUSES:
        return DEFAULT_ACTION_RESULT_STATUS
    return status


def normalize_action_failure_code(value: Any) -> str:
    code = str(value or DEFAULT_ACTION_FAILURE_CODE).strip().lower()
    if code not in ACTION_FAILURE_CODES:
        return DEFAULT_ACTION_FAILURE_CODE
    return code


def normalize_action_visibility_surface(value: Any) -> str:
    surface = str(value or DEFAULT_ACTION_VISIBILITY_SURFACE).strip().lower()
    if surface not in ACTION_VISIBILITY_SURFACES:
        return DEFAULT_ACTION_VISIBILITY_SURFACE
    return surface


class _AutomationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionFailure(_AutomationModel):
    code: str = DEFAULT_ACTION_FAILURE_CODE
    message: str
    retryable: bool = False
    detail: str | None = None

    @field_validator("code", mode="before")
    @classmethod
    def _normalize_code(cls, value: Any) -> str:
        return normalize_action_failure_code(value)


class ActionVisibility(_AutomationModel):
    surfaces: list[str] = Field(default_factory=lambda: [DEFAULT_ACTION_VISIBILITY_SURFACE])
    badge: str | None = None
    inline_status: str | None = None
    linked_summary: str | None = None
    approval_summary: str | None = None

    @field_validator("surfaces", mode="before")
    @classmethod
    def _normalize_surfaces(cls, value: Any) -> list[str]:
        if value is None:
            return [DEFAULT_ACTION_VISIBILITY_SURFACE]
        raw_items = [value] if isinstance(value, str) else list(value)
        normalized: list[str] = []
        for item in raw_items:
            surface = normalize_action_visibility_surface(item)
            if surface not in normalized:
                normalized.append(surface)
        return normalized or [DEFAULT_ACTION_VISIBILITY_SURFACE]


class ActionReferences(_AutomationModel):
    thread_id: str | None = None
    draft_id: str | None = None
    message_id: str | None = None
    session_key: str | None = None
    canonical_owner_id: str | None = None


class ActionResult(_AutomationModel):
    action_id: str
    domain: str
    action: str
    status: str = DEFAULT_ACTION_RESULT_STATUS
    title: str
    summary: str
    details: dict[str, Any] | None = None
    next_step: str | None = None
    visibility: ActionVisibility = Field(default_factory=ActionVisibility)
    references: ActionReferences = Field(default_factory=ActionReferences)
    error: ActionFailure | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, value: Any) -> str:
        return normalize_action_result_status(value)


class MailThreadSummary(_AutomationModel):
    thread_id: str
    subject: str
    sender_summary: str
    last_update_at: str
    unread: bool = False
    importance_hint: str | None = None
    snippet: str | None = None


class MailImportantThreadsDetails(_AutomationModel):
    mailbox_label: str | None = None
    total_candidates: int | None = None
    threads: list[MailThreadSummary] = Field(default_factory=list)


class MailImportantThreadsResult(ActionResult):
    domain: Literal["mail"] = "mail"
    action: Literal["list_important_threads"] = "list_important_threads"
    details: MailImportantThreadsDetails


class MailThreadDigest(_AutomationModel):
    thread_id: str
    subject: str
    summary: str
    urgency: Literal["low", "medium", "high"] | None = None
    recommended_next_action: str | None = None


class MailThreadSummariesDetails(_AutomationModel):
    summary_style: str | None = None
    urgency_threshold: str | None = None
    threads: list[MailThreadDigest] = Field(default_factory=list)


class MailSummarizeThreadsResult(ActionResult):
    domain: Literal["mail"] = "mail"
    action: Literal["summarize_threads"] = "summarize_threads"
    details: MailThreadSummariesDetails


class MailDraftPreview(_AutomationModel):
    subject: str
    body_preview: str
    to_recipients: list[str] = Field(default_factory=list)
    cc_recipients: list[str] = Field(default_factory=list)
    bcc_recipients: list[str] = Field(default_factory=list)
    thread_id: str | None = None


class MailCreateDraftDetails(_AutomationModel):
    draft_id: str | None = None
    preview: MailDraftPreview


class MailCreateDraftResult(ActionResult):
    domain: Literal["mail"] = "mail"
    action: Literal["create_draft"] = "create_draft"
    details: MailCreateDraftDetails


class MailSendMessageDetails(_AutomationModel):
    draft_id: str | None = None
    message_id: str | None = None
    preview: MailDraftPreview


class MailSendMessageResult(ActionResult):
    domain: Literal["mail"] = "mail"
    action: Literal["send_message"] = "send_message"
    details: MailSendMessageDetails


class CalendarEventPreview(_AutomationModel):
    title: str
    start_at: str
    end_at: str
    location: str | None = None
    description: str | None = None


class CalendarEventSummary(_AutomationModel):
    event_id: str | None = None
    title: str
    start_at: str
    end_at: str
    all_day: bool = False
    location: str | None = None


class CalendarListEventsDetails(_AutomationModel):
    window_label: str | None = None
    summary_text: str | None = None
    total_candidates: int | None = None
    events: list[CalendarEventSummary] = Field(default_factory=list)


class CalendarListEventsResult(ActionResult):
    domain: Literal["calendar"] = "calendar"
    action: Literal["list_events"] = "list_events"
    details: CalendarListEventsDetails


class CalendarFindConflictsDetails(_AutomationModel):
    requested_start_at: str
    requested_end_at: str
    available: bool = False
    checked_window_label: str | None = None
    reason: str | None = None
    total_candidates: int | None = None
    conflicting_events: list[CalendarEventSummary] = Field(default_factory=list)


class CalendarFindConflictsResult(ActionResult):
    domain: Literal["calendar"] = "calendar"
    action: Literal["find_conflicts"] = "find_conflicts"
    details: CalendarFindConflictsDetails


class CalendarCreateEventDetails(_AutomationModel):
    event_id: str | None = None
    preview: CalendarEventPreview


class CalendarCreateEventResult(ActionResult):
    domain: Literal["calendar"] = "calendar"
    action: Literal["create_event"] = "create_event"
    details: CalendarCreateEventDetails


__all__ = [
    "ACTION_FAILURE_CODES",
    "ACTION_RESULT_STATUSES",
    "ACTION_VISIBILITY_SURFACES",
    "ActionFailure",
    "ActionReferences",
    "ActionResult",
    "ActionVisibility",
    "CalendarCreateEventDetails",
    "CalendarCreateEventResult",
    "CalendarEventPreview",
    "CalendarEventSummary",
    "CalendarFindConflictsDetails",
    "CalendarFindConflictsResult",
    "CalendarListEventsDetails",
    "CalendarListEventsResult",
    "MailImportantThreadsDetails",
    "MailImportantThreadsResult",
    "MailCreateDraftDetails",
    "MailCreateDraftResult",
    "MailDraftPreview",
    "MailSendMessageDetails",
    "MailSendMessageResult",
    "MailSummarizeThreadsResult",
    "MailThreadDigest",
    "MailThreadSummariesDetails",
    "MailThreadSummary",
    "normalize_action_failure_code",
    "normalize_action_result_status",
    "normalize_action_visibility_surface",
]