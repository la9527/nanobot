from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nanobot.providers.base import GenerationSettings, LLMProvider, LLMResponse

CUSTOM_PLUGINS = Path(__file__).resolve().parents[2] / "custom-plugins"
if str(CUSTOM_PLUGINS) not in sys.path:
    sys.path.insert(0, str(CUSTOM_PLUGINS))

from smartrouter import SmartRouterProvider
from smartrouter.config import HealthSettings, LocalHybridSettings, LoggingSettings, PolicySettings, RouterConfig
from smartrouter.types import TierTarget


_CALL_SEQUENCE = 0


class _StubProvider(LLMProvider):
    def __init__(self, name: str, responses: list[LLMResponse]):
        super().__init__()
        self.name = name
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []
        self.generation = GenerationSettings()

    async def chat(
        self,
        messages,
        tools=None,
        model=None,
        max_tokens=4096,
        temperature=0.7,
        reasoning_effort=None,
        tool_choice=None,
    ) -> LLMResponse:
        global _CALL_SEQUENCE
        _CALL_SEQUENCE += 1
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "model": model,
                "call_sequence": _CALL_SEQUENCE,
            }
        )
        return self.responses.pop(0)

    async def chat_stream(
        self,
        messages,
        tools=None,
        model=None,
        max_tokens=4096,
        temperature=0.7,
        reasoning_effort=None,
        tool_choice=None,
        on_content_delta=None,
    ) -> LLMResponse:
        return await self.chat(
            messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
        )

    def get_default_model(self) -> str:
        return self.name


def _local_hybrid_settings() -> LocalHybridSettings:
    return LocalHybridSettings(
        enabled=False,
        mode="vision_first_text_writer",
        vision=None,
        on_vision_unavailable="error",
    )


def _enabled_local_hybrid_settings(
    *,
    on_vision_unavailable: str = "error",
) -> LocalHybridSettings:
    return LocalHybridSettings(
        enabled=True,
        mode="vision_first_text_writer",
        vision=TierTarget(tier="local", provider="vllm", model="vision-model"),
        on_vision_unavailable=on_vision_unavailable,
    )


def _image_request_messages() -> list[dict[str, object]]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What is in this image?"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,ZmFrZQ=="},
                },
            ],
        }
    ]


def _router(tmp_path: Path, *, allow_local_tools: bool = False) -> SmartRouterProvider:
    config = RouterConfig(
        enabled=True,
        allow_local_tools=allow_local_tools,
        local=TierTarget(tier="local", provider="vllm", model="local-model"),
        mini=TierTarget(tier="mini", provider="openrouter", model="mini-model"),
        full=TierTarget(tier="full", provider="openrouter", model="full-model"),
        local_hybrid=_local_hybrid_settings(),
        policy=PolicySettings(
            local_score_max=2,
            full_score_min=6,
            short_prompt_chars=120,
            medium_prompt_chars=800,
            long_prompt_chars=2000,
            tool_bonus=2,
            code_bonus=3,
            reasoning_bonus=3,
            history_bonus=2,
            attachment_bonus=2,
            full_keywords=["architecture", "refactor", "benchmark"],
            code_keywords=["python", "function", "traceback"],
            tool_keywords=["docker", "pytest", "command"],
        ),
        health=HealthSettings(failure_threshold=1, cooldown_seconds=999),
        logging=LoggingSettings(enabled=True, path=str(tmp_path / "smart-router.jsonl")),
    )
    local = _StubProvider("local", [LLMResponse(content="local ok")])
    mini = _StubProvider("mini", [LLMResponse(content="mini ok")])
    full = _StubProvider("full", [LLMResponse(content="full ok")])
    return SmartRouterProvider(
        router_config=config,
        tier_providers={"local": local, "mini": mini, "full": full},
        default_model="router",
    )


