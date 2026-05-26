"""Named model target resolution for runtime selection and /model commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _live_local_target_status() -> dict[str, Any] | None:
    try:
        from nanobot.local_llm_control import default_controller

        status = default_controller().status()
    except Exception:
        return None

    default_name = status.get("default_target")
    rows = status.get("targets")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("name") == default_name or row.get("is_default"):
            return row
    return None


def _live_local_target_label(target: dict[str, Any]) -> str:
    label = target.get("label") or target.get("name") or target.get("model") or "Local LLM"
    return str(label).strip() or "Local LLM"


def _smart_router_local_description(config: Any, text_model: Any) -> str:
    text_model_text = str(text_model).strip() if text_model else "Local LLM"
    hybrid = getattr(config.plugins.smartrouter, "local_hybrid", None)
    hybrid_enabled = bool(getattr(hybrid, "enabled", False))
    vision = getattr(hybrid, "vision", None)
    vision_model = str(getattr(vision, "model", "")).strip() if vision is not None else ""
    if hybrid_enabled and vision_model:
        return (
            "smart-router forced local tier "
            f"(text: {text_model_text}; hybrid vision: {vision_model})"
        )
    return f"smart-router forced local tier ({text_model_text})"


def _sync_live_local_targets(config: Any, targets: dict[str, "ResolvedModelTarget"]) -> None:
    if "local-llm" not in targets:
        return

    live_target = _live_local_target_status()
    if live_target is None:
        return

    label = _live_local_target_label(live_target)
    provider = live_target.get("provider") or live_target.get("runtime")
    model = live_target.get("model")
    model_text = str(model).strip() if model else label

    local_target = targets.get("local-llm")
    if local_target is not None:
        if model:
            local_target.model = str(model)
        local_target.description = f"current local runtime ({model_text})"

    smart_router_local = targets.get(SMART_ROUTER_TARGET_NAMES["local"])
    if smart_router_local is not None:
        if model:
            smart_router_local.model = str(model)
        smart_router_local.description = _smart_router_local_description(config, model_text)


def _sync_live_local_router_config(config: Any) -> None:
    live_target = _live_local_target_status()
    if live_target is None:
        return

    model = live_target.get("model")
    if model:
        config.plugins.smartrouter.local.model = str(model)
        config.smart_router.local.model = str(model)


DEFAULT_MODEL_TARGET_NAME = "default"
SMART_ROUTER_TARGET_NAME = "smart-router"
SMART_ROUTER_TARGET_NAMES = {
    "auto": SMART_ROUTER_TARGET_NAME,
    "local": "smart-router-local",
    "mini": "smart-router-mini",
    "full": "smart-router-full",
}
SESSION_MODEL_TARGET_KEY = "model_target"


@dataclass(slots=True)
class ResolvedModelTarget:
    """A resolved model target that Nanobot can execute against."""

    name: str
    kind: str
    model: str | None = None
    provider: str | None = None
    description: str = ""
    display_name: str | None = None
    group: str | None = None
    smart_router_mode: str | None = None


def _smart_router_variant(
    *,
    name: str,
    mode: str,
    description: str,
    display_name: str,
    provider: str | None = None,
    model: str | None = None,
) -> ResolvedModelTarget:
    return ResolvedModelTarget(
        name=name,
        kind="smart_router",
        model=model,
        provider=provider,
        description=description,
        display_name=display_name,
        group="smart-router",
        smart_router_mode=mode,
    )


def _smart_router_variants(config: Any) -> dict[str, ResolvedModelTarget]:
    router = config.plugins.smartrouter
    return {
        SMART_ROUTER_TARGET_NAMES["auto"]: _smart_router_variant(
            name=SMART_ROUTER_TARGET_NAMES["auto"],
            mode="auto",
            display_name="Auto",
            description="smart-router automatic tier selection.",
        ),
        SMART_ROUTER_TARGET_NAMES["local"]: _smart_router_variant(
            name=SMART_ROUTER_TARGET_NAMES["local"],
            mode="local",
            provider=router.local.provider,
            model=router.local.model,
            display_name="Local",
            description=_smart_router_local_description(config, router.local.model),
        ),
        SMART_ROUTER_TARGET_NAMES["mini"]: _smart_router_variant(
            name=SMART_ROUTER_TARGET_NAMES["mini"],
            mode="mini",
            provider=router.mini.provider,
            model=router.mini.model,
            display_name="Mini",
            description=f"smart-router forced mini tier ({router.mini.model}).",
        ),
        SMART_ROUTER_TARGET_NAMES["full"]: _smart_router_variant(
            name=SMART_ROUTER_TARGET_NAMES["full"],
            mode="full",
            provider=router.full.provider,
            model=router.full.model,
            display_name="Full",
            description=f"smart-router forced full tier ({router.full.model}).",
        ),
    }


def _normalize_smart_router_targets(config: Any, targets: dict[str, ResolvedModelTarget]) -> None:
    for name, default_target in _smart_router_variants(config).items():
        current = targets.get(name)
        if current is None:
            targets[name] = default_target
            continue
        if current.kind != "smart_router":
            continue
        if not current.provider:
            current.provider = default_target.provider
        if not current.model:
            current.model = default_target.model
        if not current.display_name:
            current.display_name = default_target.display_name
        if not current.group:
            current.group = default_target.group
        if not current.smart_router_mode:
            current.smart_router_mode = default_target.smart_router_mode
        if name == SMART_ROUTER_TARGET_NAMES["local"]:
            current.description = _smart_router_local_description(config, current.model or default_target.model)
            continue
        if not current.description:
            current.description = default_target.description


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

    if config._router_has_values(config.plugins.smartrouter):
        _normalize_smart_router_targets(config, targets)

    _sync_live_local_targets(config, targets)

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
        _sync_live_local_router_config(updated)
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
        if target.smart_router_mode == "auto":
            base = "smart-router"
        else:
            provider = target.provider or "auto"
            model = target.model or "(inherit)"
            base = f"{provider} -> {model}"
    else:
        provider = target.provider or "auto"
        model = target.model or "(inherit)"
        base = f"{provider} -> {model}"
    if target.description:
        return f"{base} | {target.description}"
    return base