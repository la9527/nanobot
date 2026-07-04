from __future__ import annotations

from typing import Any, Mapping


DEFAULT_RESPONSE_FOOTER_MODE = "off"
RESPONSE_FOOTER_MODES = ("off", "tokens", "full")
SESSION_RESPONSE_FOOTER_MODE_KEY = "response_footer_mode"


def normalize_response_footer_mode(value: Any) -> str:
    mode = str(value or DEFAULT_RESPONSE_FOOTER_MODE).strip().lower()
    if mode not in RESPONSE_FOOTER_MODES:
        return DEFAULT_RESPONSE_FOOTER_MODE
    return mode


def normalize_usage_snapshot(usage: Mapping[str, Any] | None) -> dict[str, int]:
    snapshot = usage or {}
    prompt_tokens = int(snapshot.get("prompt_tokens", 0) or 0)
    completion_tokens = int(snapshot.get("completion_tokens", 0) or 0)
    total_tokens = int(snapshot.get("total_tokens", 0) or 0)
    cached_tokens = int(snapshot.get("cached_tokens", 0) or 0)

    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens

    normalized = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
    if cached_tokens > 0:
        normalized["cached_tokens"] = cached_tokens
    return normalized


def _compact_token_count(value: int) -> str:
    if value >= 1000:
        return f"{value // 1000}k"
    return str(value)


def build_response_footer(
    *,
    mode: str,
    model: str,
    active_target: str | None,
    usage: Mapping[str, Any] | None,
    context_window_tokens: int,
    context_tokens_estimate: int | None = None,
    route_tier: str | None = None,
    route_model: str | None = None,
) -> str:
    normalized_mode = normalize_response_footer_mode(mode)
    if normalized_mode == DEFAULT_RESPONSE_FOOTER_MODE:
        return ""

    normalized_usage = normalize_usage_snapshot(usage)
    segments = [f"model={model}"]
    if active_target and active_target != model and normalized_mode == "full":
        segments.append(f"target={active_target}")

    if active_target in {"smart-router", "smart_router"} and route_tier:
        route_segment = f"route={route_tier}"
        if normalized_mode == "full" and route_model:
            route_segment = f"{route_segment}({route_model})"
        segments.append(route_segment)

    segments.append(
        "tokens="
        f"🔵{normalized_usage['prompt_tokens']} in/🟢{normalized_usage['completion_tokens']} out"
    )

    if normalized_mode == "full":
        segments.append(f"total=🟠{normalized_usage['total_tokens']}")
        cached_tokens = normalized_usage.get("cached_tokens", 0)
        if cached_tokens > 0:
            segments.append(f"cached=🟣{cached_tokens}")
        if context_tokens_estimate is not None and context_window_tokens > 0:
            segments.append(
                "context="
                f"🟡{_compact_token_count(max(context_tokens_estimate, 0))}"
                f"/⚪{_compact_token_count(max(context_window_tokens, 0))}"
            )

    return "\n\nStatus: " + " | ".join(segments)