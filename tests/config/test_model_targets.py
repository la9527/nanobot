from nanobot.config.schema import Config
from nanobot.model_targets import (
    ResolvedModelTarget,
    apply_model_target,
    build_model_targets,
    get_active_model_target_name,
)
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
                    "local": {"provider": "vllm", "model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0"},
                    "mini": {"provider": "openrouter", "model": "openai/gpt-5.4-mini"},
                    "full": {"provider": "openrouter", "model": "openai/gpt-5.4"},
                }
            }
        }
    )

    targets = build_model_targets(config)

    assert "smart-router" in targets
    assert "smart-router-local" in targets
    assert "smart-router-mini" in targets
    assert "smart-router-full" in targets
    assert targets["smart-router"].kind == "smart_router"
    assert targets["smart-router"].smart_router_mode == "auto"
    assert targets["smart-router-local"].kind == "smart_router"
    assert targets["smart-router-local"].smart_router_mode == "local"
    assert targets["smart-router-local"].provider == "vllm"
    assert targets["smart-router-local"].model == "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0"
    assert "LiquidAI/LFM2" in targets["smart-router-local"].description
    assert targets["smart-router-mini"].smart_router_mode == "mini"
    assert targets["smart-router-mini"].provider == "openrouter"
    assert targets["smart-router-mini"].model == "openai/gpt-5.4-mini"
    assert targets["smart-router-full"].display_name == "Full"


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


def test_build_model_targets_prefers_live_local_llm_status_for_local_targets(
    monkeypatch,
) -> None:
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "model": "mlx-community/Qwen3.6-35B-A3B-4bit",
                    "provider": "vllm",
                    "modelSelection": {
                        "targets": {
                            "local-llm": {
                                "kind": "provider_model",
                                "provider": "vllm",
                                "model": "mlx-community/Qwen3.6-35B-A3B-4bit",
                                "description": "current local runtime (mlx-community/Qwen3.6-35B-A3B-4bit)",
                            }
                        },
                    },
                }
            },
            "plugins": {
                "smartrouter": {
                    "enabled": True,
                    "local": {"provider": "vllm", "model": "mlx-community/Qwen3.6-35B-A3B-4bit"},
                    "mini": {"provider": "openrouter", "model": "openai/gpt-5.4-mini"},
                    "full": {"provider": "openrouter", "model": "openai/gpt-5.4"},
                }
            },
        }
    )
    monkeypatch.setattr(
        "nanobot.local_llm_control.default_controller",
        lambda: type(
            "_Controller",
            (),
            {
                "status": staticmethod(
                    lambda: {
                        "default_target": "lfm2",
                        "default_model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
                        "default_api_base": "http://127.0.0.1:1242/v1",
                        "targets": [
                            {
                                "name": "lfm2",
                                "label": "LFM2",
                                "runtime": "llama.cpp",
                                "model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
                                "api_base": "http://127.0.0.1:1242/v1",
                                "launchd_label": "com.nanobot.local-model-lfm2",
                                "running": True,
                                "endpoint_ok": True,
                                "is_default": True,
                            }
                        ],
                    }
                )
            },
        )(),
    )

    targets = build_model_targets(config)

    assert targets["local-llm"].model == "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0"
    assert targets["local-llm"].description == "current local runtime (LiquidAI/LFM2-24B-A2B-GGUF:Q4_0)"
    assert targets["smart-router-local"].provider == "vllm"
    assert targets["smart-router-local"].model == "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0"
    assert targets["smart-router-local"].description == "smart-router forced local tier (LiquidAI/LFM2-24B-A2B-GGUF:Q4_0)"


def test_apply_model_target_updates_smart_router_local_tier_from_live_local_status(
    monkeypatch,
) -> None:
    config = Config.model_validate(
        {
            "agents": {"defaults": {"model": "mlx-community/Qwen3.6-35B-A3B-4bit", "provider": "vllm"}},
            "plugins": {
                "smartrouter": {
                    "enabled": True,
                    "local": {"provider": "vllm", "model": "mlx-community/Qwen3.6-35B-A3B-4bit"},
                    "mini": {"provider": "openrouter", "model": "openai/gpt-5.4-mini"},
                    "full": {"provider": "openrouter", "model": "openai/gpt-5.4"},
                }
            },
        }
    )
    monkeypatch.setattr(
        "nanobot.local_llm_control.default_controller",
        lambda: type(
            "_Controller",
            (),
            {
                "status": staticmethod(
                    lambda: {
                        "default_target": "lfm2",
                        "default_model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
                        "default_api_base": "http://127.0.0.1:1242/v1",
                        "targets": [
                            {
                                "name": "lfm2",
                                "label": "LFM2",
                                "runtime": "llama.cpp",
                                "model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
                                "api_base": "http://127.0.0.1:1242/v1",
                                "launchd_label": "com.nanobot.local-model-lfm2",
                                "running": True,
                                "endpoint_ok": True,
                                "is_default": True,
                            }
                        ],
                    }
                )
            },
        )(),
    )

    updated = apply_model_target(config, build_model_targets(config)["smart-router-local"])

    assert updated.plugins.smartrouter.local.provider == "llama.cpp"
    assert updated.plugins.smartrouter.local.model == "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0"
    assert updated.smart_router.local.provider == "llama.cpp"
    assert updated.smart_router.local.model == "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0"