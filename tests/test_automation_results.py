from __future__ import annotations

from nanobot.automation_results import (
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
    DEFAULT_ACTION_FAILURE_CODE,
    DEFAULT_ACTION_RESULT_STATUS,
    ActionFailure,
    ActionVisibility,
    MailCreateDraftDetails,
    MailCreateDraftResult,
    MailDraftPreview,
    MailImportantThreadsDetails,
    MailImportantThreadsResult,
    MailSendMessageDetails,
    MailSendMessageResult,
    MailSummarizeThreadsResult,
    MailThreadDigest,
    MailThreadSummariesDetails,
    MailThreadSummary,
)


def test_action_failure_and_visibility_normalize_unknown_values() -> None:
    failure = ActionFailure(code="unexpected_vendor_error", message="boom")
    visibility = ActionVisibility(surfaces=["thread", "unknown-surface", "sidebar", "thread"])

    assert failure.code == DEFAULT_ACTION_FAILURE_CODE
    assert visibility.surfaces == ["thread", "sidebar"]


def test_mail_list_important_threads_result_serializes_thread_summaries() -> None:
    result = MailImportantThreadsResult(
        action_id="mail-act-1",
        status="unexpected-status",
        title="Important mail summary ready",
        summary="2 important threads were found.",
        next_step="Choose a thread to summarize in more detail.",
        details=MailImportantThreadsDetails(
            mailbox_label="INBOX",
            total_candidates=2,
            threads=[
                MailThreadSummary(
                    thread_id="thread-1",
                    subject="Budget follow-up",
                    sender_summary="Alice <alice@example.com>",
                    last_update_at="2026-04-30T09:30:00Z",
                    unread=True,
                    importance_hint="high",
                    snippet="Need your confirmation before noon.",
                )
            ],
        ),
    )

    payload = result.model_dump()

    assert result.status == DEFAULT_ACTION_RESULT_STATUS
    assert payload["domain"] == "mail"
    assert payload["action"] == "list_important_threads"
    assert payload["details"]["threads"][0]["thread_id"] == "thread-1"
    assert payload["details"]["threads"][0]["importance_hint"] == "high"


def test_mail_summarize_threads_result_serializes_digest_items() -> None:
    result = MailSummarizeThreadsResult(
        action_id="mail-act-2",
        status="completed",
        title="Thread summaries ready",
        summary="Summaries were generated for 2 threads.",
        details=MailThreadSummariesDetails(
            summary_style="brief",
            urgency_threshold="medium",
            threads=[
                MailThreadDigest(
                    thread_id="thread-1",
                    subject="Budget follow-up",
                    summary="Alice is waiting for approval before noon.",
                    urgency="high",
                    recommended_next_action="Create a reply draft.",
                ),
                MailThreadDigest(
                    thread_id="thread-2",
                    subject="Travel receipt",
                    summary="Receipt was shared for reimbursement.",
                    urgency="low",
                ),
            ],
        ),
    )

    payload = result.model_dump()

    assert payload["details"]["summary_style"] == "brief"
    assert payload["details"]["threads"][0]["recommended_next_action"] == "Create a reply draft."
    assert payload["details"]["threads"][1]["urgency"] == "low"


def test_mail_create_draft_result_serializes_preview_shape() -> None:
    result = MailCreateDraftResult(
        action_id="mail-act-3",
        status="completed",
        title="Draft ready",
        summary="Draft created for alice@example.com.",
        details=MailCreateDraftDetails(
            draft_id="draft-1",
            preview=MailDraftPreview(
                subject="Budget follow-up",
                body_preview="Sharing the updated budget notes.",
                to_recipients=["alice@example.com"],
                cc_recipients=["finance@example.com"],
                thread_id="thread-1",
            ),
        ),
    )

    payload = result.model_dump()

    assert payload["action"] == "create_draft"
    assert payload["details"]["draft_id"] == "draft-1"
    assert payload["details"]["preview"]["to_recipients"] == ["alice@example.com"]
    assert payload["details"]["preview"]["thread_id"] == "thread-1"


def test_mail_send_message_result_serializes_preview_and_message_reference() -> None:
    result = MailSendMessageResult(
        action_id="mail-act-4",
        status="waiting_approval",
        title="Mail send approval required",
        summary="Approval required before sending 'Budget follow-up' to alice@example.com.",
        details=MailSendMessageDetails(
            draft_id="draft-1",
            message_id="message-1",
            preview=MailDraftPreview(
                subject="Budget follow-up",
                body_preview="Sharing the final budget note.",
                to_recipients=["alice@example.com"],
            ),
        ),
    )

    payload = result.model_dump()

    assert payload["action"] == "send_message"
    assert payload["status"] == "waiting_approval"
    assert payload["details"]["draft_id"] == "draft-1"
    assert payload["details"]["message_id"] == "message-1"
    assert payload["details"]["preview"]["subject"] == "Budget follow-up"


