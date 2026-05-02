"""Built-in slash command handlers."""

from __future__ import annotations

import asyncio
import os
import shlex
import sys
from typing import Any

from nanobot.automation.calendar import (
    CalendarAutomationSessionRunner,
    CalendarCreateRequest,
    N8NCalendarAutomationClient,
    N8NCalendarAutomationConfig,
)
from nanobot.automation.mail import (
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
    if not targets:
        lines: list[str] = []
        for name, target in targets.items():
            prefix = "*" if name == active_name else "-"
            lines.append(f"{prefix} `{name}` — {describe_model_target(target)}")
        return lines

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
        "- `/calendar approve` to create the pending event",
        "- `/calendar deny` or `/calendar cancel` to cancel the pending create approval",
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
    from datetime import datetime
    from zoneinfo import ZoneInfo

    text = value.strip()
    if not text:
        return None
    normalized = text.replace(" ", "T")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
    return parsed.isoformat()


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

    if subcommand == "approve":
        result = await runner.approve_create(ctx.key)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=_calendar_result_content(result),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    if subcommand in {"deny", "cancel", "취소"}:
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
    router.exact("/new", cmd_new)
    router.exact("/model", cmd_model)
    router.prefix("/model ", cmd_model)
    router.exact("/status", cmd_status)
    router.exact("/usage", cmd_usage)
    router.prefix("/usage ", cmd_usage)
    router.exact("/mail", cmd_mail)
    router.prefix("/mail ", cmd_mail)
    router.exact("/calendar", cmd_calendar)
    router.prefix("/calendar ", cmd_calendar)
    router.intercept(_calendar_conflict_review_interceptor)
    router.intercept(_calendar_pending_input_interceptor)
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
