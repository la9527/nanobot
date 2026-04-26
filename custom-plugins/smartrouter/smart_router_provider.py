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


class SmartRouterProvider(LLMProvider):
    def __init__(
        self,
        *,
        router_config: RouterConfig,
        tier_providers: dict[TierName, LLMProvider],
        default_model: str,
    ):
        super().__init__(api_key=None, api_base=None)
        self._config = router_config
        self._tiers = tier_providers
        self._default_model = default_model
        self._policy = RoutingPolicy(router_config.policy)
        self._health = TierHealthTracker(router_config.health)
        self._logger = SmartRouterLogger(router_config.logging)

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
        for tier in build_fallback_chain(target_tier):
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

            try:
                if use_retry:
                    if on_content_delta is not None:
                        response = await provider.chat_stream_with_retry(
                            messages=messages,
                            tools=tier_tools,
                            model=target.model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            reasoning_effort=reasoning_effort,
                            tool_choice=tool_choice,
                            on_content_delta=on_content_delta,
                            retry_mode=retry_mode,
                            on_retry_wait=on_retry_wait,
                        )
                    else:
                        response = await provider.chat_with_retry(
                            messages=messages,
                            tools=tier_tools,
                            model=target.model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            reasoning_effort=reasoning_effort,
                            tool_choice=tool_choice,
                            retry_mode=retry_mode,
                            on_retry_wait=on_retry_wait,
                        )
                elif on_content_delta is not None:
                    response = await provider.chat_stream(
                        messages=messages,
                        tools=tier_tools,
                        model=target.model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        reasoning_effort=reasoning_effort,
                        tool_choice=tool_choice,
                        on_content_delta=on_content_delta,
                    )
                else:
                    response = await provider.chat(
                        messages=messages,
                        tools=tier_tools,
                        model=target.model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        reasoning_effort=reasoning_effort,
                        tool_choice=tool_choice,
                    )
            except Exception as exc:
                self._health.record_failure(tier)
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
                self._health.record_failure(tier)
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
                response.provider_metadata = {
                    **(response.provider_metadata or {}),
                    "smart_router_requested_tier": decision.requested_tier,
                    "smart_router_final_tier": tier,
                    "smart_router_final_model": target.model,
                }
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
            response.provider_metadata = {
                **(response.provider_metadata or {}),
                "smart_router_requested_tier": decision.requested_tier,
                "smart_router_final_tier": tier,
                "smart_router_final_model": target.model,
            }
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