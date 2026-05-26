import sys
from pathlib import Path

from nanobot.config.schema import Config

CUSTOM_PLUGINS = Path(__file__).resolve().parents[2] / "custom-plugins"
if str(CUSTOM_PLUGINS) not in sys.path:
    sys.path.insert(0, str(CUSTOM_PLUGINS))

from smartrouter.config import load_router_config_from_config


def test_smart_router_config_accepts_camel_case() -> None:
    config = Config.model_validate(
        {
            "smartRouter": {
                "enabled": True,
                "allowLocalTools": False,
                "mini": {"provider": "openrouter", "model": "openai/gpt-5.4-mini"},
                "full": {"provider": "openrouter", "model": "openai/gpt-5.4"},
            }
        }
    )

    assert config.smart_router.enabled is True
    assert config.smart_router.mini.model == "openai/gpt-5.4-mini"


def test_smart_router_config_dumps_camel_case() -> None:
    config = Config.model_validate(
        {
            "smart_router": {
                "enabled": True,
                "mini": {"provider": "openrouter", "model": "openai/gpt-5.4-mini"},
                "full": {"provider": "openrouter", "model": "openai/gpt-5.4"},
            }
        }
    )

    data = config.model_dump(mode="json", by_alias=True)
    assert data["plugins"]["smartrouter"]["mini"]["model"] == "openai/gpt-5.4-mini"


def test_smart_router_config_accepts_plugin_scoped_config() -> None:
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

    assert config.plugins.smartrouter.enabled is True
    assert config.smart_router.enabled is True
    assert config.smart_router.full.model == "openai/gpt-5.4"


def test_smart_router_config_accepts_local_hybrid_block() -> None:
    config = Config.model_validate(
        {
            "plugins": {
                "smartrouter": {
                    "enabled": True,
                    "local": {"provider": "vllm", "model": "LiquidAI/LFM2-24B-A2B-MLX-4bit"},
                    "mini": {"provider": "openrouter", "model": "openai/gpt-5.4-mini"},
                    "full": {"provider": "openrouter", "model": "openai/gpt-5.4"},
                    "localHybrid": {
                        "enabled": True,
                        "mode": "vision_first_text_writer",
                        "vision": {
                            "provider": "vllm",
                            "model": "mlx-community/Qwen3-VL-4B-Instruct-4bit",
                        },
                        "onVisionUnavailable": "error",
                    },
                }
            }
        }
    )

    assert config.plugins.smartrouter.local_hybrid.enabled is True
    assert config.plugins.smartrouter.local_hybrid.mode == "vision_first_text_writer"
    assert config.plugins.smartrouter.local_hybrid.vision.model == "mlx-community/Qwen3-VL-4B-Instruct-4bit"
    assert config.plugins.smartrouter.local_hybrid.on_vision_unavailable == "error"

    router_config = load_router_config_from_config(
        config,
        default_model="LiquidAI/LFM2-24B-A2B-MLX-4bit",
        default_provider="vllm",
    )

    assert router_config.local_hybrid.enabled is True
    assert router_config.local_hybrid.mode == "vision_first_text_writer"
    assert router_config.local_hybrid.vision.provider == "vllm"
    assert router_config.local_hybrid.vision.model == "mlx-community/Qwen3-VL-4B-Instruct-4bit"
    assert router_config.local_hybrid.on_vision_unavailable == "error"