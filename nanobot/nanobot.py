"""High-level programmatic interface to nanobot."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nanobot.agent.hook import AgentHook
from nanobot.agent.loop import AgentLoop
from nanobot.bus.queue import MessageBus


@dataclass(slots=True)
class RunResult:
    """Result of a single agent run."""

    content: str
    tools_used: list[str]
    messages: list[dict[str, Any]]


class Nanobot:
    """Programmatic facade for running the nanobot agent.

    Usage::

        bot = Nanobot.from_config()
        result = await bot.run("Summarize this repo", hooks=[MyHook()])
        print(result.content)
    """

    def __init__(self, loop: AgentLoop) -> None:
        self._loop = loop

    @classmethod
    def from_config(
        cls,
        config_path: str | Path | None = None,
        *,
        workspace: str | Path | None = None,
    ) -> Nanobot:
        """Create a Nanobot instance from a config file.

        Args:
            config_path: Path to ``config.json``.  Defaults to
                ``~/.nanobot/config.json``.
            workspace: Override the workspace directory from config.
        """
        from nanobot.config.loader import load_config, resolve_config_env_vars
        from nanobot.config.schema import Config
        from nanobot.plugins import build_runtime_plugin_hooks, initialize_runtime_plugins

        resolved: Path | None = None
        if config_path is not None:
            resolved = Path(config_path).expanduser().resolve()
            if not resolved.exists():
                raise FileNotFoundError(f"Config not found: {resolved}")

        config: Config = resolve_config_env_vars(load_config(resolved))
        if workspace is not None:
            config.agents.defaults.workspace = str(
                Path(workspace).expanduser().resolve()
            )

        provider = _make_provider(config)
        runtime_hooks = build_runtime_plugin_hooks(
            config,
            make_base_provider=_make_base_provider,
        )
        bus = MessageBus()
        defaults = config.agents.defaults

        loop = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=config.workspace_path,
            model=defaults.model,
            runtime_config=config,
            make_provider=_make_provider,
            max_iterations=defaults.max_tool_iterations,
            context_window_tokens=defaults.context_window_tokens,
            context_block_limit=defaults.context_block_limit,
            max_tool_result_chars=defaults.max_tool_result_chars,
            provider_retry_mode=defaults.provider_retry_mode,
            web_config=config.tools.web,
            exec_config=config.tools.exec,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            mcp_servers=config.tools.mcp_servers,
            timezone=defaults.timezone,
            unified_session=defaults.unified_session,
            disabled_skills=defaults.disabled_skills,
            session_ttl_minutes=defaults.session_ttl_minutes,
            hooks=runtime_hooks,
            tools_config=config.tools,
        )
        initialize_runtime_plugins(
            config,
            loop=loop,
            make_base_provider=_make_base_provider,
        )
        return cls(loop)

    async def run(
        self,
        message: str,
        *,
        session_key: str = "sdk:default",
        hooks: list[AgentHook] | None = None,
    ) -> RunResult:
        """Run the agent once and return the result.

        Args:
            message: The user message to process.
            session_key: Session identifier for conversation isolation.
                Different keys get independent history.
            hooks: Optional lifecycle hooks for this run.
        """
        prev = self._loop._extra_hooks
        if hooks is not None:
            self._loop._extra_hooks = list(hooks)
        try:
            response = await self._loop.process_direct(
                message, session_key=session_key,
            )
        finally:
            self._loop._extra_hooks = prev

        content = (response.content if response else None) or ""
        return RunResult(content=content, tools_used=[], messages=[])


def _make_provider(config: Any) -> Any:
    """Create the LLM provider from config (extracted from CLI)."""
    from nanobot.plugins import load_runtime_plugin
    from nanobot.plugins.registry import is_runtime_plugin_enabled

    plugin = load_runtime_plugin("smartrouter")
    if is_runtime_plugin_enabled(config, plugin):
        return _make_smart_router_provider(config)
    return _make_base_provider(config)


def _resolve_provider_config(config: Any, provider_name: str | None) -> Any:
    if not provider_name:
        return None
    normalized = provider_name.replace("-", "_")
    return getattr(config.providers, normalized, None)


def _resolve_api_base(config: Any, provider_name: str | None, model: str) -> str | None:
    from nanobot.providers.registry import find_by_name

    if provider_name is None:
        return config.get_api_base(model)

    p = _resolve_provider_config(config, provider_name)
    if p and p.api_base:
        return p.api_base

    spec = find_by_name(provider_name)
    if spec and (spec.is_gateway or spec.is_local) and spec.default_api_base:
        return spec.default_api_base
    return None


def _make_base_provider(
    config: Any,
    *,
    model: str | None = None,
    provider_name: str | None = None,
) -> Any:
    """Create a concrete provider for a specific provider/model target."""
    from nanobot.providers.base import GenerationSettings
    from nanobot.providers.registry import find_by_name

    selected_model = model or config.agents.defaults.model
    explicit_provider = provider_name
    if explicit_provider is None and model is None and config.agents.defaults.provider != "auto":
        explicit_provider = config.agents.defaults.provider

    resolved_provider_name = explicit_provider or config.get_provider_name(selected_model)
    p = _resolve_provider_config(config, resolved_provider_name)
    if p is None and explicit_provider is None:
        p = config.get_provider(selected_model)
    spec = find_by_name(resolved_provider_name) if resolved_provider_name else None
    backend = spec.backend if spec else "openai_compat"

    if backend == "azure_openai":
        if not p or not p.api_key or not p.api_base:
            raise ValueError("Azure OpenAI requires api_key and api_base in config.")
    elif backend == "openai_compat" and not selected_model.startswith("bedrock/"):
        needs_key = not (p and p.api_key)
        exempt = spec and (spec.is_oauth or spec.is_local or spec.is_direct)
        if needs_key and not exempt:
            raise ValueError(
                f"No API key configured for provider '{resolved_provider_name}'."
            )

    if backend == "openai_codex":
        from nanobot.providers.openai_codex_provider import OpenAICodexProvider

        provider = OpenAICodexProvider(default_model=selected_model)
    elif backend == "github_copilot":
        from nanobot.providers.github_copilot_provider import GitHubCopilotProvider

        provider = GitHubCopilotProvider(default_model=selected_model)
    elif backend == "azure_openai":
        from nanobot.providers.azure_openai_provider import AzureOpenAIProvider

        provider = AzureOpenAIProvider(
            api_key=p.api_key, api_base=p.api_base, default_model=selected_model
        )
    elif backend == "anthropic":
        from nanobot.providers.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(
            api_key=p.api_key if p else None,
            api_base=_resolve_api_base(config, resolved_provider_name, selected_model),
            default_model=selected_model,
            extra_headers=p.extra_headers if p else None,
        )
    else:
        from nanobot.providers.openai_compat_provider import OpenAICompatProvider

        provider = OpenAICompatProvider(
            api_key=p.api_key if p else None,
            api_base=_resolve_api_base(config, resolved_provider_name, selected_model),
            default_model=selected_model,
            extra_headers=p.extra_headers if p else None,
            spec=spec,
        )

    defaults = config.agents.defaults
    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
    return provider


def _make_smart_router_provider(config: Any) -> Any:
    """Create the smart-router wrapper provider."""
    from nanobot.plugins import RuntimePluginContext, load_runtime_plugin

    plugin = load_runtime_plugin("smartrouter")
    if plugin.build_provider is None:
        raise ValueError("smartrouter plugin does not expose a provider builder")
    return plugin.build_provider(
        RuntimePluginContext(
            config=config,
            make_base_provider=_make_base_provider,
        )
    )