def test_smart_router_stores_optional_hybrid_vision_provider(tmp_path: Path) -> None:
    config = RouterConfig(
        enabled=True,
        allow_local_tools=False,
        local=TierTarget(tier="local", provider="vllm", model="local-model"),
        mini=TierTarget(tier="mini", provider="openrouter", model="mini-model"),
        full=TierTarget(tier="full", provider="openrouter", model="full-model"),
        local_hybrid=_local_hybrid_settings(),
        policy=PolicySettings(
            local_score_max=2,
            full_score_min=6,
            short_prompt_chars=120,
            medium_prompt_chars=800,
            long_prompt_chars=2000,
            tool_bonus=2,
            code_bonus=3,
            reasoning_bonus=3,
            history_bonus=2,
            attachment_bonus=2,
            full_keywords=["architecture", "refactor", "benchmark"],
            code_keywords=["python", "function", "traceback"],
            tool_keywords=["docker", "pytest", "command"],
        ),
        health=HealthSettings(failure_threshold=1, cooldown_seconds=999),
        logging=LoggingSettings(enabled=True, path=str(tmp_path / "smart-router.jsonl")),
    )
    local = _StubProvider("local", [LLMResponse(content="local ok")])
    mini = _StubProvider("mini", [LLMResponse(content="mini ok")])
    full = _StubProvider("full", [LLMResponse(content="full ok")])
    hybrid_vision = _StubProvider("vision", [LLMResponse(content="vision ok")])

    router = SmartRouterProvider(
        router_config=config,
        tier_providers={"local": local, "mini": mini, "full": full},
        default_model="router",
        hybrid_vision_provider=hybrid_vision,
    )

    assert router._hybrid_vision_provider is hybrid_vision


@pytest.mark.asyncio
async def test_smart_router_routes_simple_prompt_to_local(tmp_path: Path) -> None:
    router = _router(tmp_path)

    response = await router.chat(
        messages=[{"role": "user", "content": "hello"}],
        tools=[{"function": {"name": "exec"}}],
    )

    assert response.content == "local ok"
    assert router._tiers["local"].calls[0]["tools"] is None


@pytest.mark.asyncio
async def test_smart_router_routes_complex_prompt_to_full(tmp_path: Path) -> None:
    router = _router(tmp_path)

    response = await router.chat(
        messages=[
            {
                "role": "user",
                "content": "Please design an architecture refactor plan and benchmark tradeoffs for this migration.",
            }
        ],
        tools=None,
    )

    assert response.content == "full ok"
    assert router._tiers["full"].calls[0]["model"] == "full-model"


@pytest.mark.asyncio
async def test_smart_router_falls_back_after_local_error(tmp_path: Path) -> None:
    config = RouterConfig(
        enabled=True,
        allow_local_tools=False,
        local=TierTarget(tier="local", provider="vllm", model="local-model"),
        mini=TierTarget(tier="mini", provider="openrouter", model="mini-model"),
        full=TierTarget(tier="full", provider="openrouter", model="full-model"),
        local_hybrid=_local_hybrid_settings(),
        policy=PolicySettings(
            local_score_max=2,
            full_score_min=6,
            short_prompt_chars=120,
            medium_prompt_chars=800,
            long_prompt_chars=2000,
            tool_bonus=2,
            code_bonus=3,
            reasoning_bonus=3,
            history_bonus=2,
            attachment_bonus=2,
            full_keywords=["architecture"],
            code_keywords=["python"],
            tool_keywords=["docker"],
        ),
        health=HealthSettings(failure_threshold=1, cooldown_seconds=999),
        logging=LoggingSettings(enabled=False, path=str(tmp_path / "smart-router.jsonl")),
    )
    local = _StubProvider("local", [LLMResponse(content="boom", finish_reason="error")])
    mini = _StubProvider("mini", [LLMResponse(content="mini recovered")])
    full = _StubProvider("full", [LLMResponse(content="full unused")])
    router = SmartRouterProvider(
        router_config=config,
        tier_providers={"local": local, "mini": mini, "full": full},
        default_model="router",
    )

    response = await router.chat(messages=[{"role": "user", "content": "hello"}])

    assert response.content == "mini recovered"
    assert len(local.calls) == 1
    assert len(mini.calls) == 1


