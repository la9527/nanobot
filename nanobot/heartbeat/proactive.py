from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass(slots=True)
class HeartbeatProactivePolicy:
    webui_first: bool = True
    max_digest_items: int = 3
    quiet_hours_enabled: bool = False
    quiet_hours_start_local_time: str = "22:30"
    quiet_hours_end_local_time: str = "07:30"
    quiet_hours_timezone: str | None = None
    quiet_hours_allow_critical: bool = False
    quiet_hours_allowed_channels: tuple[str, ...] = ("websocket",)


@dataclass(slots=True)
class HeartbeatTargetDecision:
    channel: str
    chat_id: str
    timezone: str | None = None
    suppressed: bool = False
    reason: str | None = None


def build_proactive_context(
    sessions: list[dict[str, object]],
    *,
    max_digest_items: int = 3,
) -> str:
    waiting: list[str] = []
    blocked: list[str] = []
    calendar: list[str] = []
    mail: list[str] = []

    for item in sessions:
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            continue

        task = metadata.get("task_summary")
        if isinstance(task, dict):
            title = _clean_text(task.get("title")) or "Untitled task"
            next_step = _clean_text(task.get("next_step_hint"))
            line = f"{title}"
            if next_step:
                line = f"{line} - {next_step}"
            status = _clean_text(task.get("status"))
            if status == "waiting-approval":
                waiting.append(line)
            elif status == "blocked":
                blocked.append(line)

        action_result = metadata.get("action_result")
        if not isinstance(action_result, dict):
            continue

        if _clean_text(action_result.get("status")) != "completed":
            continue

        summary = _clean_text(action_result.get("summary"))
        if not summary:
            continue

        domain = _clean_text(action_result.get("domain"))
        action = _clean_text(action_result.get("action"))
        if domain == "calendar" and action == "list_events":
            calendar.append(summary)
        elif domain == "mail" and action in {"list_messages", "list_threads"}:
            mail.append(summary)

    lines: list[str] = []
    if waiting:
        lines.append(
            "- Waiting approvals: "
            + "; ".join(waiting[:max_digest_items])
        )
    if blocked:
        lines.append(
            "- Blocked tasks: "
            + "; ".join(blocked[:max_digest_items])
        )
    if calendar:
        lines.append(f"- Recent calendar summary: {calendar[0]}")
    if mail:
        lines.append(f"- Recent mail summary: {mail[0]}")

    if not lines:
        return ""

    return "Current proactive context:\n" + "\n".join(lines) + "\n\n"


def classify_proactive_task(tasks: str) -> str:
    normalized = tasks.strip().lower()
    if "morning briefing" in normalized or "briefing" in normalized:
        return "briefing"
    if "remind" in normalized or "reminder" in normalized:
        return "reminder"
    return "follow-up"


def proactive_title_for_task(tasks: str) -> str:
    category = classify_proactive_task(tasks)
    if category == "briefing":
        return "Morning briefing ready"
    if category == "reminder":
        return "Reminder ready"
    return "Follow-up digest ready"


def decide_heartbeat_target(
    sessions: list[dict[str, object]],
    enabled_channels: set[str],
    *,
    policy: HeartbeatProactivePolicy,
    default_channel: str = "cli",
    default_chat_id: str = "direct",
    severity: str = "normal",
    now: datetime | None = None,
    fallback_timezone: str | None = None,
) -> HeartbeatTargetDecision:
    candidates = [
        candidate
        for candidate in (_candidate_from_session(item) for item in sessions)
        if candidate is not None and candidate.channel in enabled_channels
    ]

    websocket = next((item for item in candidates if item.channel == "websocket"), None)
    external_candidates = [item for item in candidates if item.channel != "websocket"]

    if policy.webui_first and websocket is not None:
        push_candidate = external_candidates[0] if external_candidates else websocket
        quiet_hours_timezone = _resolve_quiet_hours_timezone(
            candidate=push_candidate,
            policy=policy,
            fallback_timezone=fallback_timezone,
        )
        if external_candidates and _is_quiet_hours(
            policy=policy,
            timezone=quiet_hours_timezone,
            severity=severity,
            now=now,
            channel=push_candidate.channel,
        ):
            return websocket
        if not external_candidates:
            return websocket

    candidate = external_candidates[0] if external_candidates else candidates[0] if candidates else HeartbeatTargetDecision(
        channel=default_channel,
        chat_id=default_chat_id,
    )

    quiet_hours_timezone = _resolve_quiet_hours_timezone(
        candidate=candidate,
        policy=policy,
        fallback_timezone=fallback_timezone,
    )
    if _is_quiet_hours(
        policy=policy,
        timezone=quiet_hours_timezone,
        severity=severity,
        now=now,
        channel=candidate.channel,
    ):
        return HeartbeatTargetDecision(
            channel=candidate.channel,
            chat_id=candidate.chat_id,
            suppressed=True,
            reason="quiet_hours",
        )
    return candidate


def _candidate_from_session(item: dict[str, object]) -> HeartbeatTargetDecision | None:
    key = item.get("key")
    if not isinstance(key, str) or ":" not in key:
        return None
    channel, chat_id = key.split(":", 1)
    if channel in {"cli", "system"} or not chat_id:
        return None

    timezone = None
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        owner_profile = metadata.get("owner_profile")
        if isinstance(owner_profile, dict):
            timezone = _clean_text(owner_profile.get("timezone"))

    return HeartbeatTargetDecision(channel=channel, chat_id=chat_id, timezone=timezone)


def _resolve_quiet_hours_timezone(
    *,
    candidate: HeartbeatTargetDecision,
    policy: HeartbeatProactivePolicy,
    fallback_timezone: str | None,
) -> str | None:
    if policy.quiet_hours_timezone:
        return policy.quiet_hours_timezone
    timezone = getattr(candidate, "timezone", None)
    if isinstance(timezone, str) and timezone.strip():
        return timezone.strip()
    return fallback_timezone


def _is_quiet_hours(
    *,
    policy: HeartbeatProactivePolicy,
    timezone: str | None,
    severity: str,
    now: datetime | None,
    channel: str,
) -> bool:
    if not policy.quiet_hours_enabled:
        return False
    if channel in policy.quiet_hours_allowed_channels:
        return False
    if severity == "critical" and policy.quiet_hours_allow_critical:
        return False

    zone_name = timezone or "UTC"
    current = now.astimezone(ZoneInfo(zone_name)) if now else datetime.now(ZoneInfo(zone_name))
    current_minutes = current.hour * 60 + current.minute
    start_minutes = _parse_local_minutes(policy.quiet_hours_start_local_time)
    end_minutes = _parse_local_minutes(policy.quiet_hours_end_local_time)

    if start_minutes == end_minutes:
        return False
    if start_minutes < end_minutes:
        return start_minutes <= current_minutes < end_minutes
    return current_minutes >= start_minutes or current_minutes < end_minutes


def _parse_local_minutes(value: str) -> int:
    raw = value.strip()
    hour_text, _, minute_text = raw.partition(":")
    hour = int(hour_text)
    minute = int(minute_text or "0")
    return hour * 60 + minute


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None