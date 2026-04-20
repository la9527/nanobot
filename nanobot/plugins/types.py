"""Types for Nanobot runtime plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class RuntimePluginContext:
    """Context passed to runtime plugin builders."""

    config: Any
    make_base_provider: Callable[..., Any]


@dataclass(slots=True)
class RuntimePluginRuntimeContext(RuntimePluginContext):
    """Context passed to runtime plugin initialization hooks."""

    loop: Any


@dataclass(slots=True)
class RuntimePluginStatus:
    """Human-readable runtime plugin status for CLI and diagnostics."""

    name: str
    enabled: bool
    description: str = ""
    source: str = ""
    module_name: str = ""
    config_path: str = ""
    reason: str = ""
    registered_tools: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RuntimePlugin:
    """Minimal runtime plugin contract.

    The surface starts small on purpose. Plugins can contribute a provider
    builder today, and the contract can be extended later for hooks or tools.
    """

    name: str
    description: str = ""
    source: str = ""
    module_name: str = ""
    build_provider: Callable[[RuntimePluginContext], Any] | None = None
    build_hooks: Callable[[RuntimePluginContext], list[Any]] | None = None
    build_tools: Callable[[RuntimePluginRuntimeContext], list[Any]] | None = None
    initialize: Callable[[RuntimePluginRuntimeContext], None] | None = None
    describe_status: Callable[[RuntimePluginContext], RuntimePluginStatus] | None = None
    is_enabled: Callable[[Any], bool] | None = None