@pytest.mark.asyncio
async def test_smart_router_cools_down_local_immediately_after_timeout(tmp_path: Path) -> None:
    config = RouterConfig(
        enabled=True,
        allow_local_tools=False,
        local=TierTarget(tier="local", provider="vllm", model="local-model"),
        mini=TierTarget(tier="mini", provider="openrouter", model="mini-model"),
        full=TierTarget(tier="full", provider="openrouter", model="full-model"),
        local_hybrid=_local_hybrid_settings(),
        policy=PolicySettings(
            local_score_max=2,
            full_score_min=6,
            short_prompt_chars=120,
            medium_prompt_chars=800,
            long_prompt_chars=2000,
            tool_bonus=2,
            code_bonus=3,
            reasoning_bonus=3,
            history_bonus=2,
            attachment_bonus=2,
            full_keywords=["architecture"],
            code_keywords=["python"],
            tool_keywords=["docker"],
        ),
        health=HealthSettings(failure_threshold=3, cooldown_seconds=999),
        logging=LoggingSettings(enabled=False, path=str(tmp_path / "smart-router.jsonl")),
    )
    local = _StubProvider(
        "local",
        [LLMResponse(content="timed out", finish_reason="error", error_kind="timeout")],
    )
    mini = _StubProvider("mini", [LLMResponse(content="mini first"), LLMResponse(content="mini second")])
    full = _StubProvider("full", [LLMResponse(content="full unused")])
    router = SmartRouterProvider(
        router_config=config,
        tier_providers={"local": local, "mini": mini, "full": full},
        default_model="router",
    )

    first = await router.chat_with_retry(messages=[{"role": "user", "content": "hello"}])
    second = await router.chat_with_retry(messages=[{"role": "user", "content": "hello again"}])

    assert first.content == "mini first"
    assert second.content == "mini second"
    assert len(local.calls) == 1
    assert len(mini.calls) == 2


@pytest.mark.asyncio
async def test_smart_router_uses_vision_first_writer_for_local_image_request(tmp_path: Path) -> None:
    config = RouterConfig(
        enabled=True,
        allow_local_tools=False,
        local=TierTarget(tier="local", provider="vllm", model="local-model"),
        mini=TierTarget(tier="mini", provider="openrouter", model="mini-model"),
        full=TierTarget(tier="full", provider="openrouter", model="full-model"),
        local_hybrid=_enabled_local_hybrid_settings(),
        policy=PolicySettings(
            local_score_max=2,
            full_score_min=6,
            short_prompt_chars=120,
            medium_prompt_chars=800,
            long_prompt_chars=2000,
            tool_bonus=2,
            code_bonus=3,
            reasoning_bonus=3,
            history_bonus=2,
            attachment_bonus=2,
            full_keywords=["architecture"],
            code_keywords=["python"],
            tool_keywords=["docker"],
        ),
        health=HealthSettings(failure_threshold=1, cooldown_seconds=999),
        logging=LoggingSettings(enabled=False, path=str(tmp_path / "smart-router.jsonl")),
    )
    local = _StubProvider("local", [LLMResponse(content="local writer ok")])
    mini = _StubProvider("mini", [LLMResponse(content="mini ok")])
    full = _StubProvider("full", [LLMResponse(content="full ok")])
    vision = _StubProvider("vision", [LLMResponse(content="A camera icon on an orange background.")])
    router = SmartRouterProvider(
        router_config=config,
        tier_providers={"local": local, "mini": mini, "full": full},
        default_model="router",
        hybrid_vision_provider=vision,
    )

    response = await router.chat(messages=_image_request_messages())

    assert response.content == "local writer ok"
    assert len(vision.calls) == 1
    assert len(local.calls) == 1
    assert vision.calls[0]["call_sequence"] < local.calls[0]["call_sequence"]
    writer_message = local.calls[0]["messages"][0]
    assert writer_message["role"] == "user"
    assert "A camera icon on an orange background." in writer_message["content"]
    assert local.calls[0]["tools"] is None
    assert response.provider_metadata["smart_router_hybrid_mode"] == "vision_first_text_writer"
    assert response.provider_metadata["smart_router_vision_model"] == "vision-model"
    assert response.provider_metadata["smart_router_final_tier"] == "local"


