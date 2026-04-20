from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .types import TierTarget


@dataclass(slots=True)
class PolicySettings:
    local_score_max: int
    full_score_min: int
    short_prompt_chars: int
    medium_prompt_chars: int
    long_prompt_chars: int
    tool_bonus: int
    code_bonus: int
    reasoning_bonus: int
    history_bonus: int
    attachment_bonus: int
    full_keywords: list[str]
    code_keywords: list[str]
    tool_keywords: list[str]


@dataclass(slots=True)
class HealthSettings:
    failure_threshold: int
    cooldown_seconds: int


@dataclass(slots=True)
class LoggingSettings:
    enabled: bool
    path: str


@dataclass(slots=True)
class RouterConfig:
    enabled: bool
    allow_local_tools: bool
    local: TierTarget
    mini: TierTarget
    full: TierTarget
    policy: PolicySettings
    health: HealthSettings
    logging: LoggingSettings


def _tier_target(
    tier: str,
    value: Any,
    *,
    default_model: str | None = None,
    default_provider: str | None = None,
) -> TierTarget:
    model = getattr(value, "model", None) or default_model
    provider = getattr(value, "provider", None) or default_provider
    if not model:
        raise ValueError(f"smart_router.{tier}.model is required")
    return TierTarget(tier=tier, provider=provider, model=model)


def load_router_config(
    value: Any,
    *,
    default_model: str,
    default_provider: str | None,
) -> RouterConfig:
    local = _tier_target(
        "local",
        getattr(value, "local", None),
        default_model=default_model,
        default_provider=default_provider,
    )
    mini = _tier_target("mini", getattr(value, "mini", None))
    full = _tier_target("full", getattr(value, "full", None))
    policy_value = getattr(value, "policy")
    health_value = getattr(value, "health")
    logging_value = getattr(value, "logging")
    return RouterConfig(
        enabled=bool(getattr(value, "enabled", False)),
        allow_local_tools=bool(getattr(value, "allow_local_tools", False)),
        local=local,
        mini=mini,
        full=full,
        policy=PolicySettings(
            local_score_max=policy_value.local_score_max,
            full_score_min=policy_value.full_score_min,
            short_prompt_chars=policy_value.short_prompt_chars,
            medium_prompt_chars=policy_value.medium_prompt_chars,
            long_prompt_chars=policy_value.long_prompt_chars,
            tool_bonus=policy_value.tool_bonus,
            code_bonus=policy_value.code_bonus,
            reasoning_bonus=policy_value.reasoning_bonus,
            history_bonus=policy_value.history_bonus,
            attachment_bonus=policy_value.attachment_bonus,
            full_keywords=list(policy_value.full_keywords),
            code_keywords=list(policy_value.code_keywords),
            tool_keywords=list(policy_value.tool_keywords),
        ),
        health=HealthSettings(
            failure_threshold=health_value.failure_threshold,
            cooldown_seconds=health_value.cooldown_seconds,
        ),
        logging=LoggingSettings(
            enabled=bool(logging_value.enabled),
            path=logging_value.path,
        ),
    )