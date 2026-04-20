from __future__ import annotations

import time
from dataclasses import dataclass

from .config import HealthSettings
from .types import TierName


@dataclass(slots=True)
class TierHealthState:
    consecutive_failures: int = 0
    cooldown_until: float = 0.0


class TierHealthTracker:
    def __init__(self, settings: HealthSettings):
        self._settings = settings
        self._state = {
            "local": TierHealthState(),
            "mini": TierHealthState(),
            "full": TierHealthState(),
        }

    def is_available(self, tier: TierName) -> bool:
        return self._state[tier].cooldown_until <= time.monotonic()

    def record_success(self, tier: TierName) -> None:
        self._state[tier] = TierHealthState()

    def record_failure(self, tier: TierName) -> None:
        state = self._state[tier]
        state.consecutive_failures += 1
        if state.consecutive_failures >= self._settings.failure_threshold:
            state.cooldown_until = time.monotonic() + self._settings.cooldown_seconds