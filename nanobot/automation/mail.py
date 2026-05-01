from __future__ import annotations

import os
from typing import Any, Mapping
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from nanobot.automation_results import (
    ActionFailure,
    ActionReferences,
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
from nanobot.session.manager import SessionManager


MAIL_LAST_DRAFT_REQUEST_METADATA_KEY = "mail_last_draft_request"
MAIL_SEND_APPROVAL_METADATA_KEY = "mail_send_approval"


class _MailAutomationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class N8NGmailAutomationConfig(_MailAutomationModel):
    base_url: str
    webhook_token: str | None = None
    summary_path: str = "webhook/assistant-gmail-summary"
    thread_path: str = "webhook/assistant-gmail-thread"
    draft_path: str = "webhook/assistant-gmail-draft"
    send_path: str = "webhook/assistant-gmail-send"
    timeout_s: float = 20.0

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
    ) -> "N8NGmailAutomationConfig | None":
        scope = os.environ if env is None else env
        base_url = str(scope.get("N8N_BASE_URL") or scope.get("N8N_EDITOR_BASE_URL") or "").strip()
        if not base_url:
            return None
        return cls(
            base_url=base_url,
            webhook_token=str(scope.get("N8N_WEBHOOK_TOKEN") or "").strip() or None,
            summary_path=str(scope.get("N8N_GMAIL_WEBHOOK_PATH") or "webhook/assistant-gmail-summary").strip(),
            thread_path=str(scope.get("N8N_GMAIL_THREAD_WEBHOOK_PATH") or "webhook/assistant-gmail-thread").strip(),
            draft_path=str(scope.get("N8N_GMAIL_DRAFT_WEBHOOK_PATH") or "webhook/assistant-gmail-draft").strip(),
            send_path=str(scope.get("N8N_GMAIL_SEND_WEBHOOK_PATH") or "webhook/assistant-gmail-send").strip(),
        )


class MailDraftRequest(_MailAutomationModel):
    to_recipients: list[str] = Field(min_length=1)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
    cc_recipients: list[str] = Field(default_factory=list)
    bcc_recipients: list[str] = Field(default_factory=list)
    thread_id: str | None = None
    attachment_url: str | None = None
    email_type: str = "text"


class MailSendRequest(_MailAutomationModel):
    to_recipients: list[str] = Field(min_length=1)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
    cc_recipients: list[str] = Field(default_factory=list)
    bcc_recipients: list[str] = Field(default_factory=list)
    thread_id: str | None = None
    attachment_url: str | None = None
    email_type: str = "text"
    draft_id: str | None = None


