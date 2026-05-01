from __future__ import annotations

from pathlib import Path

import pytest

from nanobot.automation_results import (
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
from nanobot.bus.events import InboundMessage
from nanobot.command.builtin import build_help_text, cmd_mail
from nanobot.command.router import CommandContext
from nanobot.session.manager import SessionManager


class _Runner:
    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []

    async def list_important_threads(self, session_key: str, **kwargs):
        self.calls.append(("list", (session_key,), kwargs))
        return MailImportantThreadsResult(
            action_id="mail-list-1",
            status="completed",
            title="Important mail summary ready",
            summary="2 important threads were found.",
            next_step="Choose a thread to summarize in more detail.",
            details=MailImportantThreadsDetails(
                total_candidates=2,
                threads=[
                    MailThreadSummary(
                        thread_id="thread-1",
                        subject="Budget follow-up",
                        sender_summary="Alice <alice@example.com>",
                        last_update_at="2026-05-01T10:00:00Z",
                    )
                ],
            ),
        )

    async def summarize_threads(self, session_key: str, **kwargs):
        self.calls.append(("thread", (session_key,), kwargs))
        return MailSummarizeThreadsResult(
            action_id="mail-thread-1",
            status="completed",
            title="Thread summaries ready",
            summary="Summaries were generated for 1 threads.",
            next_step="Create a reply draft for the thread that needs follow-up.",
            details=MailThreadSummariesDetails(
                threads=[
                    MailThreadDigest(
                        thread_id="thread-1",
                        subject="Budget follow-up",
                        summary="Alice is waiting for approval before noon.",
                        urgency="high",
                    )
                ]
            ),
        )

    async def create_draft(self, session_key: str, request):
        self.calls.append(("draft", (session_key, request), {}))
        return MailCreateDraftResult(
            action_id="mail-draft-1",
            status="completed",
            title="Draft ready",
            summary="Draft created for alice@example.com.",
            next_step="Review the draft before requesting send approval.",
            details=MailCreateDraftDetails(
                draft_id="draft-1",
                preview=MailDraftPreview(
                    subject=request.subject,
                    body_preview=request.body,
                    to_recipients=request.to_recipients,
                ),
            ),
        )

    async def request_send_approval(self, session_key: str, request):
        self.calls.append(("send", (session_key, request), {}))
        return MailSendMessageResult(
            action_id="mail-send-approval-1",
            status="waiting_approval",
            title="Mail send approval required",
            summary="Approval required before sending 'Budget Follow-up' to alice@example.com, bob@example.com.",
            next_step="Approve or deny the pending mail send request.",
            details=MailSendMessageDetails(
                draft_id=request.draft_id,
                preview=MailDraftPreview(
                    subject=request.subject,
                    body_preview=request.body,
                    to_recipients=request.to_recipients,
                ),
            ),
        )

    async def request_send_from_latest_draft(self, session_key: str):
        self.calls.append(("send-latest", (session_key,), {}))
        return MailSendMessageResult(
            action_id="mail-send-approval-2",
            status="waiting_approval",
            title="Mail send approval required",
            summary="Approval required before sending 'Latest subject' to alice@example.com.",
            next_step="Approve or deny the pending mail send request.",
            details=MailSendMessageDetails(
                draft_id="draft-123",
                preview=MailDraftPreview(
                    subject="Latest subject",
                    body_preview="Latest body",
                    to_recipients=["alice@example.com"],
                ),
            ),
        )

    async def approve_send(self, session_key: str):
        self.calls.append(("approve", (session_key,), {}))
        return MailSendMessageResult(
            action_id="mail-send-1",
            status="completed",
            title="Message sent",
            summary="alice@example.com로 메일을 발송했습니다. 제목은 'Latest subject' 입니다.",
            details=MailSendMessageDetails(
                draft_id="draft-123",
                message_id="message-123",
                preview=MailDraftPreview(
                    subject="Latest subject",
                    body_preview="Latest body",
                    to_recipients=["alice@example.com"],
                ),
            ),
        )

    async def deny_send(self, session_key: str):
        self.calls.append(("deny", (session_key,), {}))
        return MailSendMessageResult(
            action_id="mail-send-denied-1",
            status="rejected",
            title="Mail send cancelled",
            summary="The pending mail send request was cancelled.",
            details=MailSendMessageDetails(
                draft_id="draft-123",
                preview=MailDraftPreview(
                    subject="Latest subject",
                    body_preview="Latest body",
                    to_recipients=["alice@example.com"],
                ),
            ),
        )


def _make_ctx(tmp_path: Path, raw: str) -> CommandContext:
    sessions = SessionManager(tmp_path)
    runner = _Runner()

    class _Loop:
        def __init__(self):
            self.sessions = sessions
            self.mail_automation_runner = runner

    loop = _Loop()
    msg = InboundMessage(channel="cli", sender_id="u1", chat_id="direct", content=raw)
    session = loop.sessions.get_or_create(msg.session_key)
    ctx = CommandContext(msg=msg, session=session, key=msg.session_key, raw=raw, loop=loop)
    return ctx


@pytest.mark.asyncio
async def test_cmd_mail_list_uses_runner_and_formats_threads(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, "/mail list is:unread newer_than:2d")

    out = await cmd_mail(ctx)

    assert "Important mail summary ready" in out.content
    assert "Budget follow-up" in out.content
    assert ctx.loop.mail_automation_runner.calls[0][0] == "list"
    assert ctx.loop.mail_automation_runner.calls[0][2]["search_query"] == "is:unread newer_than:2d"


@pytest.mark.asyncio
async def test_cmd_mail_draft_parses_structured_args(tmp_path: Path) -> None:
    ctx = _make_ctx(
        tmp_path,
        '/mail draft --to alice@example.com,bob@example.com --subject "Budget Follow-up" --body "Sharing revised notes" --cc finance@example.com --thread thread-1',
    )

    out = await cmd_mail(ctx)

    assert "Draft ready" in out.content
    assert "Subject: Budget Follow-up" in out.content
    call = ctx.loop.mail_automation_runner.calls[0]
    request = call[1][1]
    assert call[0] == "draft"
    assert request.to_recipients == ["alice@example.com", "bob@example.com"]
    assert request.cc_recipients == ["finance@example.com"]
    assert request.thread_id == "thread-1"


@pytest.mark.asyncio
async def test_cmd_mail_send_requests_approval_for_explicit_payload(tmp_path: Path) -> None:
    ctx = _make_ctx(
        tmp_path,
        '/mail send --to alice@example.com,bob@example.com --subject "Budget Follow-up" --body "Sharing revised notes" --draft draft-123',
    )

    out = await cmd_mail(ctx)

    assert "Mail send approval required" in out.content
    assert "Approve or deny the pending mail send request." in out.content
    call = ctx.loop.mail_automation_runner.calls[0]
    request = call[1][1]
    assert call[0] == "send"
    assert request.to_recipients == ["alice@example.com", "bob@example.com"]
    assert request.draft_id == "draft-123"


@pytest.mark.asyncio
async def test_cmd_mail_approve_uses_runner(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path, "/mail approve")

    out = await cmd_mail(ctx)

    assert "Message sent" in out.content
    assert "Latest subject" in out.content
    assert ctx.loop.mail_automation_runner.calls[0][0] == "approve"


def test_build_help_text_mentions_mail_command() -> None:
    assert "/mail — Run Gmail pilot read-only and draft actions" in build_help_text()
    assert "/mail send|approve|deny — Resolve Gmail send approval flow" in build_help_text()