from nanobot.agent.hook import AgentHook
from nanobot.config.schema import Config
from nanobot.plugins import discover_runtime_plugins, load_runtime_plugin
from nanobot.plugins.registry import build_runtime_plugin_hooks, is_runtime_plugin_enabled
from nanobot.plugins.types import RuntimePlugin


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
    enabled = Config.model_validate({"smartRouter": {"enabled": True}})

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