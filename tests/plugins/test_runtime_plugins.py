from nanobot.plugins import discover_runtime_plugins, load_runtime_plugin


def test_discover_runtime_plugins_includes_smart_router() -> None:
    plugins = discover_runtime_plugins()

    assert "smartrouter" in plugins
    assert plugins["smartrouter"].build_provider is not None


def test_load_runtime_plugin_returns_smart_router() -> None:
    plugin = load_runtime_plugin("smartrouter")

    assert plugin.name == "smartrouter"
    assert "router" in plugin.description.lower()