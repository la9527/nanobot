from nanobot.plugins import RuntimePlugin, RuntimePluginContext

from .config import RouterConfig, load_router_config
from .smart_router_provider import SmartRouterProvider


def _build_provider(context: RuntimePluginContext):
	defaults = context.config.agents.defaults
	router_config = load_router_config(
		context.config.smart_router,
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


def register_plugin() -> RuntimePlugin:
	return RuntimePlugin(
		name="smartrouter",
		description="Rule-based local/mini/full provider router for Nanobot runtime",
		source="custom",
		build_provider=_build_provider,
		is_enabled=lambda config: bool(
			getattr(config, "smart_router", None) and config.smart_router.enabled
		),
	)


__all__ = [
	"RouterConfig",
	"SmartRouterProvider",
	"load_router_config",
	"register_plugin",
]