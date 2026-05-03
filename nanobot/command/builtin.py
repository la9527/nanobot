"""Built-in slash command handlers."""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import sys
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from nanobot.automation.calendar import (
    CALENDAR_CREATE_APPROVAL_METADATA_KEY,
    CALENDAR_DELETE_APPROVAL_METADATA_KEY,
    CALENDAR_UPDATE_APPROVAL_METADATA_KEY,
    CalendarAutomationSessionRunner,
    CalendarCreateRequest,
    CalendarDeleteRequest,
    CalendarUpdateRequest,
    N8NCalendarAutomationClient,
    N8NCalendarAutomationConfig,
)
from nanobot.automation_results import CalendarEventSummary
from nanobot.automation.mail import (
    MAIL_LAST_DRAFT_REQUEST_METADATA_KEY,
    MAIL_SEND_APPROVAL_METADATA_KEY,
    MailAutomationSessionRunner,
    MailDraftRequest,
    MailSendRequest,
    N8NGmailAutomationClient,
    N8NGmailAutomationConfig,
)
from nanobot import __version__
from nanobot.bus.events import OutboundMessage
from nanobot.command.router import CommandContext, CommandRouter
from nanobot.model_targets import DEFAULT_MODEL_TARGET_NAME, describe_model_target
from nanobot.response_status import (
    RESPONSE_FOOTER_MODES,
    build_response_footer,
    normalize_response_footer_mode,
)
from nanobot.session.continuity import ACTION_RESULT_METADATA_KEY, TASK_SUMMARY_METADATA_KEY
from nanobot.utils.helpers import build_status_content
from nanobot.utils.restart import set_restart_notice_to_env


CALENDAR_CREATE_INPUT_METADATA_KEY = "calendar_create_input"
CALENDAR_CONFLICT_REVIEW_METADATA_KEY = "calendar_conflict_review"
CALENDAR_PENDING_INTERACTION_METADATA_KEY = "calendar_pending_interaction"
CALENDAR_CREATE_CANCEL_CHOICES = [["취소"]]
CALENDAR_CONFLICT_FORCE_CREATE_LABEL = "그래도 생성 승인 요청"
CALENDAR_CONFLICT_RESCHEDULE_LABEL = "새 시간 다시 입력"
CALENDAR_CONFLICT_REVIEW_CHOICES = [
    [CALENDAR_CONFLICT_FORCE_CREATE_LABEL, CALENDAR_CONFLICT_RESCHEDULE_LABEL],
    ["취소"],
]
CALENDAR_NATURAL_CREATE_KEYWORDS = ("일정", "예약", "캘린더")
CALENDAR_NATURAL_CREATE_VERBS = ("잡아", "등록", "추가", "넣어", "만들", "생성", "예약")
CALENDAR_NATURAL_MUTATION_VERBS = ("삭제", "지워", "취소", "옮겨", "변경", "수정", "미뤄", "당겨")
CALENDAR_NATURAL_DELETE_VERBS = ("삭제", "지워", "취소")
CALENDAR_NATURAL_UPDATE_VERBS = ("옮겨", "변경", "수정", "미뤄", "당겨")
CALENDAR_NATURAL_APPROVE_WORDS = ("승인", "확정", "진행", "좋아", "맞아", "그래", "ok", "okay", "yes")
CALENDAR_NATURAL_CANCEL_WORDS = ("취소", "반려", "거절", "거부", "아니", "하지마", "하지 마", "cancel", "deny", "no")
SESSION_LOG_MODE_METADATA_KEY = "_session_log_mode"
SESSION_LOG_MODE_SKIP = "skip"
CONTEXT_CLEAR_METADATA_KEYS = (
    ACTION_RESULT_METADATA_KEY,
    TASK_SUMMARY_METADATA_KEY,
    "approval_summary",
    "proactive_summary",
    "runtime_checkpoint",
    "pending_user_turn",
    "_last_summary",
    CALENDAR_CREATE_INPUT_METADATA_KEY,
    CALENDAR_CONFLICT_REVIEW_METADATA_KEY,
    CALENDAR_PENDING_INTERACTION_METADATA_KEY,
    CALENDAR_CREATE_APPROVAL_METADATA_KEY,
    CALENDAR_UPDATE_APPROVAL_METADATA_KEY,
    CALENDAR_DELETE_APPROVAL_METADATA_KEY,
    MAIL_LAST_DRAFT_REQUEST_METADATA_KEY,
    MAIL_SEND_APPROVAL_METADATA_KEY,
)
CALENDAR_WEEKDAY_INDEX = {
    "월": 0,
    "화": 1,
    "수": 2,
    "목": 3,
    "금": 4,
    "토": 5,
    "일": 6,
}


async def cmd_stop(ctx: CommandContext) -> OutboundMessage:
    """Cancel all active tasks and subagents for the session."""
    loop = ctx.loop
    msg = ctx.msg
    total = await loop._cancel_active_tasks(msg.session_key)
    content = f"Stopped {total} task(s)." if total else "No active task to stop."
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content=content,
        metadata=dict(msg.metadata or {})
    )


async def cmd_restart(ctx: CommandContext) -> OutboundMessage:
    """Restart the process in-place via os.execv."""
    msg = ctx.msg
    set_restart_notice_to_env(
        channel=msg.channel,
        chat_id=msg.chat_id,
        metadata=dict(msg.metadata or {}),
    )

    async def _do_restart():
        await asyncio.sleep(1)
        os.execv(sys.executable, [sys.executable, "-m", "nanobot"] + sys.argv[1:])

    asyncio.create_task(_do_restart())
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content="Restarting...",
        metadata=dict(msg.metadata or {})
    )


