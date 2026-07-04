from nanobot.config.schema import Config


def test_plugins_config_accepts_unknown_plugin_keys() -> None:
    config = Config.model_validate(
        {
            "plugins": {
                "sample": {
                    "enabled": True,
                    "mode": "test",
                }
            }
        }
    )

    section = getattr(config.plugins, "sample", None)
    assert isinstance(section, dict)
    assert section["enabled"] is True
    assert section["mode"] == "test"


def test_plugins_config_dumps_camel_case() -> None:
    config = Config.model_validate(
        {
            "plugins": {
                "samplePlugin": {
                    "enabled": True,
                }
            }
        }
    )

    data = config.model_dump(mode="json", by_alias=True)
    assert data["plugins"]["samplePlugin"]["enabled"] is True