from __future__ import annotations

import httpx
import pytest

from nanobot.automation.mail import (
    MailAutomationSessionRunner,
    MailDraftRequest,
    MailSendRequest,
    N8NGmailAutomationClient,
    N8NGmailAutomationConfig,
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
async def test_list_important_threads_normalizes_summary_response(monkeypatch) -> None:
    async def _handler(url, json, headers):
        assert url == "http://127.0.0.1:5678/webhook/assistant-gmail-summary"
        assert json["searchQuery"] == "is:unread newer_than:2d"
        assert headers["Authorization"] == "Bearer token-123"
        return httpx.Response(
            200,
            json={
                "action": "gmail-list",
                "count": 2,
                "shownCount": 2,
                "mailboxScope": "default",
                "items": [
                    {
                        "threadId": "thread-1",
                        "subject": "Budget follow-up",
                        "sender": "Alice <alice@example.com>",
                        "date": "2026-05-01T10:00:00Z",
                        "unread": True,
                        "snippet": "Need your confirmation before lunch.",
                    },
                    {
                        "threadId": "thread-2",
                        "subject": "Travel receipt",
                        "sender": "Finance <finance@example.com>",
                        "date": "2026-05-01T09:00:00Z",
                        "hasAttachments": True,
                        "snippet": "Receipt attached for reimbursement.",
                    },
                ],
            },
        )

    monkeypatch.setattr(
        "nanobot.automation.mail.httpx.AsyncClient",
        _mock_client_factory(_handler),
    )

    client = N8NGmailAutomationClient(
        N8NGmailAutomationConfig(
            base_url="http://127.0.0.1:5678",
            webhook_token="token-123",
        )
    )

    result = await client.list_important_threads(search_query="is:unread newer_than:2d", limit=2)

    assert result.status == "completed"
    assert result.details.total_candidates == 2
    assert result.details.threads[0].importance_hint == "high"
    assert result.details.threads[1].importance_hint == "medium"


@pytest.mark.asyncio
async def test_summarize_threads_builds_digest_from_thread_payload(monkeypatch) -> None:
    async def _handler(url, json, headers):
        assert url == "http://127.0.0.1:5678/webhook/assistant-gmail-thread"
        assert json["thread_id"] == "thread-1"
        return httpx.Response(
            200,
            json={
                "action": "gmail-thread",
                "found": True,
                "threadId": "thread-1",
                "subject": "Budget follow-up",
                "messageCount": 3,
                "items": [
                    {
                        "threadId": "thread-1",
                        "sender": "Alice <alice@example.com>",
                        "subject": "Budget follow-up",
                        "snippet": "Following up on the budget approval.",
                        "body": "Following up on the budget approval. Please confirm before noon.",
                        "unread": False,
                    },
                    {
                        "threadId": "thread-1",
                        "sender": "Alice <alice@example.com>",
                        "subject": "Budget follow-up",
                        "snippet": "Please confirm before noon.",
                        "body": "Please confirm before noon so we can close the budget.",
                        "unread": True,
                    },
                ],
            },
        )

    monkeypatch.setattr(
        "nanobot.automation.mail.httpx.AsyncClient",
        _mock_client_factory(_handler),
    )

    client = N8NGmailAutomationClient(
        N8NGmailAutomationConfig(base_url="http://127.0.0.1:5678")
    )

    result = await client.summarize_threads(thread_ids=["thread-1"])

    assert result.status == "completed"
    assert result.details.threads[0].thread_id == "thread-1"
    assert result.details.threads[0].urgency == "high"
    assert result.details.threads[0].recommended_next_action == "Create a reply draft."


@pytest.mark.asyncio
async def test_create_draft_normalizes_preview_and_reference(monkeypatch) -> None:
    async def _handler(url, json, headers):
        assert url == "http://127.0.0.1:5678/webhook/assistant-gmail-draft"
        assert json["send_to"] == "alice@example.com"
        assert json["subject"] == "Budget follow-up"
        return httpx.Response(
            200,
            json={
                "action": "gmail-draft",
                "reply": "alice@example.com 수신 메일 초안을 작성했습니다. 제목은 'Budget follow-up' 입니다.",
                "draft_id": "draft-123",
            },
        )

    monkeypatch.setattr(
        "nanobot.automation.mail.httpx.AsyncClient",
        _mock_client_factory(_handler),
    )

    client = N8NGmailAutomationClient(
        N8NGmailAutomationConfig(base_url="http://127.0.0.1:5678")
    )
    request = MailDraftRequest(
        to_recipients=["alice@example.com"],
        cc_recipients=["finance@example.com"],
        subject="Budget follow-up",
        body="Sharing the revised budget and asking for confirmation before noon.",
        thread_id="thread-1",
    )

    result = await client.create_draft(request)

    assert result.status == "completed"
    assert result.references.draft_id == "draft-123"
    assert result.details.preview.subject == "Budget follow-up"
    assert result.details.preview.thread_id == "thread-1"


@pytest.mark.asyncio
async def test_list_important_threads_maps_auth_failure_to_blocked(monkeypatch) -> None:
    async def _handler(url, json, headers):
        request = httpx.Request("POST", url, json=json, headers=headers)
        return httpx.Response(401, request=request, json={"message": "Unauthorized"})

    monkeypatch.setattr(
        "nanobot.automation.mail.httpx.AsyncClient",
        _mock_client_factory(_handler),
    )

    client = N8NGmailAutomationClient(
        N8NGmailAutomationConfig(base_url="http://127.0.0.1:5678")
    )

    result = await client.list_important_threads(search_query="is:unread")

    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "authentication_needed"


@pytest.mark.asyncio
async def test_session_runner_persists_draft_result_and_assistant_turn(monkeypatch, tmp_path) -> None:
    async def _handler(url, json, headers):
        return httpx.Response(
            200,
            json={
                "action": "gmail-draft",
                "reply": "alice@example.com 수신 메일 초안을 작성했습니다. 제목은 'Budget follow-up' 입니다.",
                "draft_id": "draft-123",
            },
        )

    monkeypatch.setattr(
        "nanobot.automation.mail.httpx.AsyncClient",
        _mock_client_factory(_handler),
    )

    client = N8NGmailAutomationClient(
        N8NGmailAutomationConfig(base_url="http://127.0.0.1:5678")
    )
    runner = MailAutomationSessionRunner(SessionManager(tmp_path), client)

    result = await runner.create_draft(
        "websocket:mail-demo",
        MailDraftRequest(
            to_recipients=["alice@example.com"],
            subject="Budget follow-up",
            body="Sharing the revised budget and asking for confirmation before noon.",
            thread_id="thread-1",
        ),
    )

    restored = runner.sessions.read_session_file("websocket:mail-demo")

    assert result.status == "completed"
    assert restored is not None
    assert restored["metadata"]["action_result"]["action"] == "create_draft"
    assert restored["metadata"]["action_result"]["details"]["draft_id"] == "draft-123"
    assert restored["messages"][-1]["role"] == "assistant"
    assert "메일 초안을 작성했습니다" in restored["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_send_message_normalizes_success_response(monkeypatch) -> None:
    async def _handler(url, json, headers):
        assert url == "http://127.0.0.1:5678/webhook/assistant-gmail-send"
        assert json["send_to"] == "alice@example.com"
        assert json["subject"] == "Budget follow-up"
        return httpx.Response(
            200,
            json={
                "action": "gmail-send",
                "reply": "alice@example.com로 메일을 발송했습니다. 제목은 'Budget follow-up' 입니다.",
                "message_id": "message-123",
            },
        )

    monkeypatch.setattr(
        "nanobot.automation.mail.httpx.AsyncClient",
        _mock_client_factory(_handler),
    )

    client = N8NGmailAutomationClient(
        N8NGmailAutomationConfig(base_url="http://127.0.0.1:5678")
    )

    result = await client.send_message(
        MailSendRequest(
            to_recipients=["alice@example.com"],
            subject="Budget follow-up",
            body="Sending the approved budget update.",
            draft_id="draft-123",
        )
    )

    assert result.status == "completed"
    assert result.details.message_id == "message-123"
    assert result.references.draft_id == "draft-123"


@pytest.mark.asyncio
async def test_session_runner_requests_send_approval_from_latest_draft(monkeypatch, tmp_path) -> None:
    async def _draft_handler(url, json, headers):
        return httpx.Response(
            200,
            json={
                "action": "gmail-draft",
                "reply": "alice@example.com 수신 메일 초안을 작성했습니다. 제목은 'Budget follow-up' 입니다.",
                "draft_id": "draft-123",
            },
        )

    monkeypatch.setattr(
        "nanobot.automation.mail.httpx.AsyncClient",
        _mock_client_factory(_draft_handler),
    )

    client = N8NGmailAutomationClient(
        N8NGmailAutomationConfig(base_url="http://127.0.0.1:5678")
    )
    runner = MailAutomationSessionRunner(SessionManager(tmp_path), client)

    await runner.create_draft(
        "websocket:mail-demo",
        MailDraftRequest(
            to_recipients=["alice@example.com"],
            subject="Budget follow-up",
            body="Sharing the revised budget and asking for confirmation before noon.",
            thread_id="thread-1",
        ),
    )
    approval = await runner.request_send_from_latest_draft("websocket:mail-demo")
    restored = runner.sessions.read_session_file("websocket:mail-demo")

    assert approval.status == "waiting_approval"
    assert restored is not None
    assert restored["metadata"]["approval_summary"]["status"] == "pending"
    assert restored["metadata"]["action_result"]["status"] == "waiting_approval"
    assert restored["metadata"]["mail_send_approval"]["draft_id"] == "draft-123"


@pytest.mark.asyncio
async def test_session_runner_approves_pending_send_and_clears_approval(monkeypatch, tmp_path) -> None:
    calls: list[str] = []

    async def _handler(url, json, headers):
        calls.append(url)
        if url.endswith("assistant-gmail-draft"):
            return httpx.Response(
                200,
                json={
                    "action": "gmail-draft",
                    "reply": "alice@example.com 수신 메일 초안을 작성했습니다. 제목은 'Budget follow-up' 입니다.",
                    "draft_id": "draft-123",
                },
            )
        return httpx.Response(
            200,
            json={
                "action": "gmail-send",
                "reply": "alice@example.com로 메일을 발송했습니다. 제목은 'Budget follow-up' 입니다.",
                "message_id": "message-123",
            },
        )

    monkeypatch.setattr(
        "nanobot.automation.mail.httpx.AsyncClient",
        _mock_client_factory(_handler),
    )

    client = N8NGmailAutomationClient(
        N8NGmailAutomationConfig(base_url="http://127.0.0.1:5678")
    )
    runner = MailAutomationSessionRunner(SessionManager(tmp_path), client)

    await runner.create_draft(
        "websocket:mail-demo",
        MailDraftRequest(
            to_recipients=["alice@example.com"],
            subject="Budget follow-up",
            body="Sharing the revised budget and asking for confirmation before noon.",
        ),
    )
    await runner.request_send_from_latest_draft("websocket:mail-demo")
    sent = await runner.approve_send("websocket:mail-demo")
    restored = runner.sessions.read_session_file("websocket:mail-demo")

    assert sent.status == "completed"
    assert restored is not None
    assert "approval_summary" not in restored["metadata"]
    assert "mail_send_approval" not in restored["metadata"]
    assert restored["metadata"]["action_result"]["action"] == "send_message"
    assert restored["metadata"]["action_result"]["details"]["message_id"] == "message-123"
    assert any(url.endswith("assistant-gmail-send") for url in calls)