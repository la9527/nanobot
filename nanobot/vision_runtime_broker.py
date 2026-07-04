from __future__ import annotations

import asyncio
import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nanobot.local_llm_control import DEFAULT_SCRIPT_PATH, LOCAL_LLM_TARGETS, _endpoint_ok

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


@dataclass
class LeaseRecord:
    acquired_at: float
    last_used_at: float
    expires_at: float


@dataclass
class BrokerEventRecord:
    event: str
    holder: str | None
    timestamp: float


@dataclass
class BrokerTargetState:
    target: str
    model: str
    api_base: str
    running: bool = False
    last_used_at: float | None = None
    idle_deadline_at: float | None = None
    idle_timeout_seconds: float = 300.0
    holders: dict[str, LeaseRecord] = field(default_factory=dict)
    recent_events: list[BrokerEventRecord] = field(default_factory=list)


class VisionRuntimeBroker:
    def __init__(
        self,
        *,
        state_root: str | Path,
        script_path: str | Path = DEFAULT_SCRIPT_PATH,
        runner: Runner | None = None,
        endpoint_ok: Callable[[str], bool] | None = None,
        monotonic: Callable[[], float] | None = None,
        sleep: Callable[[float], object] | None = None,
        idle_timeout_seconds: float = 300.0,
        lease_ttl_seconds: float = 30.0,
        trace_capacity: int = 16,
    ) -> None:
        self.state_root = Path(state_root)
        self.script_path = str(script_path)
        self.runner = runner or _default_runner
        self.endpoint_ok = endpoint_ok or _endpoint_ok
        self.monotonic = monotonic or time.monotonic
        self.sleep = sleep or asyncio.sleep
        self.idle_timeout_seconds = float(idle_timeout_seconds)
        self.lease_ttl_seconds = float(lease_ttl_seconds)
        self.trace_capacity = max(1, int(trace_capacity))
        self._locks: dict[str, asyncio.Lock] = {}
        self._stop_tasks: dict[str, asyncio.Task[None]] = {}
        self.state_root.mkdir(parents=True, exist_ok=True)

    async def acquire(self, target: str, holder: str) -> dict[str, Any]:
        async with self._lock_for(target):
            state = self._load_state(target)
            self._cancel_stop(target)
            if not await asyncio.to_thread(self.endpoint_ok, state.api_base):
                await self._run_script("start", target)
                state.running = True
            else:
                state.running = True
            now = self.monotonic()
            state.holders[holder] = LeaseRecord(
                acquired_at=now,
                last_used_at=now,
                expires_at=now + self.lease_ttl_seconds,
            )
            state.last_used_at = now
            state.idle_deadline_at = None
            self._append_event(state, "acquire", holder, now)
            self._save_state(state)
            return self._snapshot_for(state)

    async def release(self, target: str, holder: str) -> dict[str, Any]:
        async with self._lock_for(target):
            state = self._load_state(target)
            state.holders.pop(holder, None)
            state.last_used_at = self.monotonic()
            self._append_event(state, "release", holder, state.last_used_at)
            state.idle_deadline_at = (
                state.last_used_at + state.idle_timeout_seconds
                if not state.holders and state.last_used_at is not None
                else None
            )
            self._save_state(state)
            if not state.holders:
                self._schedule_stop(target)
            return self._snapshot_for(state)

    async def mark_used(self, target: str, holder: str) -> dict[str, Any]:
        async with self._lock_for(target):
            state = self._load_state(target)
            lease = state.holders.get(holder)
            now = self.monotonic()
            if lease is not None:
                lease.last_used_at = now
                lease.expires_at = now + self.lease_ttl_seconds
            state.last_used_at = now
            state.idle_deadline_at = None
            self._append_event(state, "mark_used", holder, now)
            self._save_state(state)
            return self._snapshot_for(state)

    async def reconcile(self, target: str) -> dict[str, Any]:
        async with self._lock_for(target):
            state = self._load_state(target)
            now = self.monotonic()
            state.holders = {
                holder: lease
                for holder, lease in state.holders.items()
                if lease.expires_at > now
            }
            self._save_state(state)
            return self._snapshot_for(state)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        payload: dict[str, dict[str, Any]] = {}
        for state_path in sorted(self.state_root.glob("*.json")):
            target = state_path.stem
            payload[target] = self._snapshot_for(self._load_state(target))
        return payload

    def _lock_for(self, target: str) -> asyncio.Lock:
        return self._locks.setdefault(target, asyncio.Lock())

    def _state_path(self, target: str) -> Path:
        return self.state_root / f"{target}.json"

    def _load_state(self, target: str) -> BrokerTargetState:
        meta = LOCAL_LLM_TARGETS[target]
        path = self._state_path(target)
        if not path.exists():
            return BrokerTargetState(
                target=target,
                model=meta["model"],
                api_base=meta["api_base"],
                idle_timeout_seconds=self.idle_timeout_seconds,
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        holders = {
            holder: LeaseRecord(**lease_payload)
            for holder, lease_payload in payload.get("holders", {}).items()
        }
        recent_events = [
            BrokerEventRecord(**event_payload)
            for event_payload in payload.get("recent_events", [])
            if isinstance(event_payload, dict)
        ]
        return BrokerTargetState(
            target=payload.get("target", target),
            model=payload.get("model", meta["model"]),
            api_base=payload.get("api_base", meta["api_base"]),
            running=bool(payload.get("running", False)),
            last_used_at=payload.get("last_used_at"),
            idle_deadline_at=payload.get("idle_deadline_at"),
            idle_timeout_seconds=float(payload.get("idle_timeout_seconds", self.idle_timeout_seconds)),
            holders=holders,
            recent_events=recent_events,
        )

    def _save_state(self, state: BrokerTargetState) -> None:
        payload = self._snapshot_for(state)
        payload["api_base"] = state.api_base
        self._state_path(state.target).write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _snapshot_for(self, state: BrokerTargetState) -> dict[str, Any]:
        stop_task = self._stop_tasks.get(state.target)
        stop_scheduled = bool(stop_task is not None and not stop_task.done()) or (
            state.idle_deadline_at is not None and state.running and not state.holders
        )
        return {
            "target": state.target,
            "model": state.model,
            "running": state.running,
            "last_used_at": state.last_used_at,
            "idle_deadline_at": state.idle_deadline_at,
            "idle_timeout_seconds": state.idle_timeout_seconds,
            "holder_count": len(state.holders),
            "holders": {
                holder: asdict(lease)
                for holder, lease in sorted(state.holders.items())
            },
            "recent_events": [asdict(event) for event in state.recent_events],
            "stop_scheduled": stop_scheduled,
        }

    def _append_event(
        self,
        state: BrokerTargetState,
        event: str,
        holder: str | None,
        timestamp: float | None = None,
    ) -> None:
        state.recent_events.append(
            BrokerEventRecord(
                event=event,
                holder=holder,
                timestamp=self.monotonic() if timestamp is None else timestamp,
            )
        )
        if len(state.recent_events) > self.trace_capacity:
            state.recent_events = state.recent_events[-self.trace_capacity :]

    async def _run_script(self, action: str, target: str) -> None:
        result = await asyncio.to_thread(self.runner, [self.script_path, action, target])
        if result.returncode != 0:
            message = (result.stderr or result.stdout or f"{action} failed").strip()
            raise RuntimeError(message)

    def _cancel_stop(self, target: str) -> None:
        task = self._stop_tasks.get(target)
        if task is not None and not task.done():
            task.cancel()

    def _schedule_stop(self, target: str) -> None:
        self._cancel_stop(target)
        self._stop_tasks[target] = asyncio.create_task(self._stop_after_idle(target))

    async def _stop_after_idle(self, target: str) -> None:
        try:
            await self.sleep(self.idle_timeout_seconds)
            async with self._lock_for(target):
                state = self._load_state(target)
                if state.holders:
                    return
                if await asyncio.to_thread(self.endpoint_ok, state.api_base):
                    await self._run_script("stop", target)
                state.running = False
                state.idle_deadline_at = None
                self._save_state(state)
        finally:
            current = self._stop_tasks.get(target)
            if current is asyncio.current_task():
                self._stop_tasks.pop(target, None)


def _default_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
    )