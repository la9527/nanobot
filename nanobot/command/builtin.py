"""Built-in slash command handlers."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from nanobot import __version__
from nanobot.bus.events import OutboundMessage
from nanobot.command.router import CommandContext, CommandRouter
from nanobot.i18n import translate as _t
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
SESSION_LOG_MODE_METADATA_KEY = "_session_log_mode"
SESSION_LOG_MODE_SKIP = "skip"
# Inlined literal values (rather than importing from nanobot.automation.calendar/mail
# or nanobot.session.continuity) to avoid pulling those modules into
# command/builtin.py's module-level import chain. command/builtin.py is imported
# very early by many test modules, and nanobot.session.__init__ eagerly imports
# nanobot.session.manager, which can trip a pydantic ToolsConfig/Config
# forward-ref rebuild ordering issue depending on which module happens to
# import nanobot.config.schema first (nanobot.agent.tools.web needs to run its
# WebToolsConfig registration before ToolsConfig.model_rebuild() is called).
ACTION_RESULT_METADATA_KEY = "action_result"
TASK_SUMMARY_METADATA_KEY = "task_summary"
CALENDAR_CREATE_APPROVAL_METADATA_KEY = "calendar_create_approval"
CALENDAR_UPDATE_APPROVAL_METADATA_KEY = "calendar_update_approval"
CALENDAR_DELETE_APPROVAL_METADATA_KEY = "calendar_delete_approval"
MAIL_LAST_DRAFT_REQUEST_METADATA_KEY = "mail_last_draft_request"
MAIL_SEND_APPROVAL_METADATA_KEY = "mail_send_approval"
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


@dataclass(frozen=True)
class BuiltinCommandSpec:
    command: str
    title: str
    description: str
    icon: str
    arg_hint: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "command": self.command,
            "title": self.title,
            "description": self.description,
            "icon": self.icon,
            "arg_hint": self.arg_hint,
        }


BUILTIN_COMMAND_SPECS: tuple[BuiltinCommandSpec, ...] = (
    BuiltinCommandSpec(
        "/new",
        "New chat",
        "Stop the current task and start a fresh conversation.",
        "square-pen",
    ),
    BuiltinCommandSpec(
        "/stop",
        "Stop current task",
        "Cancel the active agent turn for this chat.",
        "square",
    ),
    BuiltinCommandSpec(
        "/restart",
        "Restart nanobot",
        "Restart the bot process in place.",
        "rotate-cw",
    ),
    BuiltinCommandSpec(
        "/status",
        "Show status",
        "Display runtime, provider, and channel status.",
        "activity",
    ),
    BuiltinCommandSpec(
        "/model",
        "Select model target",
        "Switch model target, list available targets, or clear the override.",
        "bot",
        "[name|list|clear]",
    ),
    BuiltinCommandSpec(
        "/local-llm",
        "Manage local LLM",
        "Show or control local LLM runtime.",
        "bot",
        "[status|start|stop|restart|smoke|use|confirm] [lfm2|lfm25-8b-a1b|qwen35-base-mlx-4bit|qwen36|qwen3-vl-4b|qwen3-vl-8b|lfm25-vl-1.6b]",
    ),
    BuiltinCommandSpec(
        "/usage",
        "Set usage details",
        "Show or change the token usage detail level.",
        "gauge",
        "[off|tokens|full]",
    ),
    BuiltinCommandSpec(
        "/history",
        "Show conversation history",
        "Print the last N persisted conversation messages.",
        "history",
        "[n]",
    ),
    BuiltinCommandSpec(
        "/goal",
        "Start long-running goal",
        "Tell the agent to treat the request as a long-running goal.",
        "activity",
        "<goal>",
    ),
    BuiltinCommandSpec(
        "/dream",
        "Run Dream",
        "Manually trigger memory consolidation.",
        "sparkles",
    ),
    BuiltinCommandSpec(
        "/dream-log",
        "Show Dream log",
        "Show what the last Dream consolidation changed.",
        "book-open",
    ),
    BuiltinCommandSpec(
        "/dream-restore",
        "Restore memory",
        "Revert memory to a previous Dream snapshot.",
        "undo-2",
    ),
    BuiltinCommandSpec(
        "/skill",
        "List skills",
        "List all enabled skills available to the agent.",
        "wrench",
    ),
    BuiltinCommandSpec(
        "/help",
        "Show help",
        "List available slash commands.",
        "circle-help",
    ),
    BuiltinCommandSpec(
        "/pairing",
        "Manage pairing",
        "List, approve, deny or revoke pairing requests.",
        "shield",
        "[list|approve <code>|deny <code>|revoke <user_id>]",
    ),
)


def builtin_command_palette() -> list[dict[str, str]]:
    """Return structured command metadata for UI command palettes."""
    return [spec.as_dict() for spec in BUILTIN_COMMAND_SPECS]


async def cmd_stop(ctx: CommandContext) -> OutboundMessage:
    """Cancel all active tasks and subagents for the session."""
    loop = ctx.loop
    msg = ctx.msg
    total = await loop._cancel_active_tasks(ctx.key)
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
    with suppress(Exception):
        ctx_est, _ = loop.consolidator.estimate_session_prompt_tokens(session)
    if ctx_est <= 0:
        ctx_est = loop._last_usage.get("prompt_tokens", 0)

    # Fetch web search provider usage (best-effort, never blocks the response)
    search_usage_text: str | None = None
    # Never let usage fetch break /status
    with suppress(Exception):
        from nanobot.utils.searchusage import fetch_search_usage
        web_cfg = getattr(loop, "web_config", None)
        search_cfg = getattr(web_cfg, "search", None) if web_cfg else None
        if search_cfg is not None:
            provider = getattr(search_cfg, "provider", "duckduckgo")
            api_key = getattr(search_cfg, "api_key", "") or None
            usage = await fetch_search_usage(provider=provider, api_key=api_key)
            search_usage_text = usage.format()
    active_tasks = loop._active_tasks.get(ctx.key, [])
    task_count = sum(1 for t in active_tasks if not t.done())
    with suppress(Exception):
        task_count += loop.subagents.get_running_count_by_session(ctx.key)
    content = build_status_content(
        version=__version__, model=status_snapshot["model"],
        start_time=loop._start_time, last_usage=status_snapshot["usage"],
        context_window_tokens=status_snapshot["context_window_tokens"],
        session_msg_count=len(session.get_history(max_messages=0)),
        context_tokens_estimate=ctx_est,
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


async def cmd_new(ctx: CommandContext) -> OutboundMessage:
    """Stop active task and start a fresh session."""
    loop = ctx.loop
    await loop._cancel_active_tasks(ctx.key)
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    owner_profile = session.metadata.get("owner_profile") if isinstance(session.metadata, dict) else None
    locale = owner_profile.get("preferred_language") if isinstance(owner_profile, dict) else None
    if not isinstance(locale, str) or not locale.strip():
        locale = None
    snapshot = session.messages[session.last_consolidated:]
    session.clear()
    loop.sessions.save(session)
    loop.sessions.invalidate(session.key)
    if snapshot:
        loop._schedule_background(loop.consolidator.archive(snapshot, session_key=ctx.key))
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content=_t("builtin.new_session.started", locale=locale),
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


def _format_preset_names(names: list[str]) -> str:
    return ", ".join(f"`{name}`" for name in names) if names else "(none configured)"


def _model_preset_names(loop) -> list[str]:
    names = set(loop.model_presets)
    names.add("default")
    return ["default", *sorted(name for name in names if name != "default")]


def _active_model_preset_name(loop) -> str:
    return loop.model_preset or "default"


def _command_error_message(exc: Exception) -> str:
    return str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc)


def _model_command_status(loop) -> str:
    names = _model_preset_names(loop)
    active = _active_model_preset_name(loop)
    return "\n".join([
        "## Model",
        f"- Current model: `{loop.model}`",
        f"- Current preset: `{active}`",
        f"- Available presets: {_format_preset_names(names)}",
    ])


async def cmd_model(ctx: CommandContext) -> OutboundMessage:
    """Show or switch the active model.

    When ``runtime_config`` model targets are configured (smart-router or
    other named targets), this becomes a per-session target switcher.
    Otherwise it falls back to the original global model-preset switcher.
    """
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    targets = loop.get_available_model_targets()
    if targets:
        return await _cmd_model_target(ctx, loop, session, targets)
    return await _cmd_model_preset(ctx, loop)


async def _cmd_model_target(
    ctx: CommandContext, loop: Any, session: Session, targets: dict[str, Any]
) -> OutboundMessage:
    from nanobot.model_targets import DEFAULT_MODEL_TARGET_NAME, describe_model_target

    active_name = loop.get_active_model_target_name(session)
    args = ctx.args.strip().lower()

    def _render_targets() -> list[str]:
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


async def _cmd_model_preset(ctx: CommandContext, loop: Any) -> OutboundMessage:
    """Show or switch model presets."""
    args = ctx.args.strip()
    metadata = {**dict(ctx.msg.metadata or {}), "render_as": "text"}

    if not args:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=_model_command_status(loop),
            metadata=metadata,
        )

    parts = args.split()
    if len(parts) != 1:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Usage: `/model [preset]`",
            metadata=metadata,
        )

    name = parts[0]
    try:
        loop.set_model_preset(name)
    except (KeyError, ValueError) as exc:
        names = _model_preset_names(loop)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=(
                f"Could not switch model preset: {_command_error_message(exc)}\n\n"
                f"Available presets: {_format_preset_names(names)}"
            ),
            metadata=metadata,
        )

    max_tokens = getattr(getattr(loop.provider, "generation", None), "max_tokens", None)
    lines = [
        f"Switched model preset to `{loop.model_preset}`.",
        f"- Model: `{loop.model}`",
        f"- Context window: {loop.context_window_tokens}",
    ]
    if max_tokens is not None:
        lines.append(f"- Max output tokens: {max_tokens}")
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="\n".join(lines),
        metadata=metadata,
    )


async def cmd_local_llm(ctx: CommandContext) -> OutboundMessage:
    """Show or control the local LLM runtime and default local route."""
    from nanobot.local_llm_control import LocalLlmError, default_controller

    args = ctx.args.strip().lower()
    parts = args.split()
    action = parts[0] if parts else "status"
    target = parts[1] if len(parts) > 1 else "qwen36"
    controller = default_controller()
    confirm_actions = {"restart", "stop", "use"}

    def _render_status(payload: dict[str, Any]) -> str:
        lines = [
            "## Local LLM",
            "",
            f"Default: `{payload.get('default_target')}` -> {payload.get('default_model')}",
            f"Endpoint: {payload.get('default_api_base')}",
            "",
        ]
        for row in payload.get("targets", []):
            if not isinstance(row, dict):
                continue
            markers: list[str] = []
            markers.append("running" if row.get("running") else "stopped")
            markers.append("endpoint ok" if row.get("endpoint_ok") else "endpoint unavailable")
            if row.get("supports_vision"):
                markers.append(_t("local_llm.status.vision_supported"))
            elif row.get("hybrid_vision_target"):
                markers.append(
                    _t("local_llm.status.hybrid_ready")
                    if row.get("hybrid_vision_ready")
                    else _t("local_llm.status.hybrid_unavailable")
                )
            elif row.get("vision_check_ok"):
                markers.append(_t("local_llm.status.vision_unsupported"))
            else:
                markers.append(_t("local_llm.status.vision_unavailable"))
            if row.get("management_mode") == "broker":
                holders = int(row.get("holder_count") or 0)
                markers.append(_t("local_llm.status.broker"))
                markers.append(_t("local_llm.status.holders", count=holders))
            elif row.get("management_mode") == "on_demand":
                markers.append(_t("local_llm.status.on_demand"))
            if row.get("runtime_warming_up"):
                markers.append(_t("local_llm.status.warming_up"))
            if row.get("is_default"):
                markers.append("default")
            prefix = "*" if row.get("is_default") else "-"
            lines.append(f"{prefix} `{row.get('name')}` — {', '.join(markers)}")
            holders = row.get("holders")
            if isinstance(holders, list) and holders:
                lines.append(f"  holders: {', '.join(str(holder) for holder in holders)}")
            hybrid_message = str(row.get("hybrid_vision_check_message") or "").strip()
            vision_message = str(row.get("vision_check_message") or "").strip()
            if row.get("hybrid_vision_target") and hybrid_message:
                lines.append(f"  hybrid: {hybrid_message}")
            elif vision_message:
                lines.append(f"  vision: {vision_message}")
        smart_router_local_message = str(payload.get("smart_router_local_image_message") or "").strip()
        if smart_router_local_message:
            lines.extend(["", f"smart-router-local: {smart_router_local_message}"])
        lines.extend([
            "",
            "Use `/local-llm use qwen36` to change the default local LLM.",
            "Use `/model smart-router-local` to force the local tier for this chat.",
        ])
        return "\n".join(lines)

    try:
        if action in ("", "status", "list"):
            content = _render_status(controller.status())
        else:
            if action == "confirm":
                action = parts[1] if len(parts) > 1 else ""
                target = parts[2] if len(parts) > 2 else "qwen36"
            elif action in confirm_actions:
                content = _t("local_llm.confirm.required", action=action, target=target)
                return OutboundMessage(
                    channel=ctx.msg.channel,
                    chat_id=ctx.msg.chat_id,
                    content=content,
                    metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
                )
            result = controller.run_action(action, target)
            lines = [
                "## Local LLM",
                "",
                result.get("message") or f"{action} {target} completed.",
            ]
            if result.get("requires_restart"):
                lines.extend([
                    "",
                    "Restart Nanobot to apply this to new runtime config.",
                    "Use `/restart` when ready.",
                ])
            content = "\n".join(lines)
    except LocalLlmError as exc:
        content = "\n".join(["## Local LLM", "", str(exc)])

    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_dream(ctx: CommandContext) -> OutboundMessage:
    """Manually trigger a Dream consolidation run."""
    import time

    loop = ctx.loop
    msg = ctx.msg

    async def _run_dream():
        async def _silent(*_args, **_kwargs):
            pass

        from nanobot.agent.memory import MemoryStore

        dream_session_key = MemoryStore.dream_session_key
        build_dream_commit_message = MemoryStore.build_dream_commit_message
        prune_dream_sessions = MemoryStore.prune_dream_sessions

        store = loop.context.memory
        content = ""
        resp = None
        t0 = time.monotonic()
        try:
            result = store.build_dream_prompt()
            if result is None:
                await loop.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content=_format_dream_no_input_message(),
                    metadata={"render_as": "text"},
                ))
                return
            prompt, last_cursor = result
            key = dream_session_key()
            resp = await loop.process_direct(
                prompt,
                session_key=key,
                ephemeral=True,
                tools=store.build_dream_tools(),
                on_progress=_silent,
            )
            elapsed = time.monotonic() - t0
            if MemoryStore.dream_run_completed(resp):
                store.set_last_dream_cursor(last_cursor)
                content = f"Dream completed in {elapsed:.1f}s."
            else:
                content = (
                    f"Dream did not complete after {elapsed:.1f}s; "
                    "memory cursor was not advanced."
                )
        except Exception as e:
            elapsed = time.monotonic() - t0
            content = f"Dream failed after {elapsed:.1f}s: {e}"
        finally:
            from nanobot.webui.token_usage import record_response_token_usage

            record_response_token_usage(
                resp,
                source="dream",
                timezone_name=getattr(loop.context, "timezone", None),
            )
            if store.git.is_initialized():
                commit_msg = build_dream_commit_message("dream: manual run", resp)
                sha = store.git.auto_commit(commit_msg)
                if sha:
                    content += f" (commit {sha})"
            store.compact_history()
            prune_dream_sessions(loop.sessions.sessions_dir)
        await loop.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=content,
        ))

    asyncio.create_task(_run_dream())
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content="Dreaming...",
    )


def _format_dream_no_input_message() -> str:
    return "\n".join([
        "Dream has no conversation history to process yet.",
        "",
        "Dream reads new entries from `memory/history.jsonl` after the current Dream cursor.",
        (
            "Short chats only reach that file after token compaction or idle auto-compact, "
            "so a fresh or short WebUI chat may leave Dream with no input."
        ),
        "",
        "Next steps:",
        "- Enable `agents.defaults.idleCompactAfterMinutes` so completed chats become Dream input automatically.",
        "- Compact the current chat into memory once that manual action is available.",
        "- If you expected history to exist, check whether `memory/history.jsonl` has new entries after the Dream cursor.",
    ])


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


_GOAL_PROMPT_TEMPLATE = """The user declared a sustained objective for this thread.

