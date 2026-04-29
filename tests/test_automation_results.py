from __future__ import annotations

from nanobot.automation_results import (
    DEFAULT_ACTION_FAILURE_CODE,
    DEFAULT_ACTION_RESULT_STATUS,
    ActionFailure,
    ActionVisibility,
    MailImportantThreadsDetails,
    MailImportantThreadsResult,
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