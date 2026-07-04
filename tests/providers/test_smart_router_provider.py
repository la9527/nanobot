from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

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
                "max_tokens": max_tokens,
                "temperature": temperature,
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
        on_thinking_delta=None,
        on_tool_call_delta=None,
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


class _FailOnStreamProvider(_StubProvider):
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
        raise AssertionError("chat_stream should not be used")


class _ExplodingProvider(_StubProvider):
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
                "max_tokens": max_tokens,
                "temperature": temperature,
                "call_sequence": _CALL_SEQUENCE,
            }
        )
        raise RuntimeError("writer exploded")


class _StubHybridVisionRuntimeManager:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    async def ensure_runtime_ready(self, vision_model: str) -> None:
        self.events.append(("ensure", vision_model))

    async def mark_used(self, vision_model: str) -> None:
        self.events.append(("mark_used", vision_model))

    async def release(self, vision_model: str) -> None:
        self.events.append(("release", vision_model))


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


def _image_request_messages(request_text: str = "What is in this image?") -> list[dict[str, object]]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": request_text},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,ZmFrZQ=="},
                },
            ],
        }
    ]


def _write_test_image(path: Path, *, size: tuple[int, int]) -> Path:
    Image.new("RGB", size, color=(240, 120, 80)).save(path)
    return path


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
async def test_smart_router_chat_stream_with_retry_accepts_full_runner_kwargs(tmp_path: Path) -> None:
    """Regression test: AgentRunner._request_model calls chat_stream_with_retry
    with on_thinking_delta/on_tool_call_delta/on_stream_recover in addition to
    on_content_delta. SmartRouterProvider must accept and forward all of them
    without raising TypeError (previously only on_content_delta was accepted).
    """
    router = _router(tmp_path)

    content_deltas: list[str] = []
    thinking_deltas: list[str] = []
    tool_call_deltas: list[dict[str, object]] = []
    recovered = False

    async def _on_content_delta(delta: str) -> None:
        content_deltas.append(delta)

    async def _on_thinking_delta(delta: str) -> None:
        thinking_deltas.append(delta)

    async def _on_tool_call_delta(delta: dict[str, object]) -> None:
        tool_call_deltas.append(delta)

    async def _on_stream_recover() -> None:
        nonlocal recovered
        recovered = True

    response = await router.chat_stream_with_retry(
        messages=[{"role": "user", "content": "hello"}],
        tools=None,
        on_content_delta=_on_content_delta,
        on_thinking_delta=_on_thinking_delta,
        on_tool_call_delta=_on_tool_call_delta,
        on_stream_recover=_on_stream_recover,
    )

    assert response.content == "local ok"
    # The stub tier providers pass streamed calls straight through to chat()
    # without invoking delta callbacks; the point of this test is that
    # SmartRouterProvider accepts and forwards these kwargs without raising
    # TypeError (previously only on_content_delta was accepted).
    assert thinking_deltas == []
    assert tool_call_deltas == []
    assert recovered is False


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
    assert len(local.calls[0]["messages"]) == 1
    writer_message = local.calls[0]["messages"][0]
    assert writer_message["role"] == "user"
    assert "Use the vision summary as the primary factual source" in writer_message["content"]
    assert "Do not restate, explain, or comment on the request itself" in writer_message["content"]
    assert "Prefer the most specific concrete subject, object, or concept" in writer_message["content"]
    assert "Avoid generic fallback words like image, photo, picture, object, or scene" in writer_message["content"]
    assert "Name the depicted icon or object itself" in writer_message["content"]
    assert "camera icon, answer camera rather than image, photo, or sound" in writer_message["content"]
    assert "return only that payload with no markdown or extra prose" in writer_message["content"]
    assert "A camera icon on an orange background." in writer_message["content"]
    assert "[User request]" in writer_message["content"]
    assert "[/User request]" in writer_message["content"]
    assert "What is in this image?" in writer_message["content"]
    assert local.calls[0]["tools"] is None
    assert response.provider_metadata["smart_router_hybrid_mode"] == "vision_first_text_writer"
    assert response.provider_metadata["smart_router_vision_model"] == "vision-model"
    assert response.provider_metadata["smart_router_final_tier"] == "local"
    assert local.calls[0]["max_tokens"] == 256
    assert local.calls[0]["temperature"] == 0.7


