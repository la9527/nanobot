"""Discovery and loading for Nanobot runtime plugins."""

from __future__ import annotations

import importlib
import sys
from importlib.metadata import entry_points
from pathlib import Path

from loguru import logger

from .types import RuntimePlugin


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