from nanobot.config.schema import Config
from nanobot.model_targets import ResolvedModelTarget, build_model_targets, get_active_model_target_name
from nanobot.plugins.types import RuntimePlugin


def test_build_model_targets_includes_named_provider_model_targets() -> None:
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "model": "vllm/default-model",
                    "provider": "vllm",
                    "modelSelection": {
                        "activeTarget": "fast-local",
                        "targets": {
                            "fast-local": {
                                "kind": "provider_model",
                                "provider": "vllm",
                                "model": "local/fast-model",
                            }
                        },
                    },
                }
            }
        }
    )

    targets = build_model_targets(config)

    assert "default" in targets
    assert "fast-local" in targets
    assert targets["fast-local"].provider == "vllm"
    assert targets["fast-local"].model == "local/fast-model"
    assert get_active_model_target_name(config) == "fast-local"


def test_build_model_targets_includes_smart_router_target_when_configured() -> None:
    config = Config.model_validate(
        {
            "plugins": {
                "smartrouter": {
                    "enabled": True,
                    "mini": {"provider": "openrouter", "model": "openai/gpt-5.4-mini"},
                    "full": {"provider": "openrouter", "model": "openai/gpt-5.4"},
                }
            }
        }
    )

    targets = build_model_targets(config)

    assert "smart-router" in targets
    assert targets["smart-router"].kind == "smart_router"


def test_build_model_targets_merges_plugin_contributed_targets(monkeypatch) -> None:
    plugin = RuntimePlugin(
        name="sample",
        description="Sample runtime plugin",
        source="custom",
        build_model_targets=lambda context: {
            "plugin-remote": ResolvedModelTarget(
                name="plugin-remote",
                kind="provider_model",
                provider="openrouter",
                model="openai/gpt-5.4",
                description="Plugin-provided remote target.",
            )
        },
    )
    monkeypatch.setattr(
        "nanobot.plugins.registry.discover_runtime_plugins",
        lambda: {"sample": plugin},
    )

    config = Config.model_validate({"plugins": {"sample": {"enabled": True}}})

    targets = build_model_targets(config)

    assert "plugin-remote" in targets
    assert targets["plugin-remote"].model == "openai/gpt-5.4"