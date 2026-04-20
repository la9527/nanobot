from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

TierName = Literal["local", "mini", "full"]


@dataclass(slots=True)
class TierTarget:
    tier: TierName
    provider: str | None
    model: str


@dataclass(slots=True)
class RequestFeatures:
    prompt_chars: int
    message_count: int
    tool_count: int
    tool_history_count: int
    attachment_count: int
    has_code_block: bool
    code_keyword_hits: list[str] = field(default_factory=list)
    tool_keyword_hits: list[str] = field(default_factory=list)
    full_keyword_hits: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RouteDecision:
    requested_tier: TierName
    score: int
    reason_codes: list[str]
    features: RequestFeatures


@dataclass(slots=True)
class AttemptRecord:
    tier: TierName
    model: str
    provider: str | None
    status: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)