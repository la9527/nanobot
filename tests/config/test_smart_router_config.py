from nanobot.config.schema import Config


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
    assert data["smartRouter"]["mini"]["model"] == "openai/gpt-5.4-mini"