def test_calendar_list_events_result_serializes_summary_details() -> None:
    result = CalendarListEventsResult(
        action_id="calendar-act-1",
        status="completed",
        title="Calendar summary ready",
        summary="오늘 일정은 10:00 프로젝트 리뷰입니다.",
        details=CalendarListEventsDetails(
            window_label="today",
            summary_text="오늘 일정은 10:00 프로젝트 리뷰입니다.",
            total_candidates=1,
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

    payload = result.model_dump()

    assert payload["action"] == "list_events"
    assert payload["details"]["window_label"] == "today"
    assert payload["details"]["total_candidates"] == 1
    assert payload["details"]["events"][0]["title"] == "프로젝트 리뷰"


def test_calendar_create_event_result_serializes_preview_shape() -> None:
    result = CalendarCreateEventResult(
        action_id="calendar-act-2",
        status="waiting_approval",
        title="Calendar create approval required",
        summary="Approval required before creating '치과'.",
        details=CalendarCreateEventDetails(
            event_id="event-1",
            preview=CalendarEventPreview(
                title="치과",
                start_at="2026-05-02T15:00:00+09:00",
                end_at="2026-05-02T16:00:00+09:00",
                location="Seoul",
                description="정기 검진",
            ),
        ),
    )

    payload = result.model_dump()

    assert payload["action"] == "create_event"
    assert payload["details"]["event_id"] == "event-1"
    assert payload["details"]["preview"]["title"] == "치과"


def test_calendar_find_conflicts_result_serializes_requested_window() -> None:
    result = CalendarFindConflictsResult(
        action_id="calendar-act-3",
        status="blocked",
        title="Conflict review needed",
        summary="Structured conflict data is unavailable.",
        details=CalendarFindConflictsDetails(
            requested_start_at="2026-05-02T15:00:00+09:00",
            requested_end_at="2026-05-02T16:00:00+09:00",
            available=False,
            checked_window_label="today",
            reason="structured_conflict_data_unavailable",
            total_candidates=2,
            conflicting_events=[
                CalendarEventSummary(
                    event_id="event-1",
                    title="치과",
                    start_at="2026-05-02T15:30:00+09:00",
                    end_at="2026-05-02T16:30:00+09:00",
                )
            ],
        ),
    )

    payload = result.model_dump()

    assert payload["action"] == "find_conflicts"
    assert payload["details"]["requested_start_at"] == "2026-05-02T15:00:00+09:00"
    assert payload["details"]["reason"] == "structured_conflict_data_unavailable"
    assert payload["details"]["conflicting_events"][0]["title"] == "치과"


def test_calendar_update_event_result_serializes_target_and_preview() -> None:
    result = CalendarUpdateEventResult(
        action_id="calendar-act-4",
        status="waiting_approval",
        title="Calendar update approval required",
        summary="Approval required before updating '치과'.",
        details=CalendarUpdateEventDetails(
            event_id="event-1",
            target=CalendarEventSummary(
                event_id="event-1",
                title="치과",
                start_at="2026-05-02T15:00:00+09:00",
                end_at="2026-05-02T16:00:00+09:00",
            ),
            preview=CalendarEventPreview(
                title="치과",
                start_at="2026-05-02T16:00:00+09:00",
                end_at="2026-05-02T17:00:00+09:00",
            ),
        ),
    )

    payload = result.model_dump()

    assert payload["action"] == "update_event"
    assert payload["details"]["target"]["title"] == "치과"
    assert payload["details"]["preview"]["start_at"] == "2026-05-02T16:00:00+09:00"


def test_calendar_delete_event_result_serializes_target() -> None:
    result = CalendarDeleteEventResult(
        action_id="calendar-act-5",
        status="waiting_approval",
        title="Calendar delete approval required",
        summary="Approval required before deleting '치과'.",
        details=CalendarDeleteEventDetails(
            event_id="event-1",
            target=CalendarEventSummary(
                event_id="event-1",
                title="치과",
                start_at="2026-05-02T15:00:00+09:00",
                end_at="2026-05-02T16:00:00+09:00",
            ),
        ),
    )

    payload = result.model_dump()

    assert payload["action"] == "delete_event"
    assert payload["details"]["event_id"] == "event-1"
    assert payload["details"]["target"]["title"] == "치과"