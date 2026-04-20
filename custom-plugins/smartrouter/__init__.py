from nanobot.plugins import RuntimePlugin, RuntimePluginContext, RuntimePluginStatus

from .config import RouterConfig, load_router_config_from_config, resolve_router_section
from .smart_router_provider import SmartRouterProvider


def _build_provider(context: RuntimePluginContext):
	defaults = context.config.agents.defaults
	router_config = load_router_config_from_config(
		context.config,
		default_model=defaults.model,
		default_provider=None if defaults.provider == "auto" else defaults.provider,
	)
	tier_providers = {
		"local": context.make_base_provider(
			context.config,
			model=router_config.local.model,
			provider_name=router_config.local.provider,
		),
		"mini": context.make_base_provider(
			context.config,
			model=router_config.mini.model,
			provider_name=router_config.mini.provider,
		),
		"full": context.make_base_provider(
			context.config,
			model=router_config.full.model,
			provider_name=router_config.full.provider,
		),
	}
	provider = SmartRouterProvider(
		router_config=router_config,
		tier_providers=tier_providers,
		default_model=defaults.model,
	)
	provider.generation = tier_providers["local"].generation
	return provider


def _describe_status(context: RuntimePluginContext) -> RuntimePluginStatus:
	section, source = resolve_router_section(context.config)
	enabled = bool(getattr(section, "enabled", False)) if section is not None else False
	log_path = None
	if section is not None:
		logging_cfg = getattr(section, "logging", None)
		log_path = getattr(logging_cfg, "path", None)
	return RuntimePluginStatus(
		name="smartrouter",
		description="Rule-based local/mini/full provider router for Nanobot runtime",
		enabled=enabled,
		source="custom",
		module_name="smartrouter",
		config_path=source,
		reason=(f"log={log_path}" if log_path else "configured"),
	)


def register_plugin() -> RuntimePlugin:
	return RuntimePlugin(
		name="smartrouter",
		description="Rule-based local/mini/full provider router for Nanobot runtime",
		source="custom",
		build_provider=_build_provider,
		describe_status=_describe_status,
		is_enabled=lambda config: bool(
			getattr(getattr(config, "plugins", None), "smartrouter", None)
			and config.plugins.smartrouter.enabled
		),
	)


__all__ = [
	"RouterConfig",
	"SmartRouterProvider",
	"load_router_config",
	"register_plugin",
]