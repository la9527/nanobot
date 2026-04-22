"""Named model target resolution for runtime selection and /model commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_MODEL_TARGET_NAME = "default"
SMART_ROUTER_TARGET_NAME = "smart-router"
SESSION_MODEL_TARGET_KEY = "model_target"


@dataclass(slots=True)
class ResolvedModelTarget:
    """A resolved model target that Nanobot can execute against."""

    name: str
    kind: str
    model: str | None = None
    provider: str | None = None
    description: str = ""


def _default_target(config: Any) -> ResolvedModelTarget:
    defaults = config.agents.defaults
    if config.plugins.smartrouter.enabled:
        return ResolvedModelTarget(
            name=DEFAULT_MODEL_TARGET_NAME,
            kind="smart_router",
            description="Startup default via smart-router.",
        )
    return ResolvedModelTarget(
        name=DEFAULT_MODEL_TARGET_NAME,
        kind="provider_model",
        provider=None if defaults.provider == "auto" else defaults.provider,
        model=defaults.model,
        description="Startup default provider/model.",
    )


def build_model_targets(config: Any) -> dict[str, ResolvedModelTarget]:
    """Build named model targets from config plus useful built-ins."""
    targets: dict[str, ResolvedModelTarget] = {
        DEFAULT_MODEL_TARGET_NAME: _default_target(config),
    }

    from nanobot.plugins import build_runtime_plugin_model_targets

    plugin_targets = build_runtime_plugin_model_targets(
        config,
        make_base_provider=lambda *args, **kwargs: None,
    )
    for name, target in plugin_targets.items():
        if name in targets or not isinstance(target, ResolvedModelTarget):
            continue
        targets[name] = target

    selection = getattr(config.agents.defaults, "model_selection", None)
    configured_targets = getattr(selection, "targets", {}) if selection is not None else {}
    for name, target in configured_targets.items():
        targets[name] = ResolvedModelTarget(
            name=name,
            kind=target.kind,
            provider=target.provider,
            model=target.model,
            description=target.description or "",
        )

    if SMART_ROUTER_TARGET_NAME not in targets and config._router_has_values(config.plugins.smartrouter):
        targets[SMART_ROUTER_TARGET_NAME] = ResolvedModelTarget(
            name=SMART_ROUTER_TARGET_NAME,
            kind="smart_router",
            description="smart-router runtime plugin target.",
        )

    return targets


def resolve_model_target(config: Any, name: str | None) -> ResolvedModelTarget:
    """Resolve a named target, falling back to the default target."""
    targets = build_model_targets(config)
    if not name:
        return targets[DEFAULT_MODEL_TARGET_NAME]
    resolved = targets.get(name)
    if resolved is None:
        raise KeyError(name)
    return resolved


def get_active_model_target_name(config: Any, session: Any | None = None) -> str:
    """Return the active target name for a session or the global default."""
    if session is not None:
        selected = session.metadata.get(SESSION_MODEL_TARGET_KEY)
        if isinstance(selected, str) and selected:
            return selected
    selection = getattr(config.agents.defaults, "model_selection", None)
    configured_active = getattr(selection, "active_target", None) if selection is not None else None
    if configured_active:
        return configured_active
    return DEFAULT_MODEL_TARGET_NAME


def apply_model_target(config: Any, target: ResolvedModelTarget) -> Any:
    """Return a config copy adjusted to execute the requested model target."""
    updated = config.model_copy(deep=True)
    if target.kind == "smart_router":
        updated.plugins.smartrouter.enabled = True
        updated.smart_router = updated.plugins.smartrouter.model_copy(deep=True)
        return updated

    updated.plugins.smartrouter.enabled = False
    updated.smart_router.enabled = False
    if target.provider:
        updated.agents.defaults.provider = target.provider
    else:
        updated.agents.defaults.provider = "auto"
    if target.model:
        updated.agents.defaults.model = target.model
    return updated


def describe_model_target(target: ResolvedModelTarget) -> str:
    """Return a short human-readable description for a target."""
    if target.kind == "smart_router":
        base = "smart-router"
    else:
        provider = target.provider or "auto"
        model = target.model or "(inherit)"
        base = f"{provider} -> {model}"
    if target.description:
        return f"{base} | {target.description}"
    return base