async def cmd_status(ctx: CommandContext) -> OutboundMessage:
    """Build an outbound status message for a session."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    status_snapshot = loop.build_response_status(session)
    
    ctx_est = 0
    try:
        ctx_est, _ = loop.consolidator.estimate_session_prompt_tokens(session)
    except Exception:
        pass
    if ctx_est <= 0:
        ctx_est = loop._last_usage.get("prompt_tokens", 0)

    # Fetch web search provider usage (best-effort, never blocks the response)
    search_usage_text: str | None = None
    try:
        from nanobot.utils.searchusage import fetch_search_usage
        web_cfg = getattr(loop, "web_config", None)
        search_cfg = getattr(web_cfg, "search", None) if web_cfg else None
        if search_cfg is not None:
            provider = getattr(search_cfg, "provider", "duckduckgo")
            api_key = getattr(search_cfg, "api_key", "") or None
            usage = await fetch_search_usage(provider=provider, api_key=api_key)
            search_usage_text = usage.format()
    except Exception:
        pass  # Never let usage fetch break /status
    active_tasks = loop._active_tasks.get(ctx.key, [])
    task_count = sum(1 for t in active_tasks if not t.done())
    try:
        task_count += loop.subagents.get_running_count_by_session(ctx.key)
    except Exception:
        pass
    content = build_status_content(
        version=__version__, model=status_snapshot["model"],
        start_time=loop._start_time, last_usage=status_snapshot["usage"],
        context_window_tokens=status_snapshot["context_window_tokens"],
        session_msg_count=len(session.get_history(max_messages=0)),
        context_tokens_estimate=status_snapshot["context_tokens_estimate"],
        search_usage_text=search_usage_text,
        active_task_count=task_count,
        max_completion_tokens=getattr(
            getattr(loop.provider, "generation", None), "max_tokens", 8192
        ),
    )
    content += (
        f"\nTarget: {status_snapshot['active_target']}"
        f"\nReply footer: {status_snapshot['footer_mode']}"
    )
    route_tier = status_snapshot.get("smart_router_tier")
    route_model = status_snapshot.get("smart_router_model")
    if isinstance(route_tier, str) and route_tier:
        content += f"\nSmart-router route: {route_tier}"
        if isinstance(route_model, str) and route_model:
            content += f" ({route_model})"
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_usage(ctx: CommandContext) -> OutboundMessage:
    """Show or change per-session response footer mode."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    args = ctx.args.strip().lower()
    current_mode = loop.get_response_footer_mode(session)
    status_snapshot = loop.build_response_status(session)

    if not args:
        preview = build_response_footer(
            mode=current_mode,
            model=status_snapshot["model"],
            active_target=status_snapshot["active_target"],
            usage=status_snapshot["usage"],
            context_window_tokens=status_snapshot["context_window_tokens"],
            context_tokens_estimate=status_snapshot["context_tokens_estimate"],
            route_tier=status_snapshot.get("smart_router_tier"),
            route_model=status_snapshot.get("smart_router_model"),
        )
        lines = [
            "## Usage Footer",
            "",
            f"Current mode: `{current_mode}`",
        ]
        if preview:
            lines.extend(["", f"Preview:{preview}"])
        lines.extend([
            "",
            "Use `/usage off`, `/usage tokens`, or `/usage full`.",
        ])
    else:
        mode = normalize_response_footer_mode(args.split()[0])
        if mode not in RESPONSE_FOOTER_MODES or mode != args.split()[0]:
            lines = [
                "## Usage Footer",
                "",
                f"Unknown mode: `{args.split()[0]}`",
                "",
                "Valid modes: `off`, `tokens`, `full`.",
            ]
        else:
            loop.set_response_footer_mode(session, mode)
            status_snapshot = loop.build_response_status(session)
            lines = [
                "## Usage Footer",
                "",
                f"Selected `{mode}` for this session.",
            ]
            preview = build_response_footer(
                mode=mode,
                model=status_snapshot["model"],
                active_target=status_snapshot["active_target"],
                usage=status_snapshot["usage"],
                context_window_tokens=status_snapshot["context_window_tokens"],
                context_tokens_estimate=status_snapshot["context_tokens_estimate"],
                route_tier=status_snapshot.get("smart_router_tier"),
                route_model=status_snapshot.get("smart_router_model"),
            )
            if preview:
                lines.extend(["", f"Preview:{preview}"])
            else:
                lines.extend([
                    "",
                    "Future replies in this session will not include a status footer.",
                ])

    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="\n".join(lines),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_model(ctx: CommandContext) -> OutboundMessage:
    """Show or change the active named model target for the session."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    targets = loop.get_available_model_targets()
    active_name = loop.get_active_model_target_name(session)
    args = ctx.args.strip().lower()

    def _render_targets() -> list[str]:
        lines: list[str] = []
        for name, target in targets.items():
            prefix = "*" if name == active_name else "-"
            lines.append(f"{prefix} `{name}` — {describe_model_target(target)}")
        return lines

    if not targets:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="No model targets are configured.",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    if not args or args == "current":
        current = targets.get(active_name)
        lines = [
            "## Model Target",
            "",
            f"Current target: `{active_name}`",
        ]
        if current is not None:
            lines.append(f"Detail: {describe_model_target(current)}")
        lines.extend([
            "",
            "Available targets:",
            *_render_targets(),
            "",
            "Use `/model list` to see targets, `/model <name>` to switch, or `/model clear` to return to the startup default.",
        ])
    elif args == "list":
        lines = ["## Model Targets", "", *_render_targets()]
    elif args == "clear":
        loop.clear_session_model_target(session)
        active_name = loop.get_active_model_target_name(session)
        lines = [
            "## Model Target",
            "",
            f"Cleared the session override. Active target is now `{active_name}`.",
        ]
    else:
        target_name = args.split()[0]
        if target_name not in targets:
            lines = [
                "## Model Target",
                "",
                f"Unknown target: `{target_name}`",
                "",
                "Available targets:",
                *_render_targets(),
            ]
        else:
            loop.set_session_model_target(session, target_name)
            selected = targets[target_name]
            lines = [
                "## Model Target",
                "",
                f"Selected `{target_name}` for this session.",
                f"Detail: {describe_model_target(selected)}",
            ]
            if target_name == DEFAULT_MODEL_TARGET_NAME:
                lines.append("This target follows the startup default configuration.")

    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="\n".join(lines),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_new(ctx: CommandContext) -> OutboundMessage:
    """Stop active task and start a fresh session."""
    loop = ctx.loop
    await loop._cancel_active_tasks(ctx.key)
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    snapshot = session.messages[session.last_consolidated:]
    session.clear()
    loop.sessions.save(session)
    loop.sessions.invalidate(session.key)
    if snapshot:
        loop._schedule_background(loop.consolidator.archive(snapshot))
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content="New session started.",
        metadata=dict(ctx.msg.metadata or {})
    )


async def cmd_context(ctx: CommandContext) -> OutboundMessage:
    """Show or clear the current chat session context."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    raw_command = ctx.raw.strip().split(maxsplit=1)[0].split("@", 1)[0].lower()
    args = ctx.args.strip().lower()
    wants_clear = raw_command == "/clear" or args.split(maxsplit=1)[0:1] == ["clear"]

    if not wants_clear:
        message_count = len(session.messages)
        content = (
            "Context keeps this chat's recent messages for future replies.\n"
            f"Current stored message count: {message_count}.\n\n"
            "Use `/context clear` or `/clear` to drop this chat's stored conversation context."
        )
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=content,
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    cancelled = await loop._cancel_active_tasks(ctx.key)
    message_count = len(session.messages)
    removed_metadata = [key for key in CONTEXT_CLEAR_METADATA_KEYS if key in session.metadata]
    session.clear()
    for key in CONTEXT_CLEAR_METADATA_KEYS:
        session.metadata.pop(key, None)
    summaries = getattr(getattr(loop, "auto_compact", None), "_summaries", None)
    if isinstance(summaries, dict):
        summaries.pop(session.key, None)
    loop.sessions.save(session)

    details = [
        f"Cleared {message_count} stored message(s) from this chat context.",
    ]
    if removed_metadata:
        details.append(f"Removed {len(removed_metadata)} pending context marker(s).")
    if cancelled:
        details.append(f"Stopped {cancelled} active task(s) for this chat.")
    details.append("Long-term memory and global preferences were left unchanged.")
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="\n".join(details),
        metadata={
            **dict(ctx.msg.metadata or {}),
            "render_as": "text",
            SESSION_LOG_MODE_METADATA_KEY: SESSION_LOG_MODE_SKIP,
        },
    )


async def cmd_dream(ctx: CommandContext) -> OutboundMessage:
    """Manually trigger a Dream consolidation run."""
    import time

    loop = ctx.loop
    msg = ctx.msg

    async def _run_dream():
        t0 = time.monotonic()
        try:
            did_work = await loop.dream.run()
            elapsed = time.monotonic() - t0
            if did_work:
                content = f"Dream completed in {elapsed:.1f}s."
            else:
                content = "Dream: nothing to process."
        except Exception as e:
            elapsed = time.monotonic() - t0
            content = f"Dream failed after {elapsed:.1f}s: {e}"
        await loop.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=content,
        ))

    asyncio.create_task(_run_dream())
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content="Dreaming...",
    )


def _extract_changed_files(diff: str) -> list[str]:
    """Extract changed file paths from a unified diff."""
    files: list[str] = []
    seen: set[str] = set()
    for line in diff.splitlines():
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        path = parts[3]
        if path.startswith("b/"):
            path = path[2:]
        if path in seen:
            continue
        seen.add(path)
        files.append(path)
    return files


def _format_changed_files(diff: str) -> str:
    files = _extract_changed_files(diff)
    if not files:
        return "No tracked memory files changed."
    return ", ".join(f"`{path}`" for path in files)


def _format_dream_log_content(commit, diff: str, *, requested_sha: str | None = None) -> str:
    files_line = _format_changed_files(diff)
    lines = [
        "## Dream Update",
        "",
        "Here is the selected Dream memory change." if requested_sha else "Here is the latest Dream memory change.",
        "",
        f"- Commit: `{commit.sha}`",
        f"- Time: {commit.timestamp}",
        f"- Changed files: {files_line}",
    ]
    if diff:
        lines.extend([
            "",
            f"Use `/dream-restore {commit.sha}` to undo this change.",
            "",
            "```diff",
            diff.rstrip(),
            "```",
        ])
    else:
        lines.extend([
            "",
            "Dream recorded this version, but there is no file diff to display.",
        ])
    return "\n".join(lines)


def _format_dream_restore_list(commits: list) -> str:
    lines = [
        "## Dream Restore",
        "",
        "Choose a Dream memory version to restore. Latest first:",
        "",
    ]
    for c in commits:
        lines.append(f"- `{c.sha}` {c.timestamp} - {c.message.splitlines()[0]}")
    lines.extend([
        "",
        "Preview a version with `/dream-log <sha>` before restoring it.",
        "Restore a version with `/dream-restore <sha>`.",
    ])
    return "\n".join(lines)


async def cmd_dream_log(ctx: CommandContext) -> OutboundMessage:
    """Show what the last Dream changed.

    Default: diff of the latest commit (HEAD~1 vs HEAD).
    With /dream-log <sha>: diff of that specific commit.
    """
    store = ctx.loop.consolidator.store
    git = store.git

    if not git.is_initialized():
        if store.get_last_dream_cursor() == 0:
            msg = "Dream has not run yet. Run `/dream`, or wait for the next scheduled Dream cycle."
        else:
            msg = "Dream history is not available because memory versioning is not initialized."
        return OutboundMessage(
            channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
            content=msg, metadata={"render_as": "text"},
        )

    args = ctx.args.strip()

    if args:
        # Show diff of a specific commit
        sha = args.split()[0]
        result = git.show_commit_diff(sha)
        if not result:
            content = (
                f"Couldn't find Dream change `{sha}`.\n\n"
                "Use `/dream-restore` to list recent versions, "
                "or `/dream-log` to inspect the latest one."
            )
        else:
            commit, diff = result
            content = _format_dream_log_content(commit, diff, requested_sha=sha)
    else:
        # Default: show the latest commit's diff
        commits = git.log(max_entries=1)
        result = git.show_commit_diff(commits[0].sha) if commits else None
        if result:
            commit, diff = result
            content = _format_dream_log_content(commit, diff)
        else:
            content = "Dream memory has no saved versions yet."

    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content=content, metadata={"render_as": "text"},
    )


