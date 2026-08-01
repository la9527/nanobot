"""Execution helpers for session-bound cron jobs."""

from __future__ import annotations

import asyncio
import hashlib
import shlex
import time
import uuid
from typing import Any, Protocol

from nanobot.agent.tools.cron import CronTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.cron.session_delivery import origin_delivery_context
from nanobot.cron.session_turns import (
    CRON_DEFER_UNTIL_IDLE_META,
    CRON_TRIGGER_META,
    is_invalid_cron_response,
)
from nanobot.cron.types import CronJob
from nanobot.cron.webui_metadata import cron_proactive_delivery_metadata
from nanobot.utils.prompt_templates import render_template


class BoundCronAgent(Protocol):
    tools: Any
    bus: Any

    async def submit_cron_turn(self, msg: InboundMessage) -> OutboundMessage | None:
        ...


class CronRunRecorder(Protocol):
    def write_run_record(self, run_id: str, record: dict[str, Any]) -> None:
        ...


async def _run_direct_command(command: str) -> str:
    """Run a configured collector without invoking a model or a shell."""
    args = shlex.split(command)
    if not args:
        raise ValueError("direct cron command is empty")
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    response = stdout.decode("utf-8", errors="replace").strip()
    if process.returncode:
        error = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(error or f"direct cron command exited {process.returncode}")
    return response


def _cron_prompt_ref(prompt: str) -> dict[str, Any]:
    return {
        "id": "cron.agent_turn.reminder",
        "version": 1,
        "sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    }


def _bound_session_delivery_context(
    job: CronJob,
    *,
    turn_seed: str,
    source_label: str | None,
) -> tuple[str, str, dict[str, Any]]:
    channel, chat_id, metadata = origin_delivery_context(job)

    if channel == "websocket":
        metadata["webui"] = True
        metadata.update(
            cron_proactive_delivery_metadata(
                "websocket",
                metadata,
                turn_seed=turn_seed,
                source_label=source_label,
            )
        )

    return channel, chat_id, metadata


async def run_bound_cron_job(
    job: CronJob,
    *,
    agent: BoundCronAgent,
    cron: CronRunRecorder,
) -> str | None:
    """Execute a session-bound cron job as a normal agent session turn."""
    session_key = job.payload.session_key
    if not session_key:
        raise ValueError(f"cron job {job.id} is missing payload.session_key")

    prompt = render_template(
        "agent/cron_reminder.md",
        strip=True,
        message=job.payload.message,
    )
    prompt_ref = _cron_prompt_ref(prompt)
    run_id = f"{job.id}:{int(time.time() * 1000)}:{uuid.uuid4().hex[:8]}"
    channel, chat_id, metadata = _bound_session_delivery_context(
        job,
        turn_seed=f"cron:{job.id}",
        source_label=job.name,
    )
    metadata[CRON_TRIGGER_META] = {
        "job_id": job.id,
        "job_name": job.name,
        "run_id": run_id,
        "require_first_tool": job.payload.require_first_tool,
        "first_tool_name": job.payload.first_tool_name,
        "prompt_ref": prompt_ref,
        "persist_content": (
            f"Scheduled cron job triggered: {job.name}\n\n{job.payload.message}"
        ),
    }
    metadata[CRON_DEFER_UNTIL_IDLE_META] = True
    # Cron deliveries must only send the validated final answer. Streaming
    # tool-call/intermediate deltas can otherwise leak to Telegram.
    metadata["_wants_stream"] = False
    run_record_base: dict[str, Any] = {
        "job_id": job.id,
        "job_name": job.name,
        "session_key": session_key,
        "prompt_ref": prompt_ref,
        "prompt_vars": {"message": job.payload.message},
        "rendered_prompt": prompt,
    }

    cron.write_run_record(
        run_id,
        {
            **run_record_base,
            "status": "queued",
        },
    )

    if job.payload.direct_command:
        try:
            response = await _run_direct_command(job.payload.direct_command)
            if response.lstrip().startswith("Error:") or is_invalid_cron_response(response):
                raise RuntimeError(response or "Direct cron command produced no final response")
            await agent.bus.publish_outbound(
                OutboundMessage(
                    channel=channel,
                    chat_id=chat_id,
                    content=response,
                    metadata=metadata,
                )
            )
        except (Exception, asyncio.CancelledError) as exc:
            error_text = str(exc) or exc.__class__.__name__
            cron.write_run_record(
                run_id,
                {
                    **run_record_base,
                    "status": "error",
                    "error": error_text,
                },
            )
            raise
        cron.write_run_record(
            run_id,
            {
                **run_record_base,
                "status": "ok",
                "response": response,
            },
        )
        return response

    cron_tool = agent.tools.get("cron")
    cron_token = None
    if isinstance(cron_tool, CronTool):
        cron_token = cron_tool.set_cron_context(True)
    try:
        resp = await agent.submit_cron_turn(
            InboundMessage(
                channel=channel,
                sender_id="cron",
                chat_id=chat_id,
                content=prompt,
                metadata=metadata,
                session_key_override=session_key,
            )
        )
    except (Exception, asyncio.CancelledError) as exc:
        error_text = str(exc) or exc.__class__.__name__
        cron.write_run_record(
            run_id,
            {
                **run_record_base,
                "status": "error",
                "error": error_text,
            },
        )
        raise
    finally:
        if isinstance(cron_tool, CronTool) and cron_token is not None:
            cron_tool.reset_cron_context(cron_token)

    response = resp.content if resp else ""
    if response.lstrip().startswith("Error:") or is_invalid_cron_response(response):
        # AgentLoop converts provider failures into an outbound error message.
        # Treat that result as a failed cron run rather than reporting a false
        # success to the scheduler and run-history UI.
        error_text = response.strip() or "Cron turn produced no final response"
        cron.write_run_record(
            run_id,
            {
                **run_record_base,
                "status": "error",
                "error": error_text,
            },
        )
        raise RuntimeError(error_text)
    cron.write_run_record(
        run_id,
        {
            **run_record_base,
            "status": "ok",
            "response": response,
        },
    )
    return response