@pytest.mark.asyncio
async def test_smart_router_ensures_on_demand_vision_runtime_before_hybrid_call(tmp_path: Path) -> None:
    config = RouterConfig(
        enabled=True,
        allow_local_tools=False,
        local=TierTarget(tier="local", provider="vllm", model="local-model"),
        mini=TierTarget(tier="mini", provider="openrouter", model="mini-model"),
        full=TierTarget(tier="full", provider="openrouter", model="full-model"),
        local_hybrid=LocalHybridSettings(
            enabled=True,
            mode="vision_first_text_writer",
            vision=TierTarget(
                tier="local",
                provider="rapid-mlx",
                model="mlx-community/Qwen3-VL-4B-Instruct-4bit",
            ),
            on_vision_unavailable="error",
        ),
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
    vision = _StubProvider("vision", [LLMResponse(content="camera icon")])
    runtime_manager = _StubHybridVisionRuntimeManager()
    router = SmartRouterProvider(
        router_config=config,
        tier_providers={"local": local, "mini": mini, "full": full},
        default_model="router",
        hybrid_vision_provider=vision,
    )
    router._hybrid_vision_runtime_manager = runtime_manager

    response = await router.chat(messages=_image_request_messages())

    assert response.content == "local writer ok"
    assert runtime_manager.events == [
        ("ensure", "mlx-community/Qwen3-VL-4B-Instruct-4bit"),
        ("mark_used", "mlx-community/Qwen3-VL-4B-Instruct-4bit"),
        ("release", "mlx-community/Qwen3-VL-4B-Instruct-4bit"),
    ]
    assert response.provider_metadata["smart_router_vision_runtime_mode"] == "broker"


@pytest.mark.asyncio
async def test_smart_router_releases_broker_lease_when_hybrid_writer_raises(tmp_path: Path) -> None:
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
    local = _ExplodingProvider("local", [])
    mini = _StubProvider("mini", [LLMResponse(content="mini ok")])
    full = _StubProvider("full", [LLMResponse(content="full ok")])
    vision = _StubProvider("vision", [LLMResponse(content="camera icon")])
    runtime_manager = _StubHybridVisionRuntimeManager()
    router = SmartRouterProvider(
        router_config=config,
        tier_providers={"local": local, "mini": mini, "full": full},
        default_model="router",
        hybrid_vision_provider=vision,
    )
    router._hybrid_vision_runtime_manager = runtime_manager

    response = await router.chat(messages=_image_request_messages())

    assert response.content == "mini ok"
    assert len(local.calls) == 1
    assert len(mini.calls) == 1
    assert runtime_manager.events == [
        ("ensure", "vision-model"),
        ("mark_used", "vision-model"),
        ("release", "vision-model"),
    ]


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
    assert [block["type"] for block in vision_messages[0]["content"]] == ["text", "image_url"]
    assert vision_messages[0]["content"][0]["text"].startswith("Describe the main visible subject")
    assert "very long system prompt" not in vision_messages[0]["content"][0]["text"]
    assert "첨부 이미지를 보고 한 단어로만 묘사해줘." not in vision_messages[0]["content"][0]["text"]

    writer_messages = local.calls[0]["messages"]
    assert len(writer_messages) == 1
    assert writer_messages[0]["role"] == "user"
    assert "very long system prompt" not in writer_messages[0]["content"]
    assert "previous text-only question" not in writer_messages[0]["content"]
    assert "첨부 이미지를 보고 한 단어로만 묘사해줘." in writer_messages[0]["content"]


def test_smart_router_downscales_large_hybrid_vision_image_to_temp_path(tmp_path: Path) -> None:
    source_image = _write_test_image(tmp_path / "large-vision.png", size=(1365, 2048))
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image."},
                {
                    "type": "image_url",
                    "image_url": {"url": str(source_image)},
                    "_meta": {"path": str(source_image)},
                },
            ],
        }
    ]

    vision_messages = SmartRouterProvider._build_hybrid_vision_messages(messages)

    image_block = vision_messages[0]["content"][1]
    resized_path = image_block["image_url"]["url"]
    assert resized_path != str(source_image)
    assert image_block["_meta"]["path"] == resized_path
    assert image_block["_meta"]["original_path"] == str(source_image)
    with Image.open(resized_path) as resized_image:
        assert max(resized_image.size) <= 1280
        assert resized_image.width * resized_image.height <= 1280 * 28 * 28
        assert resized_image.width % 28 == 0
        assert resized_image.height % 28 == 0


def test_smart_router_keeps_small_hybrid_vision_image_path(tmp_path: Path) -> None:
    source_image = _write_test_image(tmp_path / "small-vision.png", size=(683, 1024))
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image."},
                {
                    "type": "image_url",
                    "image_url": {"url": str(source_image)},
                    "_meta": {"path": str(source_image)},
                },
            ],
        }
    ]

    vision_messages = SmartRouterProvider._build_hybrid_vision_messages(messages)

    image_block = vision_messages[0]["content"][1]
    assert image_block["image_url"]["url"] == str(source_image)
    assert image_block["_meta"]["path"] == str(source_image)
    assert "original_path" not in image_block["_meta"]


@pytest.mark.asyncio
async def test_smart_router_hybrid_writer_uses_non_stream_writer_call(tmp_path: Path) -> None:
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
    local = _FailOnStreamProvider("local", [LLMResponse(content="안녕")])
    mini = _StubProvider("mini", [LLMResponse(content="mini ok")])
    full = _StubProvider("full", [LLMResponse(content="full ok")])
    vision = _StubProvider("vision", [LLMResponse(content="사진")])
    router = SmartRouterProvider(
        router_config=config,
        tier_providers={"local": local, "mini": mini, "full": full},
        default_model="router",
        hybrid_vision_provider=vision,
    )

    chunks: list[str] = []

    response = await router.chat_stream(
        messages=_image_request_messages("첨부 이미지를 보고 한글로 한 단어만 답해줘."),
        on_content_delta=chunks.append,
    )

    assert response.content == "안녕"
    assert chunks == []
    assert len(local.calls) == 1
    assert len(vision.calls) == 1
    assert local.calls[0]["max_tokens"] == 16
    assert local.calls[0]["temperature"] == 0.0

    vision_messages = vision.calls[0]["messages"]
    assert len(vision_messages) == 1
    assert vision_messages[0]["role"] == "user"
    blocks = vision_messages[0]["content"]
    assert [block["type"] for block in blocks] == ["text", "image_url"]


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