async def cmd_dream_restore(ctx: CommandContext) -> OutboundMessage:
    """Restore memory files from a previous dream commit.

    Usage:
        /dream-restore          — list recent commits
        /dream-restore <sha>    — revert a specific commit
    """
    store = ctx.loop.consolidator.store
    git = store.git
    if not git.is_initialized():
        return OutboundMessage(
            channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
            content="Dream history is not available because memory versioning is not initialized.",
        )

    args = ctx.args.strip()
    if not args:
        # Show recent commits for the user to pick
        commits = git.log(max_entries=10)
        if not commits:
            content = "Dream memory has no saved versions to restore yet."
        else:
            content = _format_dream_restore_list(commits)
    else:
        sha = args.split()[0]
        result = git.show_commit_diff(sha)
        changed_files = _format_changed_files(result[1]) if result else "the tracked memory files"
        new_sha = git.revert(sha)
        if new_sha:
            content = (
                f"Restored Dream memory to the state before `{sha}`.\n\n"
                f"- New safety commit: `{new_sha}`\n"
                f"- Restored files: {changed_files}\n\n"
                f"Use `/dream-log {new_sha}` to inspect the restore diff."
            )
        else:
            content = (
                f"Couldn't restore Dream change `{sha}`.\n\n"
                "It may not exist, or it may be the first saved version with no earlier state to restore."
            )
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content=content, metadata={"render_as": "text"},
    )


_HISTORY_DEFAULT_COUNT = 10
_HISTORY_MAX_COUNT = 50
_HISTORY_MAX_CONTENT_CHARS = 200


def _format_history_message(msg: dict) -> str | None:
    """Format a single history message for display. Returns None to skip."""
    role = msg.get("role")
    if role not in ("user", "assistant"):
        return None
    content = msg.get("content") or ""
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        content = " ".join(parts)
    content = str(content).strip()
    if not content:
        return None
    if len(content) > _HISTORY_MAX_CONTENT_CHARS:
        content = content[:_HISTORY_MAX_CONTENT_CHARS] + "…"
    label = "👤 You" if role == "user" else "🤖 Bot"
    return f"{label}: {content}"


async def cmd_history(ctx: CommandContext) -> OutboundMessage:
    """Show the last N messages of the current session (default 10, max 50).

    Usage: /history [count]
    """
    count = _HISTORY_DEFAULT_COUNT
    if ctx.args.strip():
        try:
            count = max(1, min(int(ctx.args.strip()), _HISTORY_MAX_COUNT))
        except ValueError:
            return OutboundMessage(
                channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
                content="Usage: /history [count] — e.g. /history 5 (default: 10, max: 50)",
                metadata=dict(ctx.msg.metadata or {}),
            )

    session = ctx.session or ctx.loop.sessions.get_or_create(ctx.key)
    history = session.get_history(max_messages=0)
    visible = [_format_history_message(m) for m in history]
    visible = [m for m in visible if m is not None]
    recent = visible[-count:]

    if not recent:
        return OutboundMessage(
            channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
            content="No conversation history yet.",
            metadata=dict(ctx.msg.metadata or {}),
        )

    header = f"Last {len(recent)} message(s):\n"
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content=header + "\n".join(recent),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_help(ctx: CommandContext) -> OutboundMessage:
    """Return available slash commands."""
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=build_help_text(),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


def _mail_runner_for_ctx(ctx: CommandContext) -> MailAutomationSessionRunner | None:
    runner = getattr(ctx.loop, "mail_automation_runner", None)
    if runner is not None:
        return runner
    config = N8NGmailAutomationConfig.from_env()
    if config is None:
        return None
    return MailAutomationSessionRunner(
        ctx.loop.sessions,
        N8NGmailAutomationClient(config),
    )


def _calendar_runner_for_ctx(ctx: CommandContext) -> CalendarAutomationSessionRunner | None:
    runner = getattr(ctx.loop, "calendar_automation_runner", None)
    if runner is not None:
        return runner
    config = N8NCalendarAutomationConfig.from_env()
    if config is None:
        return None
    return CalendarAutomationSessionRunner(
        ctx.loop.sessions,
        N8NCalendarAutomationClient(config),
    )


def _mail_command_tokens(ctx: CommandContext) -> list[str]:
    raw = ctx.raw.strip()
    first, sep, rest = raw.partition(" ")
    if first.startswith("/mail@"):
        first = first.partition("@")[0]
        raw = first if not sep else f"{first}{sep}{rest}"
    if raw.startswith("/mail"):
        raw = raw[5:].strip()
    return shlex.split(raw)


def _mail_help_text() -> str:
    return "\n".join([
        "## Mail Automation",
        "",
        "Use one of the following:",
        "- `/mail list [gmail-query]`",
        "- `/mail thread <thread-id> [more-thread-ids...]`",
        "- `/mail draft --to alice@example.com[,bob@example.com] --subject \"...\" --body \"...\" [--cc ...] [--bcc ...] [--thread thread-id]`",
        "- `/mail send` to request approval for the latest draft in this session",
        "- `/mail send --to alice@example.com --subject \"...\" --body \"...\"` to request approval for a new outbound email",
        "- `/mail approve` or `/mail deny` to resolve the pending send approval",
    ])


def _calendar_command_tokens(ctx: CommandContext) -> list[str]:
    raw = ctx.raw.strip()
    first, sep, rest = raw.partition(" ")
    if first.startswith("/calendar@"):
        first = first.partition("@")[0]
        raw = first if not sep else f"{first}{sep}{rest}"
    if raw.startswith("/calendar"):
        raw = raw[9:].strip()
    return shlex.split(raw)


def _calendar_help_text() -> str:
    return "\n".join([
        "## Calendar Automation",
        "",
        "Use one of the following:",
        "- `/calendar today` to summarize today's schedule",
        "- `/calendar check --start 2026-05-02T15:00:00+09:00 --end 2026-05-02T16:00:00+09:00`",
        "- `/calendar create --title \"Dentist\" --start 2026-05-02T15:00:00+09:00 --end 2026-05-02T16:00:00+09:00 [--location ...] [--details ...]`",
        "- Natural update: `2026-05-02 오후 3시 치과 일정을 오후 4시로 변경해줘`",
        "- Natural delete: `2026-05-02 오후 3시 치과 일정 삭제해줘`",
        "- `/calendar approve` to create the pending event",
        "- `/calendar deny` or `/calendar cancel` to cancel the pending calendar approval",
    ])


def _calendar_runner_config(runner: CalendarAutomationSessionRunner | None) -> N8NCalendarAutomationConfig | None:
    client = getattr(runner, "client", None)
    config = getattr(client, "config", None)
    return config if isinstance(config, N8NCalendarAutomationConfig) else None


def _calendar_config_status_lines(runner: CalendarAutomationSessionRunner | None) -> list[str]:
    config = _calendar_runner_config(runner)
    if config is not None:
        return [
            "- Automation: configured",
            f"- Base URL: {config.base_url}",
            f"- Summary webhook path: {config.summary_path}",
            f"- Create webhook path: {config.create_path}",
            f"- Update webhook path: {config.update_path}",
            f"- Delete webhook path: {config.delete_path}",
            f"- Timezone: {config.timezone}",
            f"- Webhook token: {'configured' if config.webhook_token else 'not set'}",
        ]
    if runner is not None:
        return [
            "- Automation: available",
            "- Configuration: provided by the active runtime runner",
        ]
    base_url = str(os.environ.get("N8N_BASE_URL") or os.environ.get("N8N_EDITOR_BASE_URL") or "").strip()
    return [
        "- Automation: not configured",
        f"- Base URL: {base_url or 'missing'}",
        "- Missing: set N8N_BASE_URL or N8N_EDITOR_BASE_URL",
        f"- Timezone: {str(os.environ.get('CALENDAR_TIMEZONE') or 'Asia/Seoul').strip() or 'Asia/Seoul'}",
    ]


def _calendar_pending_status_lines(session) -> list[str]:
    pending_input = _calendar_pending_input(session)
    if pending_input is not None:
        expected = str(pending_input.get("expected_field") or "next field")
        title = str(pending_input.get("title") or "(title pending)").strip() or "(title pending)"
        return [
            "- Pending: create input",
            f"- Event title: {title}",
            f"- Waiting for: {expected}",
        ]

    conflict = _calendar_conflict_review(session)
    if conflict is not None:
        request = conflict.get("request") if isinstance(conflict, dict) else None
        title = request.get("title") if isinstance(request, dict) else None
        return [
            "- Pending: conflict review",
            f"- Event title: {str(title or '(unknown)').strip() or '(unknown)'}",
            "- Choices: 그래도 생성 승인 요청 / 새 시간 다시 입력 / 취소",
        ]

    approval = session.metadata.get("calendar_create_approval")
    if isinstance(approval, dict):
        return [
            "- Pending: create approval",
            f"- Event title: {str(approval.get('title') or '(unknown)').strip() or '(unknown)'}",
            f"- Start: {str(approval.get('start_at') or '-').strip() or '-'}",
            f"- End: {str(approval.get('end_at') or '-').strip() or '-'}",
            "- Resolve with: /calendar approve or /calendar cancel",
        ]

    update_approval = session.metadata.get("calendar_update_approval")
    if isinstance(update_approval, dict):
        request = update_approval.get("request") if isinstance(update_approval.get("request"), dict) else {}
        return [
            "- Pending: update approval",
            f"- Event title: {str(request.get('search_title') or '(unknown)').strip() or '(unknown)'}",
            f"- New start: {str(request.get('start_at') or '-').strip() or '-'}",
            f"- New end: {str(request.get('end_at') or '-').strip() or '-'}",
            "- Resolve with: /calendar approve or /calendar cancel",
        ]

    delete_approval = session.metadata.get("calendar_delete_approval")
    if isinstance(delete_approval, dict):
        target = delete_approval.get("target") if isinstance(delete_approval.get("target"), dict) else {}
        return [
            "- Pending: delete approval",
            f"- Event title: {str(target.get('title') or '(unknown)').strip() or '(unknown)'}",
            f"- Start: {str(target.get('start_at') or '-').strip() or '-'}",
            f"- End: {str(target.get('end_at') or '-').strip() or '-'}",
            "- Resolve with: /calendar approve or /calendar cancel",
        ]

    return ["- Pending: none"]