@pytest.mark.asyncio
async def test_smart_router_compacts_hybrid_vision_messages_to_last_image_turn(tmp_path: Path) -> None:
    config = RouterConfig(
        enabled=True,
        allow_local_tools=False,
        local=TierTarget(tier="local", provider="vllm", model="local-model"),
        mini=TierTarget(tier="mini", provider="openrouter", model="mini-model"),
        full=TierTarget(tier="full", provider="openrouter", model="full-model"),
        local_hybrid=_enabled_local_hybrid_settings(),
        policy=PolicySettings(
            local_score_max=2,
            full_score_min=6,
            short_prompt_chars=120,
            medium_prompt_chars=800,
            long_prompt_chars=2000,
            tool_bonus=2,
            code_bonus=3,
            reasoning_bonus=3,
            history_bonus=2,
            attachment_bonus=2,
            full_keywords=["architecture"],
            code_keywords=["python"],
            tool_keywords=["docker"],
        ),
        health=HealthSettings(failure_threshold=1, cooldown_seconds=999),
        logging=LoggingSettings(enabled=False, path=str(tmp_path / "smart-router.jsonl")),
    )
    local = _StubProvider("local", [LLMResponse(content="local writer ok")])
    mini = _StubProvider("mini", [LLMResponse(content="mini ok")])
    full = _StubProvider("full", [LLMResponse(content="full ok")])
    vision = _StubProvider("vision", [LLMResponse(content="사진")])
    router = SmartRouterProvider(
        router_config=config,
        tier_providers={"local": local, "mini": mini, "full": full},
        default_model="router",
        hybrid_vision_provider=vision,
    )

    messages = [
        {"role": "system", "content": "very long system prompt"},
        {"role": "user", "content": "previous text-only question"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "[Runtime Context]\nCurrent Time: now\n[/Runtime Context]"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,ZmFrZQ=="},
                    "_meta": {"path": "/tmp/example.png"},
                },
                {"type": "text", "text": "첨부 이미지를 보고 한 단어로만 묘사해줘."},
            ],
        },
    ]

    await router.chat(messages=messages)

    vision_messages = vision.calls[0]["messages"]
    assert len(vision_messages) == 1
    assert vision_messages[0]["role"] == "user"
    blocks = vision_messages[0]["content"]
    assert [block["type"] for block in blocks] == ["text", "image_url", "text"]
    assert blocks[1]["_meta"] == {"path": "/tmp/example.png"}


@pytest.mark.asyncio
async def test_smart_router_returns_error_when_hybrid_vision_unavailable(tmp_path: Path) -> None:
    config = RouterConfig(
        enabled=True,
        allow_local_tools=False,
        local=TierTarget(tier="local", provider="vllm", model="local-model"),
        mini=TierTarget(tier="mini", provider="openrouter", model="mini-model"),
        full=TierTarget(tier="full", provider="openrouter", model="full-model"),
        local_hybrid=_enabled_local_hybrid_settings(on_vision_unavailable="error"),
        policy=PolicySettings(
            local_score_max=2,
            full_score_min=6,
            short_prompt_chars=120,
            medium_prompt_chars=800,
            long_prompt_chars=2000,
            tool_bonus=2,
            code_bonus=3,
            reasoning_bonus=3,
            history_bonus=2,
            attachment_bonus=2,
            full_keywords=["architecture"],
            code_keywords=["python"],
            tool_keywords=["docker"],
        ),
        health=HealthSettings(failure_threshold=1, cooldown_seconds=999),
        logging=LoggingSettings(enabled=False, path=str(tmp_path / "smart-router.jsonl")),
    )
    local = _StubProvider("local", [LLMResponse(content="local writer ok")])
    mini = _StubProvider("mini", [LLMResponse(content="mini ok")])
    full = _StubProvider("full", [LLMResponse(content="full ok")])
    vision = _StubProvider(
        "vision",
        [LLMResponse(content="vision endpoint unavailable", finish_reason="error", error_kind="connection")],
    )
    router = SmartRouterProvider(
        router_config=config,
        tier_providers={"local": local, "mini": mini, "full": full},
        default_model="router",
        hybrid_vision_provider=vision,
    )

    response = await router.chat(messages=_image_request_messages())

    assert response.finish_reason == "error"
    assert "vision" in (response.content or "").lower()
    assert len(local.calls) == 0
    assert len(mini.calls) == 0
    assert response.provider_metadata["smart_router_hybrid_mode"] == "vision_first_text_writer"
    assert response.provider_metadata["smart_router_vision_model"] == "vision-model"
    assert response.provider_metadata["smart_router_final_tier"] == "local"


