"""Bridge between named model targets (including smart-router) and the
standard provider factory.

This module intentionally reuses ``nanobot.providers.factory.make_provider``
(backend dispatch, fallback wrapping, bedrock/oauth handling, etc.) instead of
re-implementing provider construction. A tier's ``model``/``provider`` pair is
expressed as a synthetic ``ModelPresetConfig`` so ``make_provider`` resolves it
exactly the same way it resolves any other configured preset.
"""

from __future__ import annotations

from typing import Any

from nanobot.config.schema import Config, ModelPresetConfig
from nanobot.providers.base import LLMProvider


def make_base_provider(
    config: Config,
    *,
    model: str | None = None,
    provider_name: str | None = None,
) -> LLMProvider:
    """Create a concrete provider for a specific provider/model pair.

    Used both as the loop's default provider factory and as the
    ``make_base_provider`` callback runtime plugins (e.g. smart-router) use to
    build their own tier sub-providers.
    """
    from nanobot.providers.factory import make_provider

    defaults = config.agents.defaults
    preset = ModelPresetConfig(
        model=model or defaults.model,
        provider=provider_name or "auto",
        max_tokens=defaults.max_tokens,
        context_window_tokens=defaults.context_window_tokens,
        temperature=defaults.temperature,
        reasoning_effort=defaults.reasoning_effort,
    )
    return make_provider(config, preset=preset)


def make_target_aware_provider(config: Config) -> LLMProvider:
    """Create the LLM provider implied by config, honoring an enabled smart-router plugin.

    Equivalent to ``make_provider(config)`` when no runtime plugin overrides
    provider construction; delegates to the plugin's own ``build_provider``
    hook (e.g. smart-router's tier composition) when enabled.
    """
    from nanobot.plugins import RuntimePluginContext, load_runtime_plugin
    from nanobot.plugins.registry import is_runtime_plugin_enabled
    from nanobot.providers.factory import make_provider

    try:
        plugin = load_runtime_plugin("smartrouter")
    except LookupError:
        plugin = None

    if plugin is not None and is_runtime_plugin_enabled(config, plugin) and plugin.build_provider is not None:
        return plugin.build_provider(
            RuntimePluginContext(config=config, make_base_provider=make_base_provider)
        )
    return make_provider(config)


def make_runtime_plugin_hooks(config: Any) -> list[Any]:
    """Build all enabled runtime plugin hooks for the given config."""
    from nanobot.plugins import build_runtime_plugin_hooks

    return build_runtime_plugin_hooks(config, make_base_provider=make_base_provider)


def initialize_runtime_plugins(config: Any, *, loop: Any) -> list[Any]:
    """Initialize enabled runtime plugins against a constructed AgentLoop."""
    from nanobot.plugins import initialize_runtime_plugins as _initialize

    return _initialize(config, loop=loop, make_base_provider=make_base_provider)
