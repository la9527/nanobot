"""Runtime plugin helpers for Nanobot.

This package hosts a minimal registry for non-channel plugins that extend
runtime behavior such as provider wrappers and hooks.
"""

from .registry import discover_runtime_plugins, load_runtime_plugin
from .types import RuntimePlugin, RuntimePluginContext

__all__ = [
    "RuntimePlugin",
    "RuntimePluginContext",
    "discover_runtime_plugins",
    "load_runtime_plugin",
]