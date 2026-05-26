from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from nanobot.providers.base import LLMProvider, LLMResponse

from .config import RouterConfig
from .fallback import build_fallback_chain
from .health import TierHealthTracker
from .logging import SmartRouterLogger
from .policy import RoutingPolicy
from .types import AttemptRecord, RouteDecision, TierName


_FORCED_TIER_ALIAS: dict[str, TierName] = {
    "smart-router-local": "local",
    "smart-router-mini": "mini",
    "smart-router-full": "full",
}

_TEXT_BLOCK_TYPES = {"text", "input_text", "output_text"}


class SmartRouterProvider(LLMProvider):
    def __init__(
        self,
        *,
        router_config: RouterConfig,
        tier_providers: dict[TierName, LLMProvider],
        default_model: str,
        hybrid_vision_provider: LLMProvider | None = None,
    ):
        super().__init__(api_key=None, api_base=None)
        self._config = router_config
        self._tiers = tier_providers
        self._default_model = default_model
        self._hybrid_vision_provider = hybrid_vision_provider
        self._policy = RoutingPolicy(router_config.policy)
        self._health = TierHealthTracker(router_config.health)
        self._logger = SmartRouterLogger(router_config.logging)

    @staticmethod
    def _should_use_provider_retry(tier: TierName, use_retry: bool) -> bool:
        # Local is an opportunistic first hop. Avoid stacking provider retries
        # there so timeout failures can fall through to mini/full quickly.
        return use_retry and tier != "local"

    @staticmethod
    def _should_immediately_cool_down(tier: TierName, response: LLMResponse) -> bool:
        if tier != "local":
            return False
        if response.error_kind in {"timeout", "connection"}:
            return True
        content = (response.content or "").lower()
        return "timed out" in content or "connection" in content or "refused" in content

    @staticmethod
    def _is_image_block(block: Any) -> bool:
        if not isinstance(block, dict):
            return False
        block_type = block.get("type")
        if block_type in {"image", "image_url", "input_image"}:
            return True
        if isinstance(block.get("image_url"), dict):
            return True
        mime_type = block.get("mimeType")
        return isinstance(mime_type, str) and mime_type.startswith("image/")

    @classmethod
    def _has_image_content(cls, messages: list[dict[str, Any]]) -> bool:
        for message in messages:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            if any(cls._is_image_block(block) for block in content):
                return True
        return False

    @classmethod
    def _content_text(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            text = value.get("text")
            return text if isinstance(text, str) else ""
        if not isinstance(value, list):
            return str(value)

        parts: list[str] = []
        for item in value:
            if not isinstance(item, dict):
                if item is not None:
                    parts.append(str(item))
                continue
            if item.get("type") in _TEXT_BLOCK_TYPES and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(part.strip() for part in parts if part and part.strip())

    @classmethod
    def _build_hybrid_writer_messages(
        cls,
        messages: list[dict[str, Any]],
        *,
        vision_summary: str,
    ) -> list[dict[str, Any]]:
        writer_messages: list[dict[str, Any]] = []
        summary_block = f"[Vision summary]\n{vision_summary.strip()}\n[/Vision summary]"

        for message in messages:
            content = message.get("content")
            has_image = isinstance(content, list) and any(cls._is_image_block(block) for block in content)
            content_text = cls._content_text(content).strip()
            new_message = {key: value for key, value in message.items() if key != "content"}

            if has_image:
                if content_text:
                    new_message["content"] = f"{content_text}\n\n{summary_block}"
                else:
                    new_message["content"] = summary_block
                writer_messages.append(new_message)
                continue

            if content_text:
                new_message["content"] = content_text
                writer_messages.append(new_message)
                continue

            if message.get("role") == "assistant" and message.get("tool_calls"):
                new_message["content"] = None
                writer_messages.append(new_message)

        return writer_messages

    @classmethod
    def _build_hybrid_vision_messages(
        cls,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Keep only the last image-bearing turn for the vision summarizer.

        The vision lane only needs the current multimodal user turn. Passing the
        full system prompt and long text history can cause local vision runtimes
        to return an empty error response instead of a usable summary.
        """
        for message in reversed(messages):
            content = message.get("content")
            if not isinstance(content, list):
                continue
            if not any(cls._is_image_block(block) for block in content):
                continue

            compact_content: list[dict[str, Any]] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if cls._is_image_block(block):
                    compact_content.append(block)
                    continue
                if block.get("type") in _TEXT_BLOCK_TYPES and isinstance(block.get("text"), str):
                    text = block["text"].strip()
                    if text:
                        compact_content.append({"type": "text", "text": text})

            if compact_content:
                return [{
                    key: value for key, value in message.items() if key != "content"
                } | {"content": compact_content}]

        return messages

    async def _call_provider(
        self,
        *,
        provider: LLMProvider,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
        max_tokens: int,
        temperature: float,
        reasoning_effort: str | None,
        tool_choice: str | dict[str, Any] | None,
        use_retry: bool,
        on_content_delta: Callable[[str], Awaitable[None]] | None,
        retry_mode: str,
        on_retry_wait: Callable[[str], Awaitable[None]] | None,
    ) -> LLMResponse:
        if use_retry:
            if on_content_delta is not None:
                return await provider.chat_stream_with_retry(
                    messages=messages,
                    tools=tools,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    reasoning_effort=reasoning_effort,
                    tool_choice=tool_choice,
                    on_content_delta=on_content_delta,
                    retry_mode=retry_mode,
                    on_retry_wait=on_retry_wait,
                )
            return await provider.chat_with_retry(
                messages=messages,
                tools=tools,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                tool_choice=tool_choice,
                retry_mode=retry_mode,
                on_retry_wait=on_retry_wait,
            )

        if on_content_delta is not None:
            return await provider.chat_stream(
                messages=messages,
                tools=tools,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                tool_choice=tool_choice,
                on_content_delta=on_content_delta,
            )
        return await provider.chat(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
        )

    @staticmethod
    def _with_router_metadata(
        response: LLMResponse,
        *,
        decision: RouteDecision,
        final_tier: TierName,
        final_model: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> LLMResponse:
        response.provider_metadata = {
            **(response.provider_metadata or {}),
            "smart_router_requested_tier": decision.requested_tier,
            "smart_router_final_tier": final_tier,
            "smart_router_final_model": final_model,
            **(extra_metadata or {}),
        }
        return response

    async def _maybe_run_local_hybrid(
        self,
        *,
        decision: RouteDecision,
        provider: LLMProvider,
        target_model: str,
        tier_tools: list[dict[str, Any]] | None,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
        reasoning_effort: str | None,
        use_retry: bool,
        on_content_delta: Callable[[str], Awaitable[None]] | None,
        retry_mode: str,
        on_retry_wait: Callable[[str], Awaitable[None]] | None,
        attempts: list[AttemptRecord],
    ) -> tuple[LLMResponse | None, TierName | None, dict[str, Any] | None]:
        hybrid_settings = self._config.local_hybrid
        vision_target = hybrid_settings.vision
        if (
            not hybrid_settings.enabled
            or hybrid_settings.mode != "vision_first_text_writer"
            or self._hybrid_vision_provider is None
            or vision_target is None
            or not self._has_image_content(messages)
        ):
            return None, None, None

        hybrid_metadata = {
            "smart_router_hybrid_mode": hybrid_settings.mode,
            "smart_router_vision_model": vision_target.model,
        }
        vision_messages = self._build_hybrid_vision_messages(messages)

        try:
            vision_response = await self._call_provider(
                provider=self._hybrid_vision_provider,
                messages=vision_messages,
                tools=None,
                model=vision_target.model,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                tool_choice=None,
                use_retry=False,
                on_content_delta=None,
                retry_mode=retry_mode,
                on_retry_wait=on_retry_wait,
            )
        except Exception as exc:
            attempts.append(
                AttemptRecord(
                    tier="local",
                    model=vision_target.model,
                    provider=vision_target.provider,
                    status="hybrid_vision_exception",
                    error=str(exc),
                )
            )
            vision_response = LLMResponse(
                content=f"Local hybrid vision provider unavailable: {exc}",
                finish_reason="error",
                error_kind="connection",
            )

        vision_summary = (vision_response.content or "").strip()
        if vision_response.finish_reason == "error" or not vision_summary:
            error_text = vision_summary or "Local hybrid vision provider unavailable."
            attempts.append(
                AttemptRecord(
                    tier="local",
                    model=vision_target.model,
                    provider=vision_target.provider,
                    status="hybrid_vision_error",
                    error=error_text,
                )
            )
            fallback_tier = hybrid_settings.on_vision_unavailable
            if fallback_tier in {"mini", "full"}:
                return None, fallback_tier, hybrid_metadata
            error_response = LLMResponse(
                content=f"Local hybrid vision provider unavailable: {error_text}",
                finish_reason="error",
                error_kind=vision_response.error_kind or "connection",
            )
            return self._with_router_metadata(
                error_response,
                decision=decision,
                final_tier="local",
                final_model=target_model,
                extra_metadata=hybrid_metadata,
            ), None, hybrid_metadata

        attempts.append(
            AttemptRecord(
                tier="local",
                model=vision_target.model,
                provider=vision_target.provider,
                status="hybrid_vision_ok",
            )
        )
        writer_messages = self._build_hybrid_writer_messages(messages, vision_summary=vision_summary)
        writer_response = await self._call_provider(
            provider=provider,
            messages=writer_messages,
            tools=None,
            model=target_model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=None,
            use_retry=use_retry,
            on_content_delta=on_content_delta,
            retry_mode=retry_mode,
            on_retry_wait=on_retry_wait,
        )
        return self._with_router_metadata(
            writer_response,
            decision=decision,
            final_tier="local",
            final_model=target_model,
            extra_metadata=hybrid_metadata,
        ), None, hybrid_metadata

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        return await self._dispatch(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
            use_retry=False,
            on_content_delta=None,
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        return await self._dispatch(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
            use_retry=False,
            on_content_delta=on_content_delta,
        )

    async def chat_with_retry(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: object = LLMProvider._SENTINEL,
        temperature: object = LLMProvider._SENTINEL,
        reasoning_effort: object = LLMProvider._SENTINEL,
        tool_choice: str | dict[str, Any] | None = None,
        retry_mode: str = "standard",
        on_retry_wait: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        if max_tokens is self._SENTINEL or max_tokens is None:
            max_tokens = self.generation.max_tokens
        if temperature is self._SENTINEL or temperature is None:
            temperature = self.generation.temperature
        if reasoning_effort is self._SENTINEL:
            reasoning_effort = self.generation.reasoning_effort
        return await self._dispatch(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
            use_retry=True,
            on_content_delta=None,
            retry_mode=retry_mode,
            on_retry_wait=on_retry_wait,
        )

    async def chat_stream_with_retry(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: object = LLMProvider._SENTINEL,
        temperature: object = LLMProvider._SENTINEL,
        reasoning_effort: object = LLMProvider._SENTINEL,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
        retry_mode: str = "standard",
        on_retry_wait: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        if max_tokens is self._SENTINEL or max_tokens is None:
            max_tokens = self.generation.max_tokens
        if temperature is self._SENTINEL or temperature is None:
            temperature = self.generation.temperature
        if reasoning_effort is self._SENTINEL:
            reasoning_effort = self.generation.reasoning_effort
        return await self._dispatch(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
            use_retry=True,
            on_content_delta=on_content_delta,
            retry_mode=retry_mode,
            on_retry_wait=on_retry_wait,
        )

    def get_default_model(self) -> str:
        return self._default_model

    def _route(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        model: str | None = None,
    ) -> RouteDecision:
        forced = _FORCED_TIER_ALIAS.get((model or "").strip())
        if forced is not None:
            return RouteDecision(
                requested_tier=forced,
                score=0,
                reason_codes=[f"forced_tier:{forced}"],
                features=self._policy.extract_features(messages=messages, tools=tools),
            )
        return self._policy.choose(messages=messages, tools=tools)

    async def _dispatch(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str | None,
        max_tokens: int,
        temperature: float,
        reasoning_effort: str | None,
        tool_choice: str | dict[str, Any] | None,
        use_retry: bool,
        on_content_delta: Callable[[str], Awaitable[None]] | None,
        retry_mode: str = "standard",
        on_retry_wait: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        decision = self._route(messages, tools, model=model)
        target_tier = decision.requested_tier
        if target_tier == "local" and tool_choice not in (None, "auto") and not self._config.allow_local_tools:
            target_tier = "mini"
            decision.reason_codes.append("tool_choice_requires_remote")

        attempts: list[AttemptRecord] = []
        next_tier_override: TierName | None = None
        pending_extra_metadata: dict[str, Any] | None = None
        for tier in build_fallback_chain(target_tier):
            if next_tier_override is not None and tier != next_tier_override:
                continue
            next_tier_override = None

            provider = self._tiers[tier]
            target = getattr(self._config, tier)
            if not self._health.is_available(tier):
                attempts.append(
                    AttemptRecord(
                        tier=tier,
                        model=target.model,
                        provider=target.provider,
                        status="cooldown",
                        error="tier cooling down",
                    )
                )
                continue

            tier_tools = tools
            if tier == "local" and not self._config.allow_local_tools:
                tier_tools = None

            should_retry_tier = self._should_use_provider_retry(tier, use_retry)

            try:
                if tier == "local":
                    hybrid_response, fallback_tier, hybrid_metadata = await self._maybe_run_local_hybrid(
                        decision=decision,
                        provider=provider,
                        target_model=target.model,
                        tier_tools=tier_tools,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        reasoning_effort=reasoning_effort,
                        use_retry=should_retry_tier,
                        on_content_delta=on_content_delta,
                        retry_mode=retry_mode,
                        on_retry_wait=on_retry_wait,
                        attempts=attempts,
                    )
                    if fallback_tier is not None:
                        pending_extra_metadata = hybrid_metadata
                        next_tier_override = fallback_tier
                        continue
                    if hybrid_response is not None:
                        response = hybrid_response
                        if response.finish_reason == "error":
                            self._logger.log(
                                decision=decision,
                                final_tier=tier,
                                request_model=model,
                                attempts=attempts,
                            )
                            return response
                    else:
                        response = await self._call_provider(
                            provider=provider,
                            messages=messages,
                            tools=tier_tools,
                            model=target.model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            reasoning_effort=reasoning_effort,
                            tool_choice=tool_choice,
                            use_retry=should_retry_tier,
                            on_content_delta=on_content_delta,
                            retry_mode=retry_mode,
                            on_retry_wait=on_retry_wait,
                        )
                else:
                    response = await self._call_provider(
                        provider=provider,
                        messages=messages,
                        tools=tier_tools,
                        model=target.model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        reasoning_effort=reasoning_effort,
                        tool_choice=tool_choice,
                        use_retry=should_retry_tier,
                        on_content_delta=on_content_delta,
                        retry_mode=retry_mode,
                        on_retry_wait=on_retry_wait,
                    )
            except Exception as exc:
                self._health.record_failure(tier, immediate=(tier == "local"))
                attempts.append(
                    AttemptRecord(
                        tier=tier,
                        model=target.model,
                        provider=target.provider,
                        status="exception",
                        error=str(exc),
                    )
                )
                continue

            if response.finish_reason == "error":
                self._health.record_failure(
                    tier,
                    immediate=self._should_immediately_cool_down(tier, response),
                )
                attempts.append(
                    AttemptRecord(
                        tier=tier,
                        model=target.model,
                        provider=target.provider,
                        status="error",
                        error=response.content,
                    )
                )
                if tier != "full":
                    continue
                self._with_router_metadata(
                    response,
                    decision=decision,
                    final_tier=tier,
                    final_model=target.model,
                    extra_metadata=pending_extra_metadata,
                )
                self._logger.log(
                    decision=decision,
                    final_tier=tier,
                    request_model=model,
                    attempts=attempts,
                )
                return response

            self._health.record_success(tier)
            attempts.append(
                AttemptRecord(
                    tier=tier,
                    model=target.model,
                    provider=target.provider,
                    status="ok",
                )
            )
            self._with_router_metadata(
                response,
                decision=decision,
                final_tier=tier,
                final_model=target.model,
                extra_metadata=pending_extra_metadata,
            )
            self._logger.log(
                decision=decision,
                final_tier=tier,
                request_model=model,
                attempts=attempts,
            )
            return response

        self._logger.log(
            decision=decision,
            final_tier=None,
            request_model=model,
            attempts=attempts,
        )
        return LLMResponse(
            content="Smart router could not find an available tier.",
            finish_reason="error",
        )