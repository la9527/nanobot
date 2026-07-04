from __future__ import annotations

from .types import TierName


def build_fallback_chain(tier: TierName) -> list[TierName]:
    if tier == "local":
        return ["local", "mini", "full"]
    if tier == "mini":
        return ["mini", "full"]
    return ["full"]