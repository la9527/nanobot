"""Runtime plugin helpers for Nanobot.

This package hosts a minimal registry for non-channel plugins that extend
runtime behavior such as provider wrappers, hooks, tools, and runtime status.
"""

from .registry import (
    build_runtime_plugin_hooks,
    describe_runtime_plugin_status,
    describe_runtime_plugin_statuses,
    discover_runtime_plugins,
    initialize_runtime_plugins,
    load_runtime_plugin,
)
from .types import RuntimePlugin, RuntimePluginContext, RuntimePluginRuntimeContext, RuntimePluginStatus

__all__ = [
    "RuntimePlugin",
    "RuntimePluginContext",
    "RuntimePluginRuntimeContext",
    "RuntimePluginStatus",
    "build_runtime_plugin_hooks",
    "describe_runtime_plugin_status",
    "describe_runtime_plugin_statuses",
    "discover_runtime_plugins",
    "initialize_runtime_plugins",
    "load_runtime_plugin",
]