@pytest.mark.asyncio
async def test_smart_router_falls_through_to_mini_when_hybrid_vision_unavailable(tmp_path: Path) -> None:
    config = RouterConfig(
        enabled=True,
        allow_local_tools=False,
        local=TierTarget(tier="local", provider="vllm", model="local-model"),
        mini=TierTarget(tier="mini", provider="openrouter", model="mini-model"),
        full=TierTarget(tier="full", provider="openrouter", model="full-model"),
        local_hybrid=_enabled_local_hybrid_settings(on_vision_unavailable="mini"),
        policy=PolicySettings(
            local_score_max=2,
            full_score_min=6,
            short_prompt_chars=120,
            medium_prompt_chars=800,
            long_prompt_chars=2000,
            tool_bonus=2,
            code_bonus=3,
            reasoning_bonus=3,
            history_bonus=2,
            attachment_bonus=2,
            full_keywords=["architecture"],
            code_keywords=["python"],
            tool_keywords=["docker"],
        ),
        health=HealthSettings(failure_threshold=1, cooldown_seconds=999),
        logging=LoggingSettings(enabled=False, path=str(tmp_path / "smart-router.jsonl")),
    )
    local = _StubProvider("local", [LLMResponse(content="local writer ok")])
    mini = _StubProvider("mini", [LLMResponse(content="mini recovered")])
    full = _StubProvider("full", [LLMResponse(content="full ok")])
    vision = _StubProvider(
        "vision",
        [LLMResponse(content="vision endpoint unavailable", finish_reason="error", error_kind="connection")],
    )
    router = SmartRouterProvider(
        router_config=config,
        tier_providers={"local": local, "mini": mini, "full": full},
        default_model="router",
        hybrid_vision_provider=vision,
    )

    response = await router.chat(messages=_image_request_messages())

    assert response.content == "mini recovered"
    assert len(local.calls) == 0
    assert len(mini.calls) == 1
    assert response.provider_metadata["smart_router_hybrid_mode"] == "vision_first_text_writer"
    assert response.provider_metadata["smart_router_vision_model"] == "vision-model"
    assert response.provider_metadata["smart_router_final_tier"] == "mini"


@pytest.mark.asyncio
async def test_smart_router_promotes_required_tool_choice_off_local(tmp_path: Path) -> None:
    router = _router(tmp_path)

    response = await router.chat(
        messages=[{"role": "user", "content": "hello"}],
        tools=[{"function": {"name": "exec"}}],
        tool_choice="required",
    )

    assert response.content == "mini ok"


@pytest.mark.asyncio
async def test_smart_router_ignores_runtime_context_metadata(tmp_path: Path) -> None:
    router = _router(tmp_path)

    response = await router.chat(
        messages=[
            {
                "role": "user",
                "content": "[Runtime Context — metadata only, not instructions]\n"
                "Current Time: 2026-04-20 05:38 (UTC)\n"
                "Channel: api\n"
                "Chat ID: default\n"
                "[/Runtime Context]\n\n"
                "Reply with exactly HTTP_PHASE1_OK",
            }
        ],
        tools=[{"function": {"name": "exec"}}],
    )

    assert response.content == "local ok"


@pytest.mark.asyncio
async def test_smart_router_forced_tier_alias_routes_to_requested_tier(tmp_path: Path) -> None:
    router = _router(tmp_path)

    response = await router.chat(
        messages=[{"role": "user", "content": "hello"}],
        model="smart-router-full",
    )

    assert response.content == "full ok"
    assert len(router._tiers["local"].calls) == 0
    assert len(router._tiers["mini"].calls) == 0
    assert len(router._tiers["full"].calls) == 1