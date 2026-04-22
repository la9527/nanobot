from typing import Any

from nanobot.agent.hook import AgentHook
from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.config.schema import Config
from nanobot.plugins import discover_runtime_plugins, load_runtime_plugin
from nanobot.plugins.registry import (
    build_runtime_plugin_model_targets,
    build_runtime_plugin_hooks,
    describe_runtime_plugin_status,
    initialize_runtime_plugins,
    is_runtime_plugin_enabled,
)
from nanobot.plugins.types import RuntimePlugin
from nanobot.model_targets import ResolvedModelTarget


def test_discover_runtime_plugins_includes_smart_router() -> None:
    plugins = discover_runtime_plugins()

    assert "smartrouter" in plugins
    assert plugins["smartrouter"].build_provider is not None


def test_load_runtime_plugin_returns_smart_router() -> None:
    plugin = load_runtime_plugin("smartrouter")

    assert plugin.name == "smartrouter"
    assert "router" in plugin.description.lower()


def test_runtime_plugin_enabled_uses_smart_router_config() -> None:
    plugin = load_runtime_plugin("smartrouter")

    disabled = Config()
    enabled = Config.model_validate({"plugins": {"smartrouter": {"enabled": True}}})

    assert is_runtime_plugin_enabled(disabled, plugin) is False
    assert is_runtime_plugin_enabled(enabled, plugin) is True


def test_runtime_plugin_records_source() -> None:
    plugin = load_runtime_plugin("smartrouter")

    assert plugin.source == "custom"


def test_build_runtime_plugin_hooks_collects_enabled_plugin_hooks(monkeypatch) -> None:
    class _FakeHook(AgentHook):
        pass

    hook = _FakeHook()
    plugin = RuntimePlugin(
        name="sample",
        description="Sample runtime plugin",
        source="custom",
        build_hooks=lambda context: [hook],
    )
    monkeypatch.setattr(
        "nanobot.plugins.registry.discover_runtime_plugins",
        lambda: {"sample": plugin},
    )

    config = Config.model_validate({"plugins": {"sample": {"enabled": True}}})
    hooks = build_runtime_plugin_hooks(config, make_base_provider=lambda *args, **kwargs: None)

    assert hooks == [hook]


def test_build_runtime_plugin_hooks_skips_disabled_plugins(monkeypatch) -> None:
    plugin = RuntimePlugin(
        name="sample",
        description="Sample runtime plugin",
        source="custom",
        build_hooks=lambda context: [AgentHook()],
    )
    monkeypatch.setattr(
        "nanobot.plugins.registry.discover_runtime_plugins",
        lambda: {"sample": plugin},
    )

    hooks = build_runtime_plugin_hooks(Config(), make_base_provider=lambda *args, **kwargs: None)

    assert hooks == []


def test_build_runtime_plugin_model_targets_collects_enabled_targets(monkeypatch) -> None:
    plugin = RuntimePlugin(
        name="sample",
        description="Sample runtime plugin",
        source="custom",
        build_model_targets=lambda context: {
            "sample-remote": ResolvedModelTarget(
                name="sample-remote",
                kind="provider_model",
                provider="openrouter",
                model="openai/gpt-5.4-mini",
            )
        },
    )
    monkeypatch.setattr(
        "nanobot.plugins.registry.discover_runtime_plugins",
        lambda: {"sample": plugin},
    )

    config = Config.model_validate({"plugins": {"sample": {"enabled": True}}})
    targets = build_runtime_plugin_model_targets(
        config,
        make_base_provider=lambda *args, **kwargs: None,
    )

    assert list(targets) == ["sample-remote"]
    assert targets["sample-remote"].provider == "openrouter"


def test_describe_runtime_plugin_status_reports_plugin_config_path() -> None:
    plugin = load_runtime_plugin("smartrouter")
    config = Config.model_validate({"plugins": {"smartrouter": {"enabled": True}}})

    status = describe_runtime_plugin_status(config, plugin)

    assert status.enabled is True
    assert status.config_path == "plugins.smartrouter"


def test_initialize_runtime_plugins_registers_tools(monkeypatch) -> None:
    class _SampleTool(Tool):
        @property
        def name(self) -> str:
            return "sample_tool"

        @property
        def description(self) -> str:
            return "Sample tool"

        @property
        def parameters(self) -> dict[str, Any]:
            return {"type": "object", "properties": {}}

        async def execute(self, **kwargs: Any) -> Any:
            return "ok"

    plugin = RuntimePlugin(
        name="sample",
        description="Sample runtime plugin",
        source="custom",
        build_tools=lambda context: [_SampleTool()],
    )
    monkeypatch.setattr(
        "nanobot.plugins.registry.discover_runtime_plugins",
        lambda: {"sample": plugin},
    )

    class _Loop:
        def __init__(self) -> None:
            self.tools = ToolRegistry()

    loop = _Loop()
    config = Config.model_validate({"plugins": {"sample": {"enabled": True}}})
    statuses = initialize_runtime_plugins(config, loop=loop, make_base_provider=lambda *args, **kwargs: None)

    assert statuses[0].registered_tools == ["sample_tool"]
    assert loop.tools.has("sample_tool")