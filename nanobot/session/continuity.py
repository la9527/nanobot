"""Minimal single-user continuity metadata helpers.

This phase intentionally keeps continuity lightweight: a stable canonical
owner plus per-session channel identity hints that can be reused by WebUI,
approval visibility, and later domain integrations.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from nanobot.session.memory_correction_nlp import memory_correction_actions

PRIMARY_OWNER_ID = "primary-user"
CONTINUITY_METADATA_KEY = "continuity"
TASK_SUMMARY_METADATA_KEY = "task_summary"
OWNER_PROFILE_METADATA_KEY = "owner_profile"
MEMORY_BOUNDARY_METADATA_KEY = "memory_boundary"
MEMORY_CORRECTION_METADATA_KEY = "memory_correction"
ACTION_RESULT_METADATA_KEY = "action_result"

_PLACEHOLDER_VALUE_RE = re.compile(r"^\([^)]*\)$")


def _channel_kind(session_key: str) -> str:
    prefix, _, _rest = session_key.partition(":")
    return prefix or "unknown"


def _external_identity(session_key: str) -> str:
    channel, _, remainder = session_key.partition(":")
    if channel == "websocket":
        return "local-webui"
    if not remainder:
        return session_key
    return remainder.split(":thread:", 1)[0].split(":topic:", 1)[0]


def _default_trust_level(channel_kind: str) -> str:
    if channel_kind == "websocket":
        return "trusted"
    return "linked"


def _clean_profile_value(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or _PLACEHOLDER_VALUE_RE.fullmatch(cleaned):
        return None
    return cleaned


def _extract_user_field(user_profile_source: str | None, field_name: str) -> str | None:
    if not user_profile_source:
        return None
    match = re.search(
        rf"^-\s+\*\*{re.escape(field_name)}\*\*:\s*(.+)$",
        user_profile_source,
        re.MULTILINE,
    )
    if not match:
        return None
    return _clean_profile_value(match.group(1))


def _extract_checked_user_option(
    user_profile_source: str | None,
    heading: str,
    mapping: dict[str, str],
) -> str | None:
    if not user_profile_source:
        return None

    heading_match = re.search(
        rf"^###\s+{re.escape(heading)}\s*$",
        user_profile_source,
        re.MULTILINE,
    )
    if not heading_match:
        return None

    remainder = user_profile_source[heading_match.end():]
    next_heading = re.search(r"^##?#?\s+", remainder, re.MULTILINE)
    section = remainder[: next_heading.start()] if next_heading else remainder
    for label, mapped_value in mapping.items():
        if re.search(rf"^-\s+\[[xX]\]\s+{re.escape(label)}\s*$", section, re.MULTILINE):
            return mapped_value
    return None


def _normalized_owner_profile(
    base: dict[str, Any],
    *,
    canonical_owner_id: str,
    user_profile_source: str | None,
) -> dict[str, Any]:
    existing = base.get(OWNER_PROFILE_METADATA_KEY)
    profile = dict(existing) if isinstance(existing, dict) else {}

    def _pick(name: str, fallback: str) -> str:
        value = profile.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return fallback

    parsed_language = _extract_user_field(user_profile_source, "Language")
    parsed_timezone = _extract_user_field(user_profile_source, "Timezone")
    parsed_tone = _extract_checked_user_option(
        user_profile_source,
        "Communication Style",
        {
            "Casual": "casual",
            "Professional": "professional",
            "Technical": "technical",
        },
    )
    parsed_length = _extract_checked_user_option(
        user_profile_source,
        "Response Length",
        {
            "Brief and concise": "brief",
            "Detailed explanations": "detailed",
            "Adaptive based on question": "balanced",
        },
    )

    return {
        "canonical_owner_id": canonical_owner_id,
        "preferred_language": _pick("preferred_language", parsed_language or "ko-KR"),
        "timezone": _pick("timezone", parsed_timezone or "UTC"),
        "response_tone": _pick("response_tone", parsed_tone or "direct"),
        "response_length": _pick("response_length", parsed_length or "balanced"),
    }


def _normalized_memory_boundary() -> dict[str, str]:
    return {
        "owner_profile": "USER.md",
        "project_memory": "memory/MEMORY.md",
        "session_state": "session.metadata",
        "raw_history": "memory/history.jsonl",
    }


def _normalized_memory_correction() -> dict[str, Any]:
    return {"actions": memory_correction_actions("ko-KR")}


def _task_title_from_metadata(base: dict[str, Any], channel_kind: str) -> str:
    action_result = base.get(ACTION_RESULT_METADATA_KEY)
    if isinstance(action_result, dict):
        title = action_result.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()

    approval = base.get("approval_summary")
    if isinstance(approval, dict):
        preview = approval.get("prompt_preview")
        if isinstance(preview, str) and preview.strip():
            return preview.strip()

    checkpoint = base.get("runtime_checkpoint")
    if isinstance(checkpoint, dict):
        phase = checkpoint.get("phase")
        if isinstance(phase, str) and phase.strip():
            return f"Resume {phase.strip().replace('_', ' ')}"

    existing = base.get(TASK_SUMMARY_METADATA_KEY)
    if isinstance(existing, dict):
        title = existing.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()

    return f"{channel_kind} session follow-up"


def _normalized_task_summary(
    session_key: str,
    base: dict[str, Any],
    *,
    canonical_owner_id: str,
    channel_kind: str,
    updated_at: str | None,
) -> dict[str, Any]:
    existing = base.get(TASK_SUMMARY_METADATA_KEY)
    task = dict(existing) if isinstance(existing, dict) else {}
    approval = base.get("approval_summary")
    action_result = base.get(ACTION_RESULT_METADATA_KEY)
    action_status = action_result.get("status") if isinstance(action_result, dict) else None
    action_next_step = action_result.get("next_step") if isinstance(action_result, dict) else None
    has_pending_approval = (
        isinstance(approval, dict) and approval.get("status") == "pending"
    )
    has_pending_user_turn = bool(base.get("pending_user_turn"))
    checkpoint = base.get("runtime_checkpoint")
    checkpoint_phase = checkpoint.get("phase") if isinstance(checkpoint, dict) else None

    if has_pending_approval:
        status = "waiting-approval"
        next_step_hint = "Review the pending approval request."
    elif isinstance(action_status, str) and action_status.strip() == "running":
        status = "running"
        next_step_hint = (
            action_next_step.strip()
            if isinstance(action_next_step, str) and action_next_step.strip()
            else "Wait for the current automation task to finish."
        )
    elif isinstance(action_status, str) and action_status.strip() == "waiting_approval":
        status = "waiting-approval"
        next_step_hint = (
            action_next_step.strip()
            if isinstance(action_next_step, str) and action_next_step.strip()
            else "Review the pending approval request."
        )
    elif isinstance(action_status, str) and action_status.strip() in {"failed", "blocked"}:
        status = "blocked"
        next_step_hint = (
            action_next_step.strip()
            if isinstance(action_next_step, str) and action_next_step.strip()
            else "Review the latest failure and retry when ready."
        )
    elif isinstance(action_status, str) and action_status.strip() == "rejected":
        status = "completed"
        next_step_hint = (
            action_next_step.strip()
            if isinstance(action_next_step, str) and action_next_step.strip()
            else "The request was cancelled; no follow-up is needed unless you start it again."
        )
    elif isinstance(action_status, str) and action_status.strip() == "completed":
        status = "completed"
        next_step_hint = (
            action_next_step.strip()
            if isinstance(action_next_step, str) and action_next_step.strip()
            else "Review the latest completed update if follow-up is needed."
        )
    elif has_pending_user_turn or isinstance(checkpoint_phase, str):
        status = "blocked"
        next_step_hint = "Reopen the interrupted session and continue the task."
    else:
        status = "completed"
        next_step_hint = "Review the latest completed update if follow-up is needed."

    task_id = task.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        task_id = f"session:{session_key}"

    title = _task_title_from_metadata(base, channel_kind)

    return {
        "task_id": task_id,
        "canonical_owner_id": canonical_owner_id,
        "title": title,
        "status": status,
        "origin_channel": task.get("origin_channel") if isinstance(task.get("origin_channel"), str) and task.get("origin_channel").strip() else channel_kind,
        "origin_session_key": task.get("origin_session_key") if isinstance(task.get("origin_session_key"), str) and task.get("origin_session_key").strip() else session_key,
        "updated_at": task.get("updated_at") if isinstance(task.get("updated_at"), str) and task.get("updated_at").strip() else updated_at,
        "next_step_hint": next_step_hint,
    }


def normalized_session_metadata(
    session_key: str,
    metadata: dict[str, Any] | None,
    *,
    last_confirmed_at: str | None,
    user_profile_source: str | None = None,
) -> dict[str, Any]:
    """Return a metadata dict with the minimum continuity block present.

    Existing continuity fields win when already present so future explicit
    linking or higher-trust flows can override these defaults without fighting
    the normalizer.
    """
    base = deepcopy(metadata) if isinstance(metadata, dict) else {}
    continuity = base.get(CONTINUITY_METADATA_KEY)
    continuity_dict = dict(continuity) if isinstance(continuity, dict) else {}

    channel_kind = continuity_dict.get("channel_kind")
    if not isinstance(channel_kind, str) or not channel_kind.strip():
        channel_kind = _channel_kind(session_key)

    external_identity = continuity_dict.get("external_identity")
    if not isinstance(external_identity, str) or not external_identity.strip():
        external_identity = _external_identity(session_key)

    canonical_owner_id = continuity_dict.get("canonical_owner_id")
    if not isinstance(canonical_owner_id, str) or not canonical_owner_id.strip():
        canonical_owner_id = PRIMARY_OWNER_ID

    trust_level = continuity_dict.get("trust_level")
    if not isinstance(trust_level, str) or not trust_level.strip():
        trust_level = _default_trust_level(channel_kind)

    confirmed = continuity_dict.get("last_confirmed_at")
    if not isinstance(confirmed, str) or not confirmed.strip():
        confirmed = last_confirmed_at

    base[CONTINUITY_METADATA_KEY] = {
        "canonical_owner_id": canonical_owner_id,
        "channel_kind": channel_kind,
        "external_identity": external_identity,
        "trust_level": trust_level,
        "last_confirmed_at": confirmed,
    }
    base[OWNER_PROFILE_METADATA_KEY] = _normalized_owner_profile(
        base,
        canonical_owner_id=canonical_owner_id,
        user_profile_source=user_profile_source,
    )
    base[MEMORY_BOUNDARY_METADATA_KEY] = _normalized_memory_boundary()
    base[MEMORY_CORRECTION_METADATA_KEY] = _normalized_memory_correction()
    base[TASK_SUMMARY_METADATA_KEY] = _normalized_task_summary(
        session_key,
        base,
        canonical_owner_id=canonical_owner_id,
        channel_kind=channel_kind,
        updated_at=confirmed,
    )
    return base
