"""Discovery and loading for Nanobot runtime plugins."""

from __future__ import annotations

import importlib
import sys
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from loguru import logger

from .types import RuntimePlugin, RuntimePluginContext, RuntimePluginRuntimeContext, RuntimePluginStatus


def custom_plugins_dir() -> Path:
    """Return the in-repo runtime plugin directory."""
    return Path(__file__).resolve().parents[2] / "custom-plugins"


def ensure_custom_plugins_path() -> Path:
    """Ensure the runtime plugin directory is importable."""
    plugins_dir = custom_plugins_dir()
    plugins_dir_str = str(plugins_dir)
    if plugins_dir.exists() and plugins_dir_str not in sys.path:
        sys.path.insert(0, plugins_dir_str)
    return plugins_dir


def _load_runtime_plugin_from_module(module_name: str) -> RuntimePlugin | None:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        logger.warning("Failed to import runtime plugin module '{}': {}", module_name, exc)
        return None

    register_plugin = getattr(module, "register_plugin", None)
    if not callable(register_plugin):
        logger.debug("Runtime plugin module '{}' has no register_plugin()", module_name)
        return None

    try:
        plugin = register_plugin()
    except Exception as exc:
        logger.warning("Failed to register runtime plugin '{}': {}", module_name, exc)
        return None

    if not isinstance(plugin, RuntimePlugin):
        logger.warning("Runtime plugin '{}' returned invalid plugin object", module_name)
        return None
    if not plugin.source:
        plugin.source = "custom"
    if not plugin.module_name:
        plugin.module_name = module_name
    return plugin


def discover_runtime_plugins() -> dict[str, RuntimePlugin]:
    """Discover runtime plugins from in-repo modules and Python entry points."""
    discovered: dict[str, RuntimePlugin] = {}

    plugins_dir = ensure_custom_plugins_path()
    if plugins_dir.exists():
        for child in sorted(plugins_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            plugin = _load_runtime_plugin_from_module(child.name)
            if plugin is not None:
                discovered[plugin.name] = plugin

    for ep in entry_points(group="nanobot.plugins"):
        try:
            plugin = ep.load()()
        except Exception as exc:
            logger.warning("Failed to load runtime plugin entry point '{}': {}", ep.name, exc)
            continue
        if isinstance(plugin, RuntimePlugin):
            if not plugin.source:
                plugin.source = "entry-point"
            if not plugin.module_name:
                plugin.module_name = ep.name
            discovered.setdefault(plugin.name, plugin)
        else:
            logger.warning("Runtime plugin entry point '{}' returned invalid plugin object", ep.name)

    return discovered


def load_runtime_plugin(name: str) -> RuntimePlugin:
    """Load a runtime plugin by name or raise an explicit error."""
    plugins = discover_runtime_plugins()
    plugin = plugins.get(name)
    if plugin is None:
        raise LookupError(f"Runtime plugin not found: {name}")
    return plugin


def is_runtime_plugin_enabled(config: Any, plugin: RuntimePlugin) -> bool:
    """Return whether a runtime plugin is enabled for the current config."""
    if plugin.is_enabled is not None:
        return bool(plugin.is_enabled(config))

    section = getattr(getattr(config, "plugins", None), plugin.name, None)
    if isinstance(section, dict):
        return bool(section.get("enabled", False))
    return bool(getattr(section, "enabled", False))


def describe_runtime_plugin_status(config: Any, plugin: RuntimePlugin) -> RuntimePluginStatus:
    """Return a human-readable runtime plugin status object."""
    context = RuntimePluginContext(
        config=config,
        make_base_provider=lambda *args, **kwargs: None,
    )
    if plugin.describe_status is not None:
        try:
            status = plugin.describe_status(context)
        except Exception as exc:
            return RuntimePluginStatus(
                name=plugin.name,
                description=plugin.description,
                enabled=False,
                source=plugin.source,
                module_name=plugin.module_name,
                reason=f"status error: {exc}",
            )
        status.name = status.name or plugin.name
        status.description = status.description or plugin.description
        status.source = status.source or plugin.source
        status.module_name = status.module_name or plugin.module_name
        return status

    return RuntimePluginStatus(
        name=plugin.name,
        description=plugin.description,
        enabled=is_runtime_plugin_enabled(config, plugin),
        source=plugin.source,
        module_name=plugin.module_name,
        config_path=f"plugins.{plugin.name}",
        reason="configured" if is_runtime_plugin_enabled(config, plugin) else "disabled",
    )


def describe_runtime_plugin_statuses(config: Any) -> list[RuntimePluginStatus]:
    """Return status rows for all discovered runtime plugins."""
    return [
        describe_runtime_plugin_status(config, plugin)
        for plugin in discover_runtime_plugins().values()
    ]


def build_runtime_plugin_hooks(
    config: Any,
    *,
    make_base_provider: Any,
) -> list[Any]:
    """Build all enabled runtime plugin hooks for the current config."""
    hooks: list[Any] = []
    context = None
    for plugin in discover_runtime_plugins().values():
        if not is_runtime_plugin_enabled(config, plugin):
            continue
        if plugin.build_hooks is None:
            continue
        if context is None:
            from .types import RuntimePluginContext

            context = RuntimePluginContext(
                config=config,
                make_base_provider=make_base_provider,
            )
        built_hooks = plugin.build_hooks(context) or []
        hooks.extend(built_hooks)
    return hooks


def build_runtime_plugin_model_targets(
    config: Any,
    *,
    make_base_provider: Any,
) -> dict[str, Any]:
    """Collect named model targets contributed by enabled runtime plugins."""
    targets: dict[str, Any] = {}
    context = None
    for plugin in discover_runtime_plugins().values():
        if not is_runtime_plugin_enabled(config, plugin):
            continue
        if plugin.build_model_targets is None:
            continue
        if context is None:
            context = RuntimePluginContext(
                config=config,
                make_base_provider=make_base_provider,
            )
        try:
            built_targets = plugin.build_model_targets(context) or {}
        except Exception as exc:
            logger.warning("Failed to build runtime plugin model targets for '{}': {}", plugin.name, exc)
            continue
        if not isinstance(built_targets, dict):
            logger.warning(
                "Runtime plugin '{}' returned invalid model target catalog",
                plugin.name,
            )
            continue
        for name, target in built_targets.items():
            if name not in targets:
                targets[name] = target
    return targets


def initialize_runtime_plugins(
    config: Any,
    *,
    loop: Any,
    make_base_provider: Any,
) -> list[RuntimePluginStatus]:
    """Register tools and run initialization for enabled runtime plugins."""
    statuses: list[RuntimePluginStatus] = []
    for plugin in discover_runtime_plugins().values():
        enabled = is_runtime_plugin_enabled(config, plugin)
        status = describe_runtime_plugin_status(config, plugin)
        if not enabled:
            statuses.append(status)
            continue

        runtime_context = RuntimePluginRuntimeContext(
            config=config,
            make_base_provider=make_base_provider,
            loop=loop,
        )
        try:
            if plugin.build_tools is not None:
                for tool in plugin.build_tools(runtime_context) or []:
                    loop.tools.register(tool)
                    status.registered_tools.append(tool.name)
            if plugin.initialize is not None:
                plugin.initialize(runtime_context)
            if not status.reason:
                status.reason = "initialized"
        except Exception as exc:
            status.reason = f"init error: {exc}"
        statuses.append(status)
    return statuses