def _calendar_status_text(ctx: CommandContext, runner: CalendarAutomationSessionRunner | None) -> str:
    session = ctx.session or ctx.loop.sessions.get_or_create(ctx.key)
    lines = _calendar_help_text().splitlines()
    lines.extend(["", "## Current status"])
    lines.extend(_calendar_config_status_lines(runner))
    lines.extend(["", "## Session state"])
    lines.extend(_calendar_pending_status_lines(session))
    return "\n".join(lines)


def _parse_csv_arg(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_mail_options(tokens: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("--"):
            index += 1
            continue
        key = token[2:]
        value = ""
        if index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
            value = tokens[index + 1]
            index += 2
        else:
            index += 1
        parsed[key] = value
    return parsed


def _parse_flag_options(tokens: list[str]) -> dict[str, str]:
    return _parse_mail_options(tokens)


def _mail_threads_content(result) -> str:
    lines = [result.title, "", result.summary]
    threads = getattr(result.details, "threads", [])
    if threads:
        lines.append("")
        for index, thread in enumerate(threads[:5], start=1):
            label = getattr(thread, "sender_summary", None) or getattr(thread, "summary", None) or ""
            subject = getattr(thread, "subject", "(No subject)")
            extra = f" ({label})" if label else ""
            lines.append(f"{index}. {subject}{extra}")
    if result.next_step:
        lines.extend(["", f"Next step: {result.next_step}"])
    return "\n".join(lines)


def _mail_draft_content(result) -> str:
    preview = result.details.preview
    recipients = ", ".join(preview.to_recipients)
    lines = [result.title, "", result.summary]
    lines.extend([
        "",
        f"To: {recipients}",
        f"Subject: {preview.subject}",
        f"Preview: {preview.body_preview}",
    ])
    if result.next_step:
        lines.extend(["", f"Next step: {result.next_step}"])
    return "\n".join(lines)


def _mail_send_content(result) -> str:
    preview = result.details.preview
    recipients = ", ".join(preview.to_recipients)
    lines = [result.title, "", result.summary]
    if recipients or preview.subject or preview.body_preview:
        lines.extend([
            "",
            f"To: {recipients or '-'}",
            f"Subject: {preview.subject or '(No subject)'}",
            f"Preview: {preview.body_preview or '-'}",
        ])
    if result.next_step:
        lines.extend(["", f"Next step: {result.next_step}"])
    return "\n".join(lines)


def _calendar_result_content(result) -> str:
    lines = [result.title, "", result.summary]
    preview = getattr(result.details, "preview", None)
    if preview is not None:
        target = getattr(result.details, "target", None)
        if target is not None:
            lines.extend([
                "",
                f"Target: {target.title}",
                f"Current: {target.start_at} -> {target.end_at}",
            ])
        lines.extend([
            "",
            f"Title: {preview.title}",
            f"When: {preview.start_at} -> {preview.end_at}",
        ])
        if getattr(preview, "location", None):
            lines.append(f"Location: {preview.location}")
        if getattr(preview, "description", None):
            lines.append(f"Details: {preview.description}")
    else:
        requested_start_at = getattr(result.details, "requested_start_at", None)
        requested_end_at = getattr(result.details, "requested_end_at", None)
        if requested_start_at and requested_end_at:
            lines.extend([
                "",
                f"When: {requested_start_at} -> {requested_end_at}",
            ])
        conflicting_events = getattr(result.details, "conflicting_events", []) or []
        if conflicting_events:
            lines.append("")
            for index, event in enumerate(conflicting_events[:5], start=1):
                lines.append(
                    f"{index}. {event.title} ({event.start_at} -> {event.end_at})"
                )
        target = getattr(result.details, "target", None)
        if target is not None:
            lines.extend([
                "",
                f"Target: {target.title}",
                f"When: {target.start_at} -> {target.end_at}",
            ])
    if result.next_step:
        lines.extend(["", f"Next step: {result.next_step}"])
    return "\n".join(lines)


def _calendar_pending_input(session) -> dict[str, Any] | None:
    payload = session.metadata.get(CALENDAR_CREATE_INPUT_METADATA_KEY)
    return payload if isinstance(payload, dict) else None


def _calendar_conflict_review(session) -> dict[str, Any] | None:
    payload = session.metadata.get(CALENDAR_CONFLICT_REVIEW_METADATA_KEY)
    return payload if isinstance(payload, dict) else None


def _calendar_pending_interaction(session) -> dict[str, Any] | None:
    payload = session.metadata.get(CALENDAR_PENDING_INTERACTION_METADATA_KEY)
    return payload if isinstance(payload, dict) else None


def _calendar_interaction_id(prefix: str) -> str:
    from uuid import uuid4

    return f"{prefix}-{uuid4().hex[:10]}"


def _calendar_timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _set_calendar_pending_interaction(session, payload: dict[str, Any]) -> None:
    now = _calendar_timestamp()
    current = _calendar_pending_interaction(session) or {}
    interaction = {
        **payload,
        "id": payload.get("id") or current.get("id") or _calendar_interaction_id("calendar-interaction"),
        "status": payload.get("status") or "pending",
        "created_at": payload.get("created_at") or current.get("created_at") or now,
        "updated_at": now,
    }
    session.metadata[CALENDAR_PENDING_INTERACTION_METADATA_KEY] = interaction


def _clear_calendar_pending_interaction(session, ctx: CommandContext | None = None) -> None:
    if session.metadata.pop(CALENDAR_PENDING_INTERACTION_METADATA_KEY, None) is not None and ctx is not None:
        ctx.loop.sessions.save(session)


def _clear_calendar_pending_input(session, ctx: CommandContext | None = None) -> None:
    changed = session.metadata.pop(CALENDAR_CREATE_INPUT_METADATA_KEY, None) is not None
    changed = session.metadata.pop(CALENDAR_PENDING_INTERACTION_METADATA_KEY, None) is not None or changed
    if changed and ctx is not None:
        ctx.loop.sessions.save(session)


def _clear_calendar_conflict_review(session, ctx: CommandContext | None = None) -> None:
    changed = session.metadata.pop(CALENDAR_CONFLICT_REVIEW_METADATA_KEY, None) is not None
    changed = session.metadata.pop(CALENDAR_PENDING_INTERACTION_METADATA_KEY, None) is not None or changed
    if changed and ctx is not None:
        ctx.loop.sessions.save(session)


def _calendar_pending_payload(parsed: dict[str, str], expected_field: str) -> dict[str, Any]:
    return {
        "title": (parsed.get("title") or "").strip() or None,
        "start_at": (parsed.get("start") or "").strip() or None,
        "end_at": (parsed.get("end") or "").strip() or None,
        "location": (parsed.get("location") or "").strip() or None,
        "description": (parsed.get("details") or "").strip() or None,
        "expected_field": expected_field,
    }


def _calendar_missing_required_fields(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in ("title", "start_at", "end_at"):
        if not str(payload.get(field) or "").strip():
            missing.append(field)
    return missing


def _calendar_prompt_for_field(field: str) -> str:
    if field == "title":
        return "Calendar create needs a title. Reply with the event title, or choose 취소 to stop."
    if field == "start_at":
        return "Calendar create needs a start time. Reply with an ISO time like 2026-05-02T15:00:00+09:00, or choose 취소."
    return "Calendar create needs an end time. Reply with an ISO time like 2026-05-02T16:00:00+09:00, or choose 취소."


def _calendar_prompt_response(ctx: CommandContext, session, payload: dict[str, Any], question: str) -> OutboundMessage:
    payload["expected_field"] = payload.get("expected_field") or _calendar_missing_required_fields(payload)[0]
    session.metadata[CALENDAR_CREATE_INPUT_METADATA_KEY] = payload
    _set_calendar_pending_interaction(session, {
        "kind": "collect_input",
        "question": question,
        "buttons": CALENDAR_CREATE_CANCEL_CHOICES,
        "request": {
            "title": payload.get("title"),
            "start_at": payload.get("start_at"),
            "end_at": payload.get("end_at"),
            "location": payload.get("location"),
            "description": payload.get("description"),
        },
        "expected_field": payload.get("expected_field"),
    })
    session.add_message("assistant", question, buttons=CALENDAR_CREATE_CANCEL_CHOICES)
    ctx.loop.sessions.save(session)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=question,
        buttons=CALENDAR_CREATE_CANCEL_CHOICES,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


def _persist_calendar_result(ctx: CommandContext, session, result, *, add_message: bool = True) -> None:
    ctx.loop.sessions.set_action_result(session, result)
    if add_message and result.summary:
        session.add_message("assistant", result.summary)
    ctx.loop.sessions.save(session)


def _calendar_conflict_review_question(result) -> str:
    lines = [
        result.title,
        "",
        result.summary,
    ]
    conflicting_events = getattr(result.details, "conflicting_events", []) or []
    if conflicting_events:
        lines.extend(["", "Conflicting events:"])
        for index, event in enumerate(conflicting_events[:5], start=1):
            lines.append(f"{index}. {event.title} ({event.start_at} -> {event.end_at})")
    lines.extend([
        "",
        "Choose how to continue before approval.",
    ])
    return "\n".join(lines)


def _calendar_conflict_review_response(ctx: CommandContext, session, request: CalendarCreateRequest, result) -> OutboundMessage:
    question = _calendar_conflict_review_question(result)
    conflicting_events = getattr(result.details, "conflicting_events", []) or []
    session.metadata[CALENDAR_CONFLICT_REVIEW_METADATA_KEY] = {
        "request": request.model_dump(mode="json"),
        "question": question,
    }
    _set_calendar_pending_interaction(session, {
        "kind": "conflict_review",
        "question": question,
        "buttons": CALENDAR_CONFLICT_REVIEW_CHOICES,
        "request": request.model_dump(mode="json"),
        "conflicts": [
            event.model_dump(mode="json") if hasattr(event, "model_dump") else dict(event)
            for event in conflicting_events
        ],
    })
    _persist_calendar_result(ctx, session, result, add_message=False)
    session.add_message("assistant", question, buttons=CALENDAR_CONFLICT_REVIEW_CHOICES)
    ctx.loop.sessions.save(session)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=question,
        buttons=CALENDAR_CONFLICT_REVIEW_CHOICES,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


def _normalize_calendar_datetime(value: str, timezone: str = "Asia/Seoul") -> str | None:
    text = value.strip()
    if not text:
        return None
    normalized = text.replace(" ", "T")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        zone = ZoneInfo(timezone)
        current = datetime.now(zone)
        local_date = _extract_calendar_natural_date(text, current, roll_forward=False)
        local_time = _extract_calendar_natural_time(text)
        if local_date is None or local_time is None:
            return None
        parsed = _calendar_datetime_from_date_time(local_date, local_time, timezone)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
    return parsed.isoformat()


def _calendar_looks_like_natural_create(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized or normalized.startswith("/"):
        return False
    if any(keyword in normalized for keyword in CALENDAR_NATURAL_MUTATION_VERBS):
        return False
    return any(keyword in normalized for keyword in CALENDAR_NATURAL_CREATE_KEYWORDS) and any(
        verb in normalized for verb in CALENDAR_NATURAL_CREATE_VERBS
    )


def _extract_calendar_natural_date(
    text: str,
    now: datetime,
    *,
    roll_forward: bool = True,
) -> datetime.date | None:
    iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if iso_match:
        try:
            return datetime(
                int(iso_match.group(1)),
                int(iso_match.group(2)),
                int(iso_match.group(3)),
            ).date()
        except ValueError:
            return None

    korean_year_match = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
    if korean_year_match:
        try:
            return datetime(
                int(korean_year_match.group(1)),
                int(korean_year_match.group(2)),
                int(korean_year_match.group(3)),
            ).date()
        except ValueError:
            return None

    month_day_match = re.search(r"(?<!년\s)(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
    if month_day_match:
        try:
            candidate = datetime(
                now.year,
                int(month_day_match.group(1)),
                int(month_day_match.group(2)),
            ).date()
        except ValueError:
            return None
        if roll_forward and candidate < now.date():
            try:
                return datetime(now.year + 1, candidate.month, candidate.day).date()
            except ValueError:
                return candidate
        return candidate

    if "모레" in text:
        return (now + timedelta(days=2)).date()
    if "내일" in text:
        return (now + timedelta(days=1)).date()
    if "오늘" in text:
        return now.date()

    weekday_match = re.search(r"다음\s*([월화수목금토일])\s*요일", text)
    if weekday_match:
        target_weekday = CALENDAR_WEEKDAY_INDEX[weekday_match.group(1)]
        days_ahead = target_weekday - now.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return (now + timedelta(days=days_ahead)).date()

    return None


def _extract_calendar_natural_time(text: str) -> tuple[int, int] | None:
    colon_match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if colon_match:
        hour = int(colon_match.group(1))
        minute = int(colon_match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
        return None

    time_match = re.search(
        r"(오전|오후)?\s*(\d{1,2})\s*시(?!간)\s*(반|\d{1,2}\s*분)?",
        text,
    )
    if not time_match:
        return None

    marker = time_match.group(1)
    hour = int(time_match.group(2))
    minute_text = (time_match.group(3) or "").strip()
    minute = 30 if minute_text == "반" else 0
    minute_match = re.search(r"(\d{1,2})", minute_text)
    if minute_match:
        minute = int(minute_match.group(1))

    if marker == "오후" and hour < 12:
        hour += 12
    elif marker == "오전" and hour == 12:
        hour = 0

    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None


def _extract_calendar_natural_duration_minutes(text: str) -> int | None:
    if re.search(r"한\s*시간", text):
        return 60
    hour_match = re.search(r"(\d{1,2})\s*시간(?:\s*(\d{1,2})\s*분)?", text)
    if hour_match:
        hours = int(hour_match.group(1))
        minutes = int(hour_match.group(2) or "0")
        total = hours * 60 + minutes
        return total if total > 0 else None
    minute_match = re.search(r"(\d{1,3})\s*분\s*(?:동안|짜리)?", text)
    if minute_match:
        minutes = int(minute_match.group(1))
        return minutes if minutes > 0 else None
    return None


def _strip_calendar_natural_title(text: str) -> str | None:
    cleaned = text.strip()
    removal_patterns = [
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일",
        r"\d{1,2}\s*월\s*\d{1,2}\s*일",
        r"다음\s*[월화수목금토일]\s*요일",
        r"오늘|내일|모레",
        r"(오전|오후)?\s*\d{1,2}\s*시(?!간)\s*(반|\d{1,2}\s*분)?\s*(부터|에)?",
        r"\b\d{1,2}:\d{2}\b\s*(부터|에)?",
        r"한\s*시간",
        r"\d{1,2}\s*시간(?:\s*\d{1,2}\s*분)?",
        r"\d{1,3}\s*분\s*(동안|짜리)?",
    ]
    for pattern in removal_patterns:
        cleaned = re.sub(pattern, " ", cleaned)
    for token in (
        "캘린더", "일정", "예약", "등록", "추가", "넣어줘", "넣어", "잡아줘", "잡아",
        "만들어줘", "만들어", "생성해줘", "생성", "해줘", "해주세요", "부탁해",
    ):
        cleaned = cleaned.replace(token, " ")
    cleaned = re.sub(r"[.,!?]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" 은는이가을를에으로 ")
    return cleaned or None


def _parse_calendar_natural_create(
    text: str,
    *,
    timezone: str = "Asia/Seoul",
    now: datetime | None = None,
) -> dict[str, Any] | None:
    if not _calendar_looks_like_natural_create(text):
        return None

    zone = ZoneInfo(timezone)
    current = now.astimezone(zone) if now else datetime.now(zone)
    local_date = _extract_calendar_natural_date(text, current)
    local_time = _extract_calendar_natural_time(text)
    duration_minutes = _extract_calendar_natural_duration_minutes(text)
    title = _strip_calendar_natural_title(text)

    start_at = None
    end_at = None
    if local_time is not None:
        if local_date is None:
            candidate = datetime.combine(current.date(), datetime.min.time(), tzinfo=zone).replace(
                hour=local_time[0],
                minute=local_time[1],
            )
            if candidate <= current:
                candidate += timedelta(days=1)
        else:
            candidate = datetime.combine(local_date, datetime.min.time(), tzinfo=zone).replace(
                hour=local_time[0],
                minute=local_time[1],
            )
        start_at = candidate.isoformat()
        if duration_minutes:
            end_at = (candidate + timedelta(minutes=duration_minutes)).isoformat()

    return {
        "title": title,
        "start_at": start_at,
        "end_at": end_at,
        "location": None,
        "description": text.strip(),
    }


def _calendar_looks_like_natural_delete(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized or normalized.startswith("/"):
        return False
    return any(keyword in normalized for keyword in CALENDAR_NATURAL_CREATE_KEYWORDS) and any(
        verb in normalized for verb in CALENDAR_NATURAL_DELETE_VERBS
    )


def _calendar_looks_like_natural_update(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized or normalized.startswith("/"):
        return False
    return any(keyword in normalized for keyword in CALENDAR_NATURAL_CREATE_KEYWORDS) and any(
        verb in normalized for verb in CALENDAR_NATURAL_UPDATE_VERBS
    )


def _extract_calendar_natural_times(text: str) -> list[tuple[int, int]]:
    times: list[tuple[int, int]] = []
    for match in re.finditer(r"\b(\d{1,2}):(\d{2})\b", text):
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            times.append((hour, minute))

    pattern = r"(오전|오후)?\s*(\d{1,2})\s*시(?!간)\s*(반|\d{1,2}\s*분)?"
    for match in re.finditer(pattern, text):
        marker = match.group(1)
        hour = int(match.group(2))
        minute_text = (match.group(3) or "").strip()
        minute = 30 if minute_text == "반" else 0
        minute_match = re.search(r"(\d{1,2})", minute_text)
        if minute_match:
            minute = int(minute_match.group(1))
        if marker == "오후" and hour < 12:
            hour += 12
        elif marker == "오전" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59 and (hour, minute) not in times:
            times.append((hour, minute))
    return times


def _strip_calendar_natural_mutation_title(text: str) -> str | None:
    cleaned = text.strip()
    removal_patterns = [
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일",
        r"\d{1,2}\s*월\s*\d{1,2}\s*일",
        r"다음\s*[월화수목금토일]\s*요일",
        r"오늘|내일|모레",
        r"(오전|오후)?\s*\d{1,2}\s*시(?!간)\s*(반|\d{1,2}\s*분)?\s*(부터|에|로|으로)?",
        r"\b\d{1,2}:\d{2}\b\s*(부터|에|로|으로)?",
        r"한\s*시간",
        r"\d{1,2}\s*시간(?:\s*\d{1,2}\s*분)?",
        r"\d{1,3}\s*분\s*(동안|짜리)?",
    ]
    for pattern in removal_patterns:
        cleaned = re.sub(pattern, " ", cleaned)
    for token in (
        "캘린더", "일정", "예약", "변경해줘", "변경", "수정해줘", "수정", "옮겨줘", "옮겨",
        "미뤄줘", "미뤄", "당겨줘", "당겨", "삭제해줘", "삭제", "지워줘", "지워",
        "취소해줘", "취소", "해줘", "해주세요", "부탁해",
    ):
        cleaned = cleaned.replace(token, " ")
    cleaned = re.sub(r"[.,!?]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" 은는이가을를에으로로 ")
    return cleaned or None


def _calendar_day_window(local_date, timezone: str = "Asia/Seoul") -> tuple[str, str]:
    zone = ZoneInfo(timezone)
    start = datetime.combine(local_date, datetime.min.time(), tzinfo=zone)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return start.isoformat(), end.isoformat()


def _calendar_datetime_from_date_time(local_date, local_time: tuple[int, int], timezone: str = "Asia/Seoul") -> datetime:
    zone = ZoneInfo(timezone)
    return datetime.combine(local_date, datetime.min.time(), tzinfo=zone).replace(
        hour=local_time[0],
        minute=local_time[1],
    )


def _calendar_parse_event_datetime(value: str, timezone: str = "Asia/Seoul") -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
    return parsed.astimezone(ZoneInfo(timezone))


async def _calendar_find_single_target(
    ctx: CommandContext,
    runner: CalendarAutomationSessionRunner,
    *,
    search_title: str,
    local_date,
    local_time: tuple[int, int] | None,
    purpose: str,
) -> tuple[CalendarEventSummary | None, str | None]:
    time_min, time_max = _calendar_day_window(local_date)
    list_result = await runner.client.list_events(
        message="일정 후보를 찾아줘",
        channel=ctx.key.split(":", 1)[0] if ":" in ctx.key else "websocket",
        session_id=ctx.key,
        user_id="primary-user",
        time_min=time_min,
        time_max=time_max,
        window_label=local_date.isoformat(),
    )
    if list_result.status != "completed":
        return None, list_result.summary

    normalized_title = search_title.lower()
    matches: list[CalendarEventSummary] = []
    for event in list_result.details.events:
        if normalized_title and normalized_title not in event.title.lower():
            continue
        if local_time is not None:
            start = _calendar_parse_event_datetime(event.start_at)
            if start is None or (start.hour, start.minute) != local_time:
                continue
        matches.append(event)

    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, f"{purpose}할 일정 '{search_title}' 을 찾지 못했습니다. 날짜와 시간을 더 구체적으로 알려주세요."

    lines = [f"{purpose}할 일정 후보가 여러 개입니다. 제목과 시간을 더 구체적으로 알려주세요.", ""]
    for index, event in enumerate(matches[:5], start=1):
        lines.append(f"{index}. {event.title} ({event.start_at} -> {event.end_at})")
    return None, "\n".join(lines)


async def _calendar_update_request_outbound(
    ctx: CommandContext,
    runner: CalendarAutomationSessionRunner,
    request: CalendarUpdateRequest,
    target: CalendarEventSummary | None,
) -> OutboundMessage:
    result = await runner.request_update_approval(ctx.key, request, target)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=_calendar_result_content(result),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def _calendar_delete_request_outbound(
    ctx: CommandContext,
    runner: CalendarAutomationSessionRunner,
    request: CalendarDeleteRequest,
    target: CalendarEventSummary,
) -> OutboundMessage:
    result = await runner.request_delete_approval(ctx.key, request, target)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=_calendar_result_content(result),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def _calendar_create_request_outbound(
    ctx: CommandContext,
    runner: CalendarAutomationSessionRunner,
    request: CalendarCreateRequest,
) -> OutboundMessage:
    conflict = await runner.client.find_conflicts(
        start_at=request.start_at,
        end_at=request.end_at,
        channel=ctx.key.split(":", 1)[0] if ":" in ctx.key else "websocket",
        session_id=ctx.key,
        user_id="primary-user",
    )
    session = ctx.session or ctx.loop.sessions.get_or_create(ctx.key)
    if getattr(conflict.details, "available", False):
        result = await runner.request_create_approval(ctx.key, request)
        content = _calendar_result_content(result)
    elif getattr(conflict.details, "reason", None) == "overlap_detected":
        return _calendar_conflict_review_response(ctx, session, request, conflict)
    else:
        _persist_calendar_result(ctx, session, conflict)
        content = _calendar_result_content(conflict)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def _calendar_pending_input_interceptor(ctx: CommandContext) -> OutboundMessage | None:
    session = ctx.session
    if session is None:
        return None
    pending = _calendar_pending_input(session)
    if pending is None:
        return None

    answer = ctx.raw.strip()
    if not answer:
        return None
    if answer.lower() in {"취소", "cancel", "stop", "abort"}:
        _clear_calendar_pending_input(session, ctx)
        session.add_message("assistant", "Calendar create input was cancelled.")
        ctx.loop.sessions.save(session)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Calendar create input was cancelled.",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    expected_field = str(pending.get("expected_field") or "title")
    if expected_field == "title":
        pending["title"] = answer
    elif expected_field in {"start_at", "end_at"}:
        normalized = _normalize_calendar_datetime(answer)
        if normalized is None:
            return _calendar_prompt_response(
                ctx,
                session,
                pending,
                f"The {expected_field[:-3] if expected_field.endswith('_at') else expected_field} time must be ISO format, for example 2026-05-02T15:00:00+09:00.",
            )
        pending[expected_field] = normalized
    else:
        return None

    if pending.get("start_at") and pending.get("end_at") and pending["end_at"] <= pending["start_at"]:
        pending["end_at"] = None
        pending["expected_field"] = "end_at"
        return _calendar_prompt_response(
            ctx,
            session,
            pending,
            "Calendar create needs an end time later than the start time. Reply with a later ISO end time, or choose 취소.",
        )

    missing = _calendar_missing_required_fields(pending)
    if missing:
        next_field = missing[0]
        pending["expected_field"] = next_field
        return _calendar_prompt_response(ctx, session, pending, _calendar_prompt_for_field(next_field))

    _clear_calendar_pending_input(session)
    ctx.loop.sessions.save(session)
    runner = _calendar_runner_for_ctx(ctx)
    if runner is None:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Calendar automation is not configured. Set N8N_BASE_URL and the Calendar webhook env vars first.",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )
    result = await runner.request_create_approval(
        ctx.key,
        CalendarCreateRequest(
            title=str(pending.get("title") or "").strip(),
            start_at=str(pending.get("start_at") or "").strip(),
            end_at=str(pending.get("end_at") or "").strip(),
            location=str(pending.get("location") or "").strip() or None,
            description=str(pending.get("description") or "").strip() or None,
        ),
    )
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=_calendar_result_content(result),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def _calendar_conflict_review_interceptor(ctx: CommandContext) -> OutboundMessage | None:
    session = ctx.session
    if session is None:
        return None
    pending = _calendar_conflict_review(session)
    if pending is None:
        return None

    answer = ctx.raw.strip()
    if not answer:
        return None

    request_payload = pending.get("request")
    if not isinstance(request_payload, dict):
        _clear_calendar_conflict_review(session, ctx)
        return None

    try:
        request = CalendarCreateRequest.model_validate(request_payload)
    except Exception:
        _clear_calendar_conflict_review(session, ctx)
        return None

    normalized = answer.strip().lower()
    if normalized in {"취소", "cancel", "stop", "abort"}:
        _clear_calendar_conflict_review(session)
        session.add_message("assistant", "Calendar create request was cancelled before approval.")
        ctx.loop.sessions.save(session)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Calendar create request was cancelled before approval.",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    if answer == CALENDAR_CONFLICT_FORCE_CREATE_LABEL:
        _clear_calendar_conflict_review(session)
        ctx.loop.sessions.save(session)
        runner = _calendar_runner_for_ctx(ctx)
        if runner is None:
            return OutboundMessage(
                channel=ctx.msg.channel,
                chat_id=ctx.msg.chat_id,
                content="Calendar automation is not configured. Set N8N_BASE_URL and the Calendar webhook env vars first.",
                metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
            )
        result = await runner.request_create_approval(ctx.key, request)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=_calendar_result_content(result),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    if answer == CALENDAR_CONFLICT_RESCHEDULE_LABEL:
        _clear_calendar_conflict_review(session)
        payload = {
            "title": request.title,
            "start_at": None,
            "end_at": None,
            "location": request.location,
            "description": request.description,
            "expected_field": "start_at",
        }
        return _calendar_prompt_response(
            ctx,
            session,
            payload,
            _calendar_prompt_for_field("start_at"),
        )

    question = str(pending.get("question") or "Choose how to continue before approval.")
    session.add_message("assistant", question, buttons=CALENDAR_CONFLICT_REVIEW_CHOICES)
    ctx.loop.sessions.save(session)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=question,
        buttons=CALENDAR_CONFLICT_REVIEW_CHOICES,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


def _calendar_pending_resolution_kind(session) -> str | None:
    if _calendar_pending_input(session) is not None:
        return "input"
    if _calendar_conflict_review(session) is not None:
        return "conflict"
    if isinstance(session.metadata.get(CALENDAR_UPDATE_APPROVAL_METADATA_KEY), dict):
        return "approval"
    if isinstance(session.metadata.get(CALENDAR_DELETE_APPROVAL_METADATA_KEY), dict):
        return "approval"
    if isinstance(session.metadata.get(CALENDAR_CREATE_APPROVAL_METADATA_KEY), dict):
        return "approval"
    return None


def _calendar_natural_resolution_intent(text: str) -> str | None:
    normalized = text.strip().lower()
    if not normalized or normalized.startswith("/"):
        return None
    if any(word in normalized for word in CALENDAR_NATURAL_CANCEL_WORDS):
        return "cancel"
    if any(word in normalized for word in CALENDAR_NATURAL_APPROVE_WORDS):
        return "approve"
    return None


async def _calendar_natural_resolution_interceptor(ctx: CommandContext) -> OutboundMessage | None:
    session = ctx.session
    if session is None:
        return None
    pending_kind = _calendar_pending_resolution_kind(session)
    if pending_kind is None:
        return None

    intent = _calendar_natural_resolution_intent(ctx.raw)
    if intent is None:
        return None
    if intent == "approve" and pending_kind == "input":
        return None

    if intent == "approve" and pending_kind == "conflict":
        synthetic_ctx = CommandContext(
            msg=ctx.msg,
            session=session,
            key=ctx.key,
            raw=CALENDAR_CONFLICT_FORCE_CREATE_LABEL,
            loop=ctx.loop,
        )
        return await _calendar_conflict_review_interceptor(synthetic_ctx)

    command = "/calendar approve" if intent == "approve" else "/calendar cancel"
    synthetic_ctx = CommandContext(
        msg=ctx.msg,
        session=session,
        key=ctx.key,
        raw=command,
        loop=ctx.loop,
    )
    return await cmd_calendar(synthetic_ctx)


async def _calendar_natural_update_interceptor(ctx: CommandContext) -> OutboundMessage | None:
    if not _calendar_looks_like_natural_update(ctx.raw):
        return None

    zone = ZoneInfo("Asia/Seoul")
    current = datetime.now(zone)
    local_date = _extract_calendar_natural_date(ctx.raw, current, roll_forward=False)
    times = _extract_calendar_natural_times(ctx.raw)
    title = _strip_calendar_natural_mutation_title(ctx.raw)
    if local_date is None or len(times) < 2 or not title:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Calendar update needs a title, date, current time, and new time. For example: 2026-05-05 오후 3시 치과 일정을 오후 4시로 변경해줘",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    runner = _calendar_runner_for_ctx(ctx)
    if runner is None:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Calendar automation is not configured. Set N8N_BASE_URL and the Calendar webhook env vars first.",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    old_time, new_time = times[0], times[-1]
    target, error = await _calendar_find_single_target(
        ctx,
        runner,
        search_title=title,
        local_date=local_date,
        local_time=old_time,
        purpose="변경",
    )
    if target is None:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=error or "변경할 일정을 찾지 못했습니다.",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    target_start = _calendar_parse_event_datetime(target.start_at) or _calendar_datetime_from_date_time(local_date, old_time)
    target_end = _calendar_parse_event_datetime(target.end_at) or (target_start + timedelta(hours=1))
    duration = target_end - target_start
    if duration.total_seconds() <= 0:
        duration = timedelta(hours=1)
    new_start = _calendar_datetime_from_date_time(local_date, new_time)
    new_end = new_start + duration
    request = CalendarUpdateRequest(
        search_title=target.title,
        new_title=target.title,
        start_at=new_start.isoformat(),
        end_at=new_end.isoformat(),
        search_time_min=target.start_at,
        search_time_max=target.end_at,
        event_id=target.event_id,
    )
    return await _calendar_update_request_outbound(ctx, runner, request, target)


async def _calendar_natural_delete_interceptor(ctx: CommandContext) -> OutboundMessage | None:
    if not _calendar_looks_like_natural_delete(ctx.raw):
        return None

    zone = ZoneInfo("Asia/Seoul")
    current = datetime.now(zone)
    local_date = _extract_calendar_natural_date(ctx.raw, current, roll_forward=False)
    times = _extract_calendar_natural_times(ctx.raw)
    title = _strip_calendar_natural_mutation_title(ctx.raw)
    if local_date is None or not title:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Calendar delete needs a title and date. For example: 2026-05-05 오후 3시 치과 일정 삭제해줘",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    runner = _calendar_runner_for_ctx(ctx)
    if runner is None:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Calendar automation is not configured. Set N8N_BASE_URL and the Calendar webhook env vars first.",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    target, error = await _calendar_find_single_target(
        ctx,
        runner,
        search_title=title,
        local_date=local_date,
        local_time=times[0] if times else None,
        purpose="삭제",
    )
    if target is None:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=error or "삭제할 일정을 찾지 못했습니다.",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    request = CalendarDeleteRequest(
        search_title=target.title,
        search_time_min=target.start_at,
        search_time_max=target.end_at,
        event_id=target.event_id,
    )
    return await _calendar_delete_request_outbound(ctx, runner, request, target)


async def _calendar_natural_create_interceptor(ctx: CommandContext) -> OutboundMessage | None:
    parsed = _parse_calendar_natural_create(ctx.raw)
    if parsed is None:
        return None

    session = ctx.session or ctx.loop.sessions.get_or_create(ctx.key)
    missing = _calendar_missing_required_fields(parsed)
    if missing:
        parsed["expected_field"] = missing[0]
        return _calendar_prompt_response(
            ctx,
            session,
            parsed,
            _calendar_prompt_for_field(parsed["expected_field"]),
        )

    runner = _calendar_runner_for_ctx(ctx)
    if runner is None:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Calendar automation is not configured. Set N8N_BASE_URL and the Calendar webhook env vars first.",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    request = CalendarCreateRequest(
        title=str(parsed.get("title") or "").strip(),
        start_at=str(parsed.get("start_at") or "").strip(),
        end_at=str(parsed.get("end_at") or "").strip(),
        location=str(parsed.get("location") or "").strip() or None,
        description=str(parsed.get("description") or "").strip() or None,
    )
    return await _calendar_create_request_outbound(ctx, runner, request)


async def cmd_mail(ctx: CommandContext) -> OutboundMessage:
    """Run phase-1 Gmail pilot actions through the mail automation runner."""
    runner = _mail_runner_for_ctx(ctx)
    if runner is None:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Mail automation is not configured. Set N8N_BASE_URL and the Gmail webhook env vars first.",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    tokens = _mail_command_tokens(ctx)
    if not tokens:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=_mail_help_text(),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    subcommand = tokens[0].lower()
    if subcommand == "list":
        query = " ".join(tokens[1:]).strip() or "newer_than:7d"
        result = await runner.list_important_threads(ctx.key, search_query=query, limit=5)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=_mail_threads_content(result),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    if subcommand == "thread":
        thread_ids = [token for token in tokens[1:] if token.strip()]
        if not thread_ids:
            content = "Usage: /mail thread <thread-id> [more-thread-ids...]"
        else:
            result = await runner.summarize_threads(ctx.key, thread_ids=thread_ids)
            content = _mail_threads_content(result)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=content,
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    if subcommand == "draft":
        parsed = _parse_mail_options(tokens[1:])
        to_recipients = _parse_csv_arg(parsed.get("to"))
        subject = (parsed.get("subject") or "").strip()
        body = (parsed.get("body") or "").strip()
        if not to_recipients or not subject or not body:
            content = (
                "Usage: /mail draft --to alice@example.com --subject \"Budget follow-up\" "
                "--body \"Sharing the revised budget\" [--cc ...] [--bcc ...] [--thread thread-id]"
            )
        else:
            result = await runner.create_draft(
                ctx.key,
                MailDraftRequest(
                    to_recipients=to_recipients,
                    cc_recipients=_parse_csv_arg(parsed.get("cc")),
                    bcc_recipients=_parse_csv_arg(parsed.get("bcc")),
                    subject=subject,
                    body=body,
                    thread_id=(parsed.get("thread") or "").strip() or None,
                ),
            )
            content = _mail_draft_content(result)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=content,
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    if subcommand == "send":
        parsed = _parse_mail_options(tokens[1:])
        has_explicit_payload = any(parsed.get(key) for key in ("to", "subject", "body"))
        if has_explicit_payload:
            to_recipients = _parse_csv_arg(parsed.get("to"))
            subject = (parsed.get("subject") or "").strip()
            body = (parsed.get("body") or "").strip()
            if not to_recipients or not subject or not body:
                content = (
                    "Usage: /mail send --to alice@example.com --subject \"Budget follow-up\" "
                    "--body \"Sharing the revised budget\" [--cc ...] [--bcc ...] [--thread thread-id]"
                )
            else:
                result = await runner.request_send_approval(
                    ctx.key,
                    MailSendRequest(
                        to_recipients=to_recipients,
                        cc_recipients=_parse_csv_arg(parsed.get("cc")),
                        bcc_recipients=_parse_csv_arg(parsed.get("bcc")),
                        subject=subject,
                        body=body,
                        thread_id=(parsed.get("thread") or "").strip() or None,
                        draft_id=(parsed.get("draft") or "").strip() or None,
                    ),
                )
                content = _mail_send_content(result)
        else:
            result = await runner.request_send_from_latest_draft(ctx.key)
            content = _mail_send_content(result)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=content,
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    if subcommand == "approve":
        result = await runner.approve_send(ctx.key)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=_mail_send_content(result),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    if subcommand == "deny":
        result = await runner.deny_send(ctx.key)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=_mail_send_content(result),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=_mail_help_text(),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_calendar(ctx: CommandContext) -> OutboundMessage:
    """Run phase-1 calendar list/conflict/create actions through the calendar automation runner."""
    tokens = _calendar_command_tokens(ctx)
    runner = _calendar_runner_for_ctx(ctx)
    if not tokens or tokens[0].lower() in {"help", "status", "config", "settings"}:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=_calendar_status_text(ctx, runner),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    subcommand = tokens[0].lower()
    session = ctx.session or ctx.loop.sessions.get_or_create(ctx.key)

    if subcommand in {"cancel", "취소"}:
        if _calendar_pending_input(session) is not None:
            _clear_calendar_pending_input(session, ctx)
            session.add_message("assistant", "Calendar create input was cancelled.")
            ctx.loop.sessions.save(session)
            return OutboundMessage(
                channel=ctx.msg.channel,
                chat_id=ctx.msg.chat_id,
                content="Calendar create input was cancelled.",
                metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
            )
        if _calendar_conflict_review(session) is not None:
            _clear_calendar_conflict_review(session, ctx)
            session.add_message("assistant", "Calendar create request was cancelled before approval.")
            ctx.loop.sessions.save(session)
            return OutboundMessage(
                channel=ctx.msg.channel,
                chat_id=ctx.msg.chat_id,
                content="Calendar create request was cancelled before approval.",
                metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
            )

    if runner is None:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=_calendar_status_text(ctx, runner),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    if subcommand in {"today", "list"}:
        result = await runner.list_events(ctx.key)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=_calendar_result_content(result),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    if subcommand == "check":
        parsed = _parse_flag_options(tokens[1:])
        start_at = (parsed.get("start") or "").strip()
        end_at = (parsed.get("end") or "").strip()
        if not start_at or not end_at:
            content = "Usage: /calendar check --start 2026-05-02T15:00:00+09:00 --end 2026-05-02T16:00:00+09:00"
        else:
            result = await runner.find_conflicts(ctx.key, start_at=start_at, end_at=end_at)
            content = _calendar_result_content(result)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=content,
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    if subcommand == "create":
        parsed = _parse_flag_options(tokens[1:])
        title = (parsed.get("title") or "").strip()
        start_at = _normalize_calendar_datetime((parsed.get("start") or "").strip() or "") or (parsed.get("start") or "").strip()
        end_at = _normalize_calendar_datetime((parsed.get("end") or "").strip() or "") or (parsed.get("end") or "").strip()
        if not title or not start_at or not end_at:
            payload = _calendar_pending_payload(
                {
                    "title": title,
                    "start": start_at,
                    "end": end_at,
                    "location": (parsed.get("location") or "").strip(),
                    "details": (parsed.get("details") or "").strip(),
                },
                expected_field=_calendar_missing_required_fields(
                    {
                        "title": title,
                        "start_at": start_at,
                        "end_at": end_at,
                    }
                )[0],
            )
            return _calendar_prompt_response(
                ctx,
                ctx.session or ctx.loop.sessions.get_or_create(ctx.key),
                payload,
                _calendar_prompt_for_field(payload["expected_field"]),
            )
        else:
            request = CalendarCreateRequest(
                title=title,
                start_at=start_at,
                end_at=end_at,
                location=(parsed.get("location") or "").strip() or None,
                description=(parsed.get("details") or "").strip() or None,
            )
            return await _calendar_create_request_outbound(ctx, runner, request)

    if subcommand == "approve":
        if isinstance(session.metadata.get("calendar_update_approval"), dict):
            result = await runner.approve_update(ctx.key)
        elif isinstance(session.metadata.get("calendar_delete_approval"), dict):
            result = await runner.approve_delete(ctx.key)
        else:
            result = await runner.approve_create(ctx.key)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=_calendar_result_content(result),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    if subcommand in {"deny", "cancel", "취소"}:
        if isinstance(session.metadata.get("calendar_update_approval"), dict):
            result = await runner.deny_update(ctx.key)
        elif isinstance(session.metadata.get("calendar_delete_approval"), dict):
            result = await runner.deny_delete(ctx.key)
        else:
            result = await runner.deny_create(ctx.key)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=_calendar_result_content(result),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=_calendar_status_text(ctx, runner),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


def build_help_text() -> str:
    """Build canonical help text shared across channels."""
    lines = [
        "🐈 nanobot commands:",
        "/new — Stop current task and start a new conversation",
        "/stop — Stop the current task",
        "/restart — Restart the bot",
        "/context clear — Clear this chat's stored conversation context",
        "/clear — Shortcut for /context clear",
        "/model — Show or change the active model target",
        "/status — Show bot status",
        "/usage — Show or change the reply footer mode",
        "/mail — Run Gmail pilot read-only and draft actions",
        "/mail send|approve|deny — Resolve Gmail send approval flow",
        "/calendar — Run Calendar pilot read, check, and create approval actions",
        "/history [n] — Show the last N conversation messages (default 10)",
        "/usage — Show or change the reply footer mode",
        "/history [n] — Show the last N conversation messages (default 10)",
        "/dream — Manually trigger Dream consolidation",
        "/dream-log — Show what the last Dream changed",
        "/dream-restore — Revert memory to a previous state",
        "/help — Show available commands",
    ]
    return "\n".join(lines)


def register_builtin_commands(router: CommandRouter) -> None:
    """Register the default set of slash commands."""
    router.priority("/stop", cmd_stop)
    router.priority("/restart", cmd_restart)
    router.priority("/status", cmd_status)
    router.priority("/clear", cmd_context)
    router.exact("/new", cmd_new)
    router.exact("/clear", cmd_context)
    router.exact("/context", cmd_context)
    router.prefix("/context ", cmd_context)
    router.exact("/model", cmd_model)
    router.prefix("/model ", cmd_model)
    router.exact("/status", cmd_status)
    router.exact("/usage", cmd_usage)
    router.prefix("/usage ", cmd_usage)
    router.exact("/mail", cmd_mail)
    router.prefix("/mail ", cmd_mail)
    router.exact("/calendar", cmd_calendar)
    router.prefix("/calendar ", cmd_calendar)
    router.intercept(_calendar_natural_resolution_interceptor)
    router.intercept(_calendar_conflict_review_interceptor)
    router.intercept(_calendar_pending_input_interceptor)
    router.intercept(_calendar_natural_update_interceptor)
    router.intercept(_calendar_natural_delete_interceptor)
    router.intercept(_calendar_natural_create_interceptor)
    router.exact("/history", cmd_history)
    router.prefix("/history ", cmd_history)
    router.exact("/usage", cmd_usage)
    router.prefix("/usage ", cmd_usage)
    router.exact("/history", cmd_history)
    router.prefix("/history ", cmd_history)
    router.exact("/dream", cmd_dream)
    router.exact("/dream-log", cmd_dream_log)
    router.prefix("/dream-log ", cmd_dream_log)
    router.exact("/dream-restore", cmd_dream_restore)
    router.prefix("/dream-restore ", cmd_dream_restore)
    router.exact("/help", cmd_help)
