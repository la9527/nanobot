"""Tests for metadata passed from bound cron jobs into the agent loop."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from nanobot.bus.events import OutboundMessage
from nanobot.cron.bound_runner import run_bound_cron_job
from nanobot.cron.session_turns import CRON_TRIGGER_META
from nanobot.cron.types import CronJob, CronPayload


@pytest.mark.asyncio
async def test_bound_cron_job_propagates_required_first_tool_flag() -> None:
    received = []
    records = []

    class Agent:
        tools = SimpleNamespace(get=lambda _name: None)

        async def submit_cron_turn(self, msg):
            received.append(msg)
            return OutboundMessage(channel="telegram", chat_id="42", content="briefing")

    class Recorder:
        def write_run_record(self, run_id, record):
            records.append((run_id, record))

    job = CronJob(
        id="news",
        name="news briefing",
        payload=CronPayload(
            message="search current news",
            require_first_tool=True,
            first_tool_name="web_search",
            session_key="telegram:42",
            origin_channel="telegram",
            origin_chat_id="42",
        ),
    )

    result = await run_bound_cron_job(job, agent=Agent(), cron=Recorder())

    assert result == "briefing"
    assert received[0].metadata[CRON_TRIGGER_META]["require_first_tool"] is True
    assert received[0].metadata[CRON_TRIGGER_META]["first_tool_name"] == "web_search"
    assert received[0].metadata["_wants_stream"] is False
    assert records[-1][1]["status"] == "ok"


@pytest.mark.asyncio
async def test_bound_cron_job_marks_agent_error_response_as_failed() -> None:
    records = []

    class Agent:
        tools = SimpleNamespace(get=lambda _name: None)

        async def submit_cron_turn(self, _msg):
            return OutboundMessage(
                channel="telegram",
                chat_id="42",
                content="Error: {'message': 'model request failed'}",
            )

    class Recorder:
        def write_run_record(self, run_id, record):
            records.append((run_id, record))

    job = CronJob(
        id="news",
        name="news briefing",
        payload=CronPayload(
            message="search current news",
            session_key="telegram:42",
            origin_channel="telegram",
            origin_chat_id="42",
        ),
    )

    with pytest.raises(RuntimeError, match="model request failed"):
        await run_bound_cron_job(job, agent=Agent(), cron=Recorder())

    assert records[-1][1]["status"] == "error"
    assert "model request failed" in records[-1][1]["error"]


@pytest.mark.asyncio
async def test_bound_cron_job_rejects_intermediate_tool_marker() -> None:
    records = []

    class Agent:
        tools = SimpleNamespace(get=lambda _name: None)

        async def submit_cron_turn(self, _msg):
            return OutboundMessage(
                channel="telegram",
                chat_id="42",
                content="[Calling tool",
            )

    class Recorder:
        def write_run_record(self, run_id, record):
            records.append((run_id, record))

    job = CronJob(
        id="news",
        name="news briefing",
        payload=CronPayload(
            message="search current news",
            session_key="telegram:42",
            origin_channel="telegram",
            origin_chat_id="42",
        ),
    )

    with pytest.raises(RuntimeError, match="Calling tool"):
        await run_bound_cron_job(job, agent=Agent(), cron=Recorder())

    assert records[-1][1]["status"] == "error"