class N8NGmailAutomationClient:
    """Direct n8n-backed Gmail automation seam for the phase-1 mail pilot."""

    def __init__(self, config: N8NGmailAutomationConfig):
        self.config = config

    async def list_important_threads(
        self,
        *,
        search_query: str,
        limit: int = 5,
        group_by_date: bool = False,
        mailbox_scope: str = "default",
    ) -> MailImportantThreadsResult:
        action_id = self._action_id("mail-list")
        try:
            payload = await self._post_json(
                self.config.summary_path,
                {
                    "searchQuery": search_query,
                    "limit": limit,
                    "groupByDate": group_by_date,
                    "mailboxScope": mailbox_scope,
                },
            )
        except httpx.HTTPError as exc:
            return self._list_failure_result(action_id, exc)

        items = payload.get("items") if isinstance(payload, dict) else None
        threads = [self._thread_from_summary_item(item) for item in items or [] if isinstance(item, dict)]
        shown_count = self._coerce_int(payload.get("shownCount")) if isinstance(payload, dict) else None
        title = "Important mail summary ready" if threads else "No important mail found"
        summary = (
            f"{shown_count or len(threads)} important threads were found."
            if threads
            else "No important mail matched the current query."
        )
        return MailImportantThreadsResult(
            action_id=action_id,
            status="completed",
            title=title,
            summary=summary,
            next_step="Choose a thread to summarize in more detail." if threads else None,
            visibility=ActionVisibility(
                surfaces=["thread", "sidebar"],
                badge="Mail",
                inline_status=summary,
                linked_summary=summary,
            ),
            details=MailImportantThreadsDetails(
                mailbox_label=self._coerce_text(payload.get("mailboxScope")) if isinstance(payload, dict) else mailbox_scope,
                total_candidates=self._coerce_int(payload.get("count")) if isinstance(payload, dict) else len(threads),
                threads=threads,
            ),
        )

    async def summarize_threads(
        self,
        *,
        thread_ids: list[str],
        summary_style: str = "brief",
        urgency_threshold: str = "medium",
    ) -> MailSummarizeThreadsResult:
        action_id = self._action_id("mail-summarize")
        digests: list[MailThreadDigest] = []
        for thread_id in thread_ids:
            try:
                payload = await self._post_json(
                    self.config.thread_path,
                    {
                        "thread_id": thread_id,
                        "detail_level": "brief",
                        "limit": 20,
                    },
                )
            except httpx.HTTPError as exc:
                return self._summaries_failure_result(action_id, exc)
            if not isinstance(payload, dict) or payload.get("found") is False:
                continue
            digest = self._digest_from_thread_payload(payload)
            if digest is not None:
                digests.append(digest)

        if not digests:
            return MailSummarizeThreadsResult(
                action_id=action_id,
                status="blocked",
                title="Mail thread summary unavailable",
                summary="The requested thread could not be found in the mailbox context.",
                visibility=ActionVisibility(surfaces=["thread"], badge="Mail blocked"),
                details=MailThreadSummariesDetails(
                    summary_style=summary_style,
                    urgency_threshold=urgency_threshold,
                    threads=[],
                ),
                error=ActionFailure(
                    code="not_found",
                    message="The requested thread could not be found.",
                    retryable=False,
                ),
            )

        return MailSummarizeThreadsResult(
            action_id=action_id,
            status="completed",
            title="Thread summaries ready",
            summary=f"Summaries were generated for {len(digests)} threads.",
            next_step="Create a reply draft for the thread that needs follow-up.",
            visibility=ActionVisibility(
                surfaces=["thread", "sidebar"],
                badge="Thread summary",
                inline_status="Mail thread summary ready",
            ),
            details=MailThreadSummariesDetails(
                summary_style=summary_style,
                urgency_threshold=urgency_threshold,
                threads=digests,
            ),
        )

    async def create_draft(self, request: MailDraftRequest) -> MailCreateDraftResult:
        action_id = self._action_id("mail-draft")
        preview = MailDraftPreview(
            subject=request.subject,
            body_preview=self._body_preview(request.body),
            to_recipients=request.to_recipients,
            cc_recipients=request.cc_recipients,
            bcc_recipients=request.bcc_recipients,
            thread_id=request.thread_id,
        )
        try:
            payload = await self._post_json(
                self.config.draft_path,
                {
                    "send_to": ", ".join(request.to_recipients),
                    "subject": request.subject,
                    "message": request.body,
                    "email_type": request.email_type,
                    "cc_list": ", ".join(request.cc_recipients),
                    "bcc_list": ", ".join(request.bcc_recipients),
                    "attachment_url": request.attachment_url or "",
                    "thread_id": request.thread_id or "",
                },
            )
        except httpx.HTTPError as exc:
            return self._draft_failure_result(action_id, preview, exc)

        draft_id = self._coerce_text(payload.get("draft_id")) if isinstance(payload, dict) else None
        summary = self._coerce_text(payload.get("reply")) if isinstance(payload, dict) else None
        return MailCreateDraftResult(
            action_id=action_id,
            status="completed",
            title="Draft ready",
            summary=summary or f"Draft created for {', '.join(request.to_recipients)}.",
            next_step="Review the draft before requesting send approval.",
            visibility=ActionVisibility(
                surfaces=["thread", "sidebar"],
                badge="Draft ready",
                inline_status="Mail draft created",
                linked_summary=request.subject,
            ),
            references=ActionReferences(thread_id=request.thread_id, draft_id=draft_id),
            details=MailCreateDraftDetails(draft_id=draft_id, preview=preview),
        )

    async def send_message(self, request: MailSendRequest) -> MailSendMessageResult:
        action_id = self._action_id("mail-send")
        preview = MailDraftPreview(
            subject=request.subject,
            body_preview=self._body_preview(request.body),
            to_recipients=request.to_recipients,
            cc_recipients=request.cc_recipients,
            bcc_recipients=request.bcc_recipients,
            thread_id=request.thread_id,
        )
        try:
            payload = await self._post_json(
                self.config.send_path,
                {
                    "send_to": ", ".join(request.to_recipients),
                    "subject": request.subject,
                    "message": request.body,
                    "email_type": request.email_type,
                    "cc_list": ", ".join(request.cc_recipients),
                    "bcc_list": ", ".join(request.bcc_recipients),
                    "attachment_url": request.attachment_url or "",
                    "thread_id": request.thread_id or "",
                    "draft_id": request.draft_id or "",
                },
            )
        except httpx.HTTPError as exc:
            return self._send_failure_result(action_id, request, preview, exc)

        message_id = self._coerce_text(payload.get("message_id")) if isinstance(payload, dict) else None
        summary = self._coerce_text(payload.get("reply")) if isinstance(payload, dict) else None
        return MailSendMessageResult(
            action_id=action_id,
            status="completed",
            title="Message sent",
            summary=summary or f"Email sent to {', '.join(request.to_recipients)}.",
            visibility=ActionVisibility(
                surfaces=["thread", "sidebar", "linked_session"],
                badge="Sent",
                inline_status="Mail sent",
                linked_summary=request.subject,
            ),
            references=ActionReferences(
                thread_id=request.thread_id,
                draft_id=request.draft_id,
                message_id=message_id,
            ),
            details=MailSendMessageDetails(
                draft_id=request.draft_id,
                message_id=message_id,
                preview=preview,
            ),
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
                    f"Mail automation webhook returned HTTP {response.status_code}",
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
    ) -> MailImportantThreadsResult:
        failure = self._map_http_error(exc, missing_code="service_unavailable")
        return MailImportantThreadsResult(
            action_id=action_id,
            status="blocked" if failure.code == "authentication_needed" else "failed",
            title="Important mail summary unavailable",
            summary=failure.message,
            visibility=ActionVisibility(surfaces=["thread"], badge="Mail failed"),
            details=MailImportantThreadsDetails(threads=[]),
            error=failure,
        )

    def _summaries_failure_result(
        self,
        action_id: str,
        exc: httpx.HTTPError,
    ) -> MailSummarizeThreadsResult:
        failure = self._map_http_error(exc, missing_code="service_unavailable")
        return MailSummarizeThreadsResult(
            action_id=action_id,
            status="blocked" if failure.code == "authentication_needed" else "failed",
            title="Mail thread summary unavailable",
            summary=failure.message,
            visibility=ActionVisibility(surfaces=["thread"], badge="Mail failed"),
            details=MailThreadSummariesDetails(threads=[]),
            error=failure,
        )

    def _draft_failure_result(
        self,
        action_id: str,
        preview: MailDraftPreview,
        exc: httpx.HTTPError,
    ) -> MailCreateDraftResult:
        failure = self._map_http_error(exc, missing_code="service_unavailable")
        return MailCreateDraftResult(
            action_id=action_id,
            status="blocked" if failure.code == "authentication_needed" else "failed",
            title="Draft creation failed",
            summary=failure.message,
            visibility=ActionVisibility(surfaces=["thread"], badge="Draft failed"),
            details=MailCreateDraftDetails(preview=preview),
            error=failure,
        )

    def _send_failure_result(
        self,
        action_id: str,
        request: MailSendRequest,
        preview: MailDraftPreview,
        exc: httpx.HTTPError,
    ) -> MailSendMessageResult:
        failure = self._map_http_error(exc, missing_code="service_unavailable")
        return MailSendMessageResult(
            action_id=action_id,
            status="blocked" if failure.code == "authentication_needed" else "failed",
            title="Mail send failed",
            summary=failure.message,
            visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Send failed"),
            references=ActionReferences(thread_id=request.thread_id, draft_id=request.draft_id),
            details=MailSendMessageDetails(
                draft_id=request.draft_id,
                preview=preview,
            ),
            error=failure,
        )

    def _map_http_error(self, exc: httpx.HTTPError, *, missing_code: str) -> ActionFailure:
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            if status_code in {401, 403}:
                return ActionFailure(
                    code="authentication_needed",
                    message="Gmail automation credentials need attention before this action can continue.",
                    retryable=False,
                )
            if status_code == 404:
                return ActionFailure(
                    code="executor_unavailable",
                    message="The Gmail automation webhook is not available.",
                    retryable=False,
                )
            if status_code == 429:
                return ActionFailure(
                    code="rate_limited",
                    message="The Gmail automation endpoint is rate limited right now.",
                    retryable=True,
                )
            return ActionFailure(
                code=missing_code,
                message="The Gmail automation endpoint could not complete the request.",
                retryable=status_code >= 500,
                detail=f"HTTP {status_code}",
            )
        if isinstance(exc, httpx.TimeoutException):
            return ActionFailure(
                code="service_unavailable",
                message="The Gmail automation endpoint timed out.",
                retryable=True,
            )
        return ActionFailure(
            code="service_unavailable",
            message="The Gmail automation endpoint is temporarily unavailable.",
            retryable=True,
        )

    def _thread_from_summary_item(self, item: Mapping[str, Any]) -> MailThreadSummary:
        unread = bool(item.get("unread"))
        has_attachments = bool(item.get("hasAttachments"))
        importance_hint = "high" if unread else "medium" if has_attachments else None
        return MailThreadSummary(
            thread_id=self._coerce_text(item.get("threadId")) or self._coerce_text(item.get("messageId")) or "unknown-thread",
            subject=self._coerce_text(item.get("subject")) or "(No subject)",
            sender_summary=self._coerce_text(item.get("sender")) or "Unknown sender",
            last_update_at=self._coerce_text(item.get("date")) or "",
            unread=unread,
            importance_hint=importance_hint,
            snippet=self._coerce_text(item.get("snippet")),
        )

    def _digest_from_thread_payload(self, payload: Mapping[str, Any]) -> MailThreadDigest | None:
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return None
        normalized_items = [item for item in items if isinstance(item, dict)]
        if not normalized_items:
            return None
        latest = normalized_items[-1]
        unread = any(bool(item.get("unread")) for item in normalized_items)
        body = self._coerce_text(latest.get("body")) or self._coerce_text(latest.get("snippet")) or ""
        sender = self._coerce_text(latest.get("sender")) or "Unknown sender"
        subject = self._coerce_text(payload.get("subject")) or self._coerce_text(latest.get("subject")) or "(No subject)"
        message_count = self._coerce_int(payload.get("messageCount")) or len(normalized_items)
        summary = f"{sender} thread with {message_count} messages. {self._body_preview(body, limit=180)}".strip()
        return MailThreadDigest(
            thread_id=self._coerce_text(payload.get("threadId")) or self._coerce_text(latest.get("threadId")) or "unknown-thread",
            subject=subject,
            summary=summary,
            urgency="high" if unread else "medium" if message_count >= 3 else "low",
            recommended_next_action="Create a reply draft." if unread or message_count >= 2 else None,
        )

    def _action_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:10]}"

    def _body_preview(self, body: str, *, limit: int = 240) -> str:
        collapsed = " ".join(body.split())
        if len(collapsed) <= limit:
            return collapsed
        return f"{collapsed[: limit - 3]}..."

    def _coerce_text(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _coerce_int(self, value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed


class MailAutomationSessionRunner:
    """Persist mail automation results onto a Nanobot session."""

    def __init__(self, sessions: SessionManager, client: N8NGmailAutomationClient):
        self.sessions = sessions
        self.client = client

    async def list_important_threads(
        self,
        session_key: str,
        *,
        search_query: str,
        limit: int = 5,
        group_by_date: bool = False,
        mailbox_scope: str = "default",
    ) -> MailImportantThreadsResult:
        result = await self.client.list_important_threads(
            search_query=search_query,
            limit=limit,
            group_by_date=group_by_date,
            mailbox_scope=mailbox_scope,
        )
        self._persist_result(session_key, result)
        return result

    async def summarize_threads(
        self,
        session_key: str,
        *,
        thread_ids: list[str],
        summary_style: str = "brief",
        urgency_threshold: str = "medium",
    ) -> MailSummarizeThreadsResult:
        result = await self.client.summarize_threads(
            thread_ids=thread_ids,
            summary_style=summary_style,
            urgency_threshold=urgency_threshold,
        )
        self._persist_result(session_key, result)
        return result

    async def create_draft(
        self,
        session_key: str,
        request: MailDraftRequest,
    ) -> MailCreateDraftResult:
        result = await self.client.create_draft(request)
        self._persist_result(session_key, result)
        self._remember_latest_draft(session_key, request, draft_id=result.details.draft_id)
        return result

    async def request_send_approval(
        self,
        session_key: str,
        request: MailSendRequest,
    ) -> MailSendMessageResult:
        preview = MailDraftPreview(
            subject=request.subject,
            body_preview=self.client._body_preview(request.body),
            to_recipients=request.to_recipients,
            cc_recipients=request.cc_recipients,
            bcc_recipients=request.bcc_recipients,
            thread_id=request.thread_id,
        )
        recipients = ", ".join(request.to_recipients)
        result = MailSendMessageResult(
            action_id=self.client._action_id("mail-send-approval"),
            status="waiting_approval",
            title="Mail send approval required",
            summary=f"Approval required before sending '{request.subject}' to {recipients}.",
            next_step="Approve or deny the pending mail send request.",
            visibility=ActionVisibility(
                surfaces=["thread", "sidebar", "linked_session"],
                badge="Approval pending",
                inline_status="Mail send approval pending",
                linked_summary=request.subject,
                approval_summary="Mail send approval pending",
            ),
            references=ActionReferences(thread_id=request.thread_id, draft_id=request.draft_id),
            details=MailSendMessageDetails(draft_id=request.draft_id, preview=preview),
            error=ActionFailure(
                code="approval_needed",
                message="Approval is required before sending this email.",
                retryable=True,
            ),
        )
        session = self.sessions.get_or_create(session_key)
        session.metadata[MAIL_SEND_APPROVAL_METADATA_KEY] = request.model_dump(mode="json")
        self.sessions.set_action_result(session, result)
        self.sessions.set_approval_summary(
            session,
            {
                "status": "pending",
                "channel": self._channel_from_session_key(session_key),
                "tool_name": "mail.send_message",
                "tool_call_id": result.action_id,
                "message_id": None,
                "prompt_preview": self._approval_prompt(request),
            },
        )
        session.add_message("assistant", result.summary)
        self.sessions.save(session)
        return result

    async def request_send_from_latest_draft(self, session_key: str) -> MailSendMessageResult:
        request = self._latest_draft_request(session_key)
        if request is None:
            return self._persist_ephemeral_result(
                session_key,
                MailSendMessageResult(
                    action_id=self.client._action_id("mail-send-missing-draft"),
                    status="blocked",
                    title="Mail send approval unavailable",
                    summary="There is no saved draft in this session to approve for sending.",
                    next_step="Create a draft first, then request send approval.",
                    visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Send blocked"),
                    details=MailSendMessageDetails(
                        preview=MailDraftPreview(subject="(No subject)", body_preview="", to_recipients=[]),
                    ),
                    error=ActionFailure(
                        code="not_found",
                        message="No saved draft is available for send approval.",
                        retryable=False,
                    ),
                ),
            )
        return await self.request_send_approval(session_key, request)

    async def approve_send(self, session_key: str) -> MailSendMessageResult:
        request = self._pending_send_request(session_key)
        if request is None:
            return self._persist_ephemeral_result(
                session_key,
                MailSendMessageResult(
                    action_id=self.client._action_id("mail-send-no-pending"),
                    status="blocked",
                    title="No pending mail approval",
                    summary="There is no pending mail send approval in this session.",
                    next_step="Request mail send approval first.",
                    visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Send blocked"),
                    details=MailSendMessageDetails(
                        preview=MailDraftPreview(subject="(No subject)", body_preview="", to_recipients=[]),
                    ),
                    error=ActionFailure(
                        code="not_found",
                        message="No pending mail approval is available.",
                        retryable=False,
                    ),
                ),
            )
        result = await self.client.send_message(request)
        session = self.sessions.get_or_create(session_key)
        session.metadata.pop(MAIL_SEND_APPROVAL_METADATA_KEY, None)
        self.sessions.clear_approval_summary(session)
        self.sessions.set_action_result(session, result)
        session.add_message("assistant", result.summary)
        self.sessions.save(session)
        return result

    async def deny_send(self, session_key: str) -> MailSendMessageResult:
        request = self._pending_send_request(session_key)
        if request is None:
            return await self.approve_send(session_key)
        preview = MailDraftPreview(
            subject=request.subject,
            body_preview=self.client._body_preview(request.body),
            to_recipients=request.to_recipients,
            cc_recipients=request.cc_recipients,
            bcc_recipients=request.bcc_recipients,
            thread_id=request.thread_id,
        )
        result = MailSendMessageResult(
            action_id=self.client._action_id("mail-send-denied"),
            status="rejected",
            title="Mail send cancelled",
            summary="The pending mail send request was cancelled.",
            next_step="Review the draft and request approval again when ready.",
            visibility=ActionVisibility(surfaces=["thread", "sidebar"], badge="Send cancelled"),
            references=ActionReferences(thread_id=request.thread_id, draft_id=request.draft_id),
            details=MailSendMessageDetails(draft_id=request.draft_id, preview=preview),
            error=ActionFailure(
                code="approval_rejected",
                message="The pending mail send request was cancelled.",
                retryable=False,
            ),
        )
        session = self.sessions.get_or_create(session_key)
        session.metadata.pop(MAIL_SEND_APPROVAL_METADATA_KEY, None)
        self.sessions.clear_approval_summary(session)
        self.sessions.set_action_result(session, result)
        session.add_message("assistant", result.summary)
        self.sessions.save(session)
        return result

    def _persist_result(
        self,
        session_key: str,
        result: MailImportantThreadsResult | MailSummarizeThreadsResult | MailCreateDraftResult | MailSendMessageResult,
    ) -> None:
        session = self.sessions.get_or_create(session_key)
        self.sessions.set_action_result(session, result)
        if result.summary:
            session.add_message("assistant", result.summary)
        self.sessions.save(session)

    def _persist_ephemeral_result(self, session_key: str, result: MailSendMessageResult) -> MailSendMessageResult:
        self._persist_result(session_key, result)
        return result

    def _remember_latest_draft(
        self,
        session_key: str,
        request: MailDraftRequest,
        *,
        draft_id: str | None,
    ) -> None:
        session = self.sessions.get_or_create(session_key)
        session.metadata[MAIL_LAST_DRAFT_REQUEST_METADATA_KEY] = MailSendRequest(
            to_recipients=request.to_recipients,
            cc_recipients=request.cc_recipients,
            bcc_recipients=request.bcc_recipients,
            subject=request.subject,
            body=request.body,
            thread_id=request.thread_id,
            attachment_url=request.attachment_url,
            email_type=request.email_type,
            draft_id=draft_id,
        ).model_dump(mode="json")
        self.sessions.save(session)

    def _latest_draft_request(self, session_key: str) -> MailSendRequest | None:
        session = self.sessions.get_or_create(session_key)
        payload = session.metadata.get(MAIL_LAST_DRAFT_REQUEST_METADATA_KEY)
        if not isinstance(payload, dict):
            return None
        try:
            return MailSendRequest.model_validate(payload)
        except Exception:
            return None

    def _pending_send_request(self, session_key: str) -> MailSendRequest | None:
        session = self.sessions.get_or_create(session_key)
        payload = session.metadata.get(MAIL_SEND_APPROVAL_METADATA_KEY)
        if not isinstance(payload, dict):
            return None
        try:
            return MailSendRequest.model_validate(payload)
        except Exception:
            return None

    @staticmethod
    def _channel_from_session_key(session_key: str) -> str:
        return session_key.split(":", 1)[0] if ":" in session_key else "websocket"

    def _approval_prompt(self, request: MailSendRequest) -> str:
        recipients = ", ".join(request.to_recipients)
        return (
            "Approval required before sending this email. "
            f"To: {recipients}. Subject: {request.subject}. "
            "Use /mail approve to send or /mail deny to cancel."
        )