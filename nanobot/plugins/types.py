"""Types for Nanobot runtime plugins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class RuntimePluginContext:
    """Context passed to runtime plugin builders."""

    config: Any
    make_base_provider: Callable[..., Any]


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
    is_enabled: Callable[[Any], bool] | None = None