Inspect or clarify if needed, then call `long_task` with the refined objective (and optional short ui_summary). Work proceeds as normal assistant turns using your usual tools. When the objective is fully done and verified, call `complete_goal` with a brief recap. If the user later cancels or changes direction, still call `complete_goal` with an honest recap (then `long_task` again only after there is no active goal). Do not use `long_task` / `complete_goal` for trivial one-shot answers.

Goal:
{goal}
"""


async def cmd_goal(ctx: CommandContext) -> OutboundMessage | None:
    """Rewrite /goal into a normal agent turn that nudges long_task use."""
    goal = ctx.args.strip()
    if not goal:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Usage: /goal <long-running task description>",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )
    if ctx.session is None:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=(
                "A task is already running for this chat. "
                "Use `/stop` first, then send `/goal <long-running task description>` again."
            ),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    ctx.msg.metadata = {
        **dict(ctx.msg.metadata or {}),
        "original_command": "/goal",
        "original_content": ctx.raw,
        "goal_started_at": time.time(),
    }
    ctx.msg.content = _GOAL_PROMPT_TEMPLATE.format(goal=goal)
    return None


async def cmd_pairing(ctx: CommandContext) -> OutboundMessage:
    """List, approve, deny or revoke pairing requests."""
    from nanobot.pairing import PAIRING_COMMAND_META_KEY, handle_pairing_command

    reply = handle_pairing_command(ctx.msg.channel, ctx.args)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=reply,
        metadata={PAIRING_COMMAND_META_KEY: True},
    )


async def cmd_skill(ctx: CommandContext) -> OutboundMessage:
    """List all enabled skills (name and description only)."""
    loop = ctx.loop
    skills = loop.context.skills.list_skills(filter_unavailable=False)
    if not skills:
        content = "No skills available."
    else:
        lines = [f"Available skills ({len(skills)}):", ""]
        for entry in skills:
            desc = loop.context.skills._get_skill_description(entry["name"])
            lines.append(f"- **{entry['name']}** — {desc}")
        content = "\n".join(lines)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata=dict(ctx.msg.metadata or {}),
    )

async def cmd_help(ctx: CommandContext) -> OutboundMessage:
    """Return available slash commands."""
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=build_help_text(),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


def build_help_text() -> str:
    """Build canonical help text shared across channels."""
    lines = ["🐈 nanobot commands:"]
    for spec in BUILTIN_COMMAND_SPECS:
        command = spec.command
        if spec.arg_hint:
            command = f"{command} {spec.arg_hint}"
        lines.append(f"{command} — {spec.description}")
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
    router.exact("/status", cmd_status)
    router.exact("/model", cmd_model)
    router.prefix("/model ", cmd_model)
    router.exact("/local-llm", cmd_local_llm)
    router.prefix("/local-llm ", cmd_local_llm)
    router.exact("/usage", cmd_usage)
    router.prefix("/usage ", cmd_usage)
    router.exact("/history", cmd_history)
    router.prefix("/history ", cmd_history)
    router.exact("/goal", cmd_goal)
    router.prefix("/goal ", cmd_goal)
    router.exact("/dream", cmd_dream)
    router.exact("/dream-log", cmd_dream_log)
    router.prefix("/dream-log ", cmd_dream_log)
    router.exact("/dream-restore", cmd_dream_restore)
    router.prefix("/dream-restore ", cmd_dream_restore)
    router.exact("/skill", cmd_skill)
    router.exact("/help", cmd_help)
    router.exact("/pairing", cmd_pairing)
    router.prefix("/pairing ", cmd_pairing)
