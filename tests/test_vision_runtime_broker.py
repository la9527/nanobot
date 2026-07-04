from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from nanobot.vision_runtime_broker import VisionRuntimeBroker


@pytest.mark.asyncio
async def test_acquire_starts_runtime_once_tracks_two_holders_and_persists_state(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []
    running = {"value": False}
    now = {"value": 100.0}

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv[1] == "start":
            running["value"] = True
        return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    broker = VisionRuntimeBroker(
        state_root=tmp_path,
        script_path="/tmp/local-models.sh",
        runner=runner,
        endpoint_ok=lambda _api_base: running["value"],
        monotonic=lambda: now["value"],
        sleep=lambda _seconds: asyncio.sleep(0),
        idle_timeout_seconds=30.0,
        lease_ttl_seconds=15.0,
    )

    snapshot_a = await broker.acquire("qwen3-vl-4b", "smart-router-local")
    snapshot_b = await broker.acquire("qwen3-vl-4b", "photo-ranker:pid-42")
    persisted = json.loads((tmp_path / "qwen3-vl-4b.json").read_text(encoding="utf-8"))
    restored_snapshot = VisionRuntimeBroker(
        state_root=tmp_path,
        script_path="/tmp/local-models.sh",
    ).snapshot()["qwen3-vl-4b"]

    assert calls == [["/tmp/local-models.sh", "start", "qwen3-vl-4b"]]
    assert snapshot_a["running"] is True
    assert sorted(snapshot_b["holders"].keys()) == ["photo-ranker:pid-42", "smart-router-local"]
    assert persisted["holder_count"] == 2
    assert restored_snapshot["holder_count"] == 2
    assert restored_snapshot["model"] == "mlx-community/Qwen3-VL-4B-Instruct-4bit"


@pytest.mark.asyncio
async def test_mark_used_refreshes_existing_holder_lease(tmp_path: Path) -> None:
    now = {"value": 300.0}
    broker = VisionRuntimeBroker(
        state_root=tmp_path,
        script_path="/tmp/local-models.sh",
        endpoint_ok=lambda _api_base: True,
        monotonic=lambda: now["value"],
        sleep=lambda _seconds: asyncio.sleep(0),
        lease_ttl_seconds=15.0,
    )

    await broker.acquire("qwen3-vl-4b", "photo-ranker:pid-9")
    before = json.loads((tmp_path / "qwen3-vl-4b.json").read_text(encoding="utf-8"))
    now["value"] += 5.0

    snapshot = await broker.mark_used("qwen3-vl-4b", "photo-ranker:pid-9")
    after = json.loads((tmp_path / "qwen3-vl-4b.json").read_text(encoding="utf-8"))

    assert snapshot["holders"]["photo-ranker:pid-9"]["last_used_at"] == 305.0
    assert after["holders"]["photo-ranker:pid-9"]["expires_at"] > before["holders"]["photo-ranker:pid-9"]["expires_at"]


@pytest.mark.asyncio
async def test_release_only_stops_after_last_holder_and_idle_timeout(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    running = {"value": True}
    now = {"value": 200.0}

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv[1] == "stop":
            running["value"] = False
        return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    async def fake_sleep(seconds: float) -> None:
        now["value"] += seconds
        await asyncio.sleep(0)

    broker = VisionRuntimeBroker(
        state_root=tmp_path,
        script_path="/tmp/local-models.sh",
        runner=runner,
        endpoint_ok=lambda _api_base: running["value"],
        monotonic=lambda: now["value"],
        sleep=fake_sleep,
        idle_timeout_seconds=10.0,
        lease_ttl_seconds=15.0,
    )

    await broker.acquire("qwen3-vl-4b", "smart-router-local")
    await broker.acquire("qwen3-vl-4b", "photo-ranker:pid-42")
    await broker.release("qwen3-vl-4b", "smart-router-local")

    assert calls == []

    snapshot = await broker.release("qwen3-vl-4b", "photo-ranker:pid-42")
    await broker._stop_tasks["qwen3-vl-4b"]

    assert snapshot["holder_count"] == 0
    assert calls == [["/tmp/local-models.sh", "stop", "qwen3-vl-4b"]]


@pytest.mark.asyncio
async def test_reconcile_removes_expired_holders(tmp_path: Path) -> None:
    now = {"value": 400.0}
    broker = VisionRuntimeBroker(
        state_root=tmp_path,
        script_path="/tmp/local-models.sh",
        endpoint_ok=lambda _api_base: True,
        monotonic=lambda: now["value"],
        sleep=lambda _seconds: asyncio.sleep(0),
        lease_ttl_seconds=15.0,
    )

    await broker.acquire("qwen3-vl-4b", "photo-ranker:pid-9")
    now["value"] += 120.0

    snapshot = await broker.reconcile("qwen3-vl-4b")
    persisted = json.loads((tmp_path / "qwen3-vl-4b.json").read_text(encoding="utf-8"))

    assert snapshot["holders"] == {}
    assert snapshot["holder_count"] == 0
    assert persisted["holders"] == {}


@pytest.mark.asyncio
async def test_snapshot_includes_recent_holder_events_for_overlap_debugging(
    tmp_path: Path,
) -> None:
    now = {"value": 500.0}
    broker = VisionRuntimeBroker(
        state_root=tmp_path,
        script_path="/tmp/local-models.sh",
        endpoint_ok=lambda _api_base: True,
        monotonic=lambda: now["value"],
        sleep=lambda _seconds: asyncio.sleep(0),
        lease_ttl_seconds=15.0,
    )

    await broker.acquire("qwen3-vl-4b", "smart-router-local")
    now["value"] += 1.0
    await broker.acquire("qwen3-vl-4b", "photo-ranker:pid-42")
    now["value"] += 1.0
    snapshot = await broker.release("qwen3-vl-4b", "smart-router-local")

    assert [event["event"] for event in snapshot["recent_events"]] == [
        "acquire",
        "acquire",
        "release",
    ]
    assert [event["holder"] for event in snapshot["recent_events"]] == [
        "smart-router-local",
        "photo-ranker:pid-42",
        "smart-router-local",
    ]
    assert snapshot["recent_events"][-1]["timestamp"] == 502.0


@pytest.mark.asyncio
async def test_release_persists_idle_deadline_for_cross_process_observers(tmp_path: Path) -> None:
    running = {"value": True}
    now = {"value": 600.0}

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        if argv[1] == "stop":
            running["value"] = False
        return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    async def fake_sleep(seconds: float) -> None:
        now["value"] += seconds
        await asyncio.sleep(0)

    broker = VisionRuntimeBroker(
        state_root=tmp_path,
        script_path="/tmp/local-models.sh",
        runner=runner,
        endpoint_ok=lambda _api_base: running["value"],
        monotonic=lambda: now["value"],
        sleep=fake_sleep,
        idle_timeout_seconds=10.0,
        lease_ttl_seconds=15.0,
    )

    await broker.acquire("qwen3-vl-4b", "smart-router-local")
    released = await broker.release("qwen3-vl-4b", "smart-router-local")
    restored = VisionRuntimeBroker(
        state_root=tmp_path,
        script_path="/tmp/local-models.sh",
    ).snapshot()["qwen3-vl-4b"]

    assert released["stop_scheduled"] is True
    assert released["idle_deadline_at"] == 610.0
    assert restored["stop_scheduled"] is True
    assert restored["idle_deadline_at"] == 610.0