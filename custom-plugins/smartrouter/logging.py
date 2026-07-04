from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import LoggingSettings
from .types import AttemptRecord, RouteDecision, TierName


class SmartRouterLogger:
    def __init__(self, settings: LoggingSettings):
        self._enabled = settings.enabled
        self._path = Path(settings.path).expanduser()

    def log(
        self,
        *,
        decision: RouteDecision,
        final_tier: TierName | None,
        request_model: str | None,
        attempts: list[AttemptRecord],
    ) -> None:
        if not self._enabled:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "requestModel": request_model,
            "requestedTier": decision.requested_tier,
            "finalTier": final_tier,
            "score": decision.score,
            "reasonCodes": decision.reason_codes,
            "features": decision.features.to_dict(),
            "attempts": [attempt.to_dict() for attempt in attempts],
        }
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")