"""Local LLM runtime control helpers shared by WebUI and slash commands."""

from __future__ import annotations

import asyncio
import base64
import subprocess
import json
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from nanobot.vision_runtime_broker import VisionRuntimeBroker

DEFAULT_LOCAL_LLM_TARGET = "qwen36"
LOCAL_LLM_ENV_FILENAME = "local-llm.env"
DEFAULT_SCRIPT_PATH = "/Volumes/ExtData/Nanobot/infra/scripts/local-models/local-models.sh"

ALLOWED_ACTIONS = {"status", "start", "stop", "restart", "smoke", "use"}
ALLOWED_TARGETS = {"lfm2", "lfm25-8b-a1b", "qwen35-base-mlx-4bit", "qwen36", "qwen3-vl-4b", "qwen3-vl-8b", "lfm25-vl-1.6b", "gemma4-e4b-current", "all"}
ALL_REJECTED_ACTIONS = {"start", "restart", "smoke", "use"}

_VISION_CHECK_TTL_SECONDS = 30.0
_VISION_CHECK_CACHE: dict[tuple[str, str], tuple[float, tuple[bool, bool, str]]] = {}
_VISION_PROBE_IMAGE_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sA"
    "AAAASUVORK5CYII="
)
_VISION_PROBE_IMAGE_BYTES = base64.b64decode(_VISION_PROBE_IMAGE_B64)
_VISION_PROBE_IMAGE_PATH = Path(tempfile.gettempdir()) / "nanobot-vision-probe.png"
_VISION_RUNTIME_IDLE_TIMEOUT_SECONDS = 300.0
_VISION_RUNTIME_WARMUP_TIMEOUT_SECONDS = 90.0
_VISION_RUNTIME_POLL_INTERVAL_SECONDS = 1.0

LOCAL_LLM_TARGETS: dict[str, dict[str, str]] = {
    "lfm2": {
        "label": "LFM2",
        "provider": "rapid-mlx",
        "runtime": "rapid-mlx",
        "model": "LiquidAI/LFM2-24B-A2B-MLX-4bit",
        "api_base": "http://127.0.0.1:1242/v1",
        "launchd_label": "com.nanobot.local-model-lfm2",
        "role": "text",
        "recommendation": "default_text",
    },
    "lfm25-8b-a1b": {
        "label": "LFM2.5 8B A1B",
        "provider": "rapid-mlx",
        "runtime": "rapid-mlx",
        "model": "LiquidAI/LFM2.5-8B-A1B",
        "api_base": "http://127.0.0.1:1256/v1",
        "launchd_label": "com.nanobot.local-model-lfm25-8b-a1b",
        "role": "text",
        "recommendation": "text_fast_candidate",
    },
    "qwen36": {
        "label": "Qwen3.6",
        "provider": "vllm",
        "runtime": "mlx_vlm.server",
        "model": "mlx-community/Qwen3.6-35B-A3B-4bit",
        "api_base": "http://127.0.0.1:1246/v1",
        "launchd_label": "com.nanobot.local-model-qwen36",
        "role": "text",
        "recommendation": "general_text",
    },
    "qwen35-base-mlx-4bit": {
        "label": "Qwen3.5 9B",
        "provider": "vllm",
        "runtime": "mlx_lm.server",
        "model": "mlx-community/Qwen3.5-9B-MLX-4bit",
        "api_base": "http://127.0.0.1:1248/v1",
        "launchd_label": "com.nanobot.local-model-qwen35-base-mlx-4bit",
        "role": "text",
        "recommendation": "text_fallback",
    },
    "qwen3-vl-4b": {
        "label": "Qwen3-VL 4B",
        "provider": "rapid-mlx",
        "runtime": "rapid-mlx",
        "model": "mlx-community/Qwen3-VL-4B-Instruct-4bit",
        "api_base": "http://127.0.0.1:1252/v1",
        "launchd_label": "com.nanobot.local-model-qwen3-vl-4b",
        "role": "vision",
        "recommendation": "hybrid_vision_fast",
    },
    "qwen3-vl-8b": {
        "label": "Qwen3-VL 8B",
        "provider": "rapid-mlx",
        "runtime": "rapid-mlx",
        "model": "mlx-community/Qwen3-VL-8B-Instruct-4bit",
        "api_base": "http://127.0.0.1:1254/v1",
        "launchd_label": "com.nanobot.local-model-qwen3-vl-8b",
        "role": "vision",
        "recommendation": "hybrid_vision_quality",
    },
    "lfm25-vl-1.6b": {
        "label": "LFM2.5-VL 1.6B",
        "provider": "vllm",
        "runtime": "mlx_vlm.server",
        "model": "/Users/byoungyoungla/.nanobot/local-model-cache/liquidai-lfm25-vl-1_6b",
        "api_base": "http://127.0.0.1:1258/v1",
        "launchd_label": "com.nanobot.local-model-lfm25-vl-1.6b",
        "role": "vision",
        "recommendation": "vision_ocr_candidate",
    },
    "gemma4-e4b-current": {
        "label": "Gemma 4 E4B Current",
        "provider": "rapid-mlx",
        "runtime": "rapid-mlx 0.7.26",
        "model": "mlx-community/gemma-4-e4b-it-4bit",
        "api_base": "http://127.0.0.1:1264/v1",
        "launchd_label": "com.nanobot.local-model-gemma4-e4b-current",
        "role": "text",
        "recommendation": "default_text_fast",
    },
}

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class LocalLlmError(RuntimeError):
    """Raised when a local LLM control request is invalid or fails."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


class HybridVisionRuntimeManager:
    def __init__(
        self,
        *,
        broker: VisionRuntimeBroker | None = None,
        holder: str = "smart-router-local",
    ) -> None:
        self._broker = broker or default_vision_runtime_broker()
        self._holder = holder

    def _resolve_target(self, vision_model: str) -> tuple[str, dict[str, str]] | tuple[None, None]:
        target_name = _target_name_for_model(vision_model)
        if target_name is None:
            return None, None
        meta = LOCAL_LLM_TARGETS.get(target_name)
        if meta is None or meta.get("role") != "vision":
            return None, None
        return target_name, meta

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return _broker_snapshot()

    async def ensure_runtime_ready(self, vision_model: str) -> None:
        target_name, _meta = self._resolve_target(vision_model)
        if target_name is None:
            return
        await self._broker.acquire(target_name, self._holder)

    async def mark_used(self, vision_model: str) -> None:
        target_name, _meta = self._resolve_target(vision_model)
        if target_name is None:
            return
        await self._broker.mark_used(target_name, self._holder)

    async def release(self, vision_model: str) -> None:
        target_name, _meta = self._resolve_target(vision_model)
        if target_name is None:
            return
        await self._broker.release(target_name, self._holder)


def _default_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
    )


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _has_local_llm_override(values: dict[str, str]) -> bool:
    target = values.get("NANOBOT_LOCAL_LLM_TARGET", "").strip()
    model = values.get("LOCAL_LLM_MODEL", "").strip()
    api_base = values.get("LOCAL_LLM_BASE_URL", "").strip()
    return bool(target or model or api_base)


def _endpoint_ok(api_base: str) -> bool:
    try:
        with urlopen(f"{api_base.rstrip('/')}/models", timeout=1.5) as response:
            return 200 <= int(response.status) < 300
    except (OSError, URLError, ValueError):
        return False


def _normalize_vision_probe_message(body_text: str) -> str:
    lowered = body_text.lower()
    if "only 'text' content type is supported" in lowered:
        return "Only 'text' content type is supported."
    if "image input is not supported" in lowered:
        if "mmproj" in lowered:
            return "image input is not supported - hint: mmproj-backed multimodal model is required"
        return "image input is not supported"
    return body_text.strip() or "vision probe failed"


def _vision_probe_image_path() -> str:
    if not _VISION_PROBE_IMAGE_PATH.exists() or _VISION_PROBE_IMAGE_PATH.read_bytes() != _VISION_PROBE_IMAGE_BYTES:
        _VISION_PROBE_IMAGE_PATH.write_bytes(_VISION_PROBE_IMAGE_BYTES)
    return str(_VISION_PROBE_IMAGE_PATH)


def _target_name_for_model(model: str | None) -> str | None:
    normalized = str(model or "").strip()
    if not normalized:
        return None
    for name, meta in LOCAL_LLM_TARGETS.items():
        if normalized == meta["model"]:
            return name
    return None


def _load_smart_router_local_targets() -> tuple[str | None, str | None]:
    try:
        from nanobot.config.loader import load_config, resolve_config_env_vars

        config = load_config()
        try:
            config = resolve_config_env_vars(config)
        except ValueError:
            pass

        router = getattr(getattr(config, "plugins", None), "smartrouter", None)
        if router is None or not bool(getattr(router, "enabled", False)):
            return None, None

        local = getattr(router, "local", None)
        text_target = _target_name_for_model(getattr(local, "model", None))

        hybrid = getattr(router, "local_hybrid", None)
        if hybrid is None or not bool(getattr(hybrid, "enabled", False)):
            return text_target, None

        vision = getattr(hybrid, "vision", None)
        vision_target = _target_name_for_model(getattr(vision, "model", None))
        return text_target, vision_target
    except Exception:
        return None, None


_DEFAULT_VISION_RUNTIME_BROKER: VisionRuntimeBroker | None = None


def default_vision_runtime_broker() -> VisionRuntimeBroker:
    global _DEFAULT_VISION_RUNTIME_BROKER
    if _DEFAULT_VISION_RUNTIME_BROKER is None:
        from nanobot.vision_runtime_broker import VisionRuntimeBroker

        _DEFAULT_VISION_RUNTIME_BROKER = VisionRuntimeBroker(
            state_root=Path.home() / ".nanobot" / "state" / "vision-runtime-broker",
        )
    return _DEFAULT_VISION_RUNTIME_BROKER


def _broker_snapshot() -> dict[str, dict[str, Any]]:
    try:
        return default_vision_runtime_broker().snapshot()
    except Exception:
        return {}


def _smart_router_local_image_status(rows_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    text_target, vision_target = _load_smart_router_local_targets()
    payload = {
        "text_target": text_target,
        "vision_target": vision_target,
        "image_ready": False,
        "message": "smart-router-local image path unavailable",
        "mode": "unavailable",
        "vision_runtime_mode": None,
        "vision_runtime_running": False,
    }
    if not text_target:
        payload["message"] = "smart-router-local local tier is not configured"
        return payload

    text_row = rows_by_name.get(text_target)
    if text_row is None:
        payload["message"] = f"smart-router-local text target `{text_target}` is not present in local LLM status"
        return payload

    if text_row.get("supports_vision"):
        payload.update({
            "image_ready": True,
            "message": f"smart-router-local image path ready via direct local target `{text_target}`",
            "mode": "direct",
        })
        return payload

    if not vision_target:
        payload["message"] = f"smart-router-local text target `{text_target}` has no configured hybrid vision target"
        return payload

    vision_row = rows_by_name.get(vision_target)
    if vision_row is None:
        payload["message"] = f"smart-router-local hybrid vision target `{vision_target}` is not present in local LLM status"
    elif vision_row.get("running") and vision_row.get("supports_vision"):
        payload.update({
            "image_ready": True,
            "message": f"smart-router-local hybrid vision ready via `{vision_target}`",
            "mode": "hybrid",
            "vision_runtime_mode": vision_row.get("management_mode"),
            "vision_runtime_running": bool(vision_row.get("runtime_running") or vision_row.get("running")),
        })
    else:
        detail = str(vision_row.get("vision_check_message") or "endpoint unavailable").strip()
        payload["message"] = f"smart-router-local hybrid vision target `{vision_target}` unavailable: {detail}"
        payload["vision_runtime_mode"] = vision_row.get("management_mode")
        payload["vision_runtime_running"] = bool(vision_row.get("runtime_running") or vision_row.get("running"))

    text_row["hybrid_vision_target"] = vision_target
    text_row["hybrid_vision_ready"] = bool(payload["image_ready"] and payload["mode"] == "hybrid")
    text_row["hybrid_vision_check_message"] = payload["message"]
    return payload


def _probe_vision_capability(api_base: str, model: str) -> tuple[bool, bool, str]:
    cache_key = (api_base, model)
    now = time.monotonic()
    cached = _VISION_CHECK_CACHE.get(cache_key)
    if cached is not None and cached[0] > now:
        return cached[1]

    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Return exactly one JSON object."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": _vision_probe_image_path(),
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 32,
        }
    ).encode("utf-8")
    request = Request(
        f"{api_base.rstrip('/')}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=5) as response:
            result = (200 <= int(response.status) < 300, True, "vision probe passed")
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="ignore")
        result = (False, True, _normalize_vision_probe_message(body_text))
    except TimeoutError:
        result = (False, False, "vision probe timed out")
    except (OSError, URLError, ValueError):
        result = (False, False, "endpoint unavailable")

    _VISION_CHECK_CACHE[cache_key] = (now + _VISION_CHECK_TTL_SECONDS, result)
    return result


class LocalLlmController:
    """Small allowlisted wrapper around the local-models control script."""

    def __init__(
        self,
        *,
        nanobot_home: str | Path | None = None,
        script_path: str | Path = DEFAULT_SCRIPT_PATH,
        runner: Runner | None = None,
        runtime_manager: HybridVisionRuntimeManager | None = None,
    ) -> None:
        self.nanobot_home = Path(nanobot_home).expanduser() if nanobot_home is not None else Path.home() / ".nanobot"
        self.script_path = str(script_path)
        self.runner = runner or _default_runner
        self.runtime_manager = runtime_manager or default_hybrid_vision_runtime_manager()

    @property
    def local_llm_env_path(self) -> Path:
        return self.nanobot_home / LOCAL_LLM_ENV_FILENAME

    def _default_target_name(self) -> str:
        values = _parse_env_file(self.local_llm_env_path)
        target = values.get("NANOBOT_LOCAL_LLM_TARGET", "").strip()
        if target in LOCAL_LLM_TARGETS:
            return target
        model = values.get("LOCAL_LLM_MODEL", "").strip()
        api_base = values.get("LOCAL_LLM_BASE_URL", "").strip()
        for name, meta in LOCAL_LLM_TARGETS.items():
            if model and model == meta["model"]:
                return name
            if api_base and api_base == meta["api_base"]:
                return name
        return DEFAULT_LOCAL_LLM_TARGET

    def status(self) -> dict[str, Any]:
        values = _parse_env_file(self.local_llm_env_path)
        runtime_snapshot = self.runtime_manager.snapshot()
        broker_snapshot = _broker_snapshot()
        targets: list[dict[str, Any]] = []
        for name, meta in LOCAL_LLM_TARGETS.items():
            endpoint_ok = _endpoint_ok(meta["api_base"])
            supports_vision = False
            vision_check_ok = False
            vision_check_message = "endpoint unavailable"
            if endpoint_ok:
                supports_vision, vision_check_ok, vision_check_message = _probe_vision_capability(
                    meta["api_base"],
                    meta["model"],
                )
            runtime_state = runtime_snapshot.get(name, {})
            broker_state = broker_snapshot.get(name, {}) if meta.get("role") == "vision" else {}
            holder_names = sorted(broker_state.get("holders", {}).keys()) if broker_state else []
            targets.append({
                "name": name,
                "label": meta["label"],
                "provider": meta["provider"],
                "runtime": meta["runtime"],
                "model": meta["model"],
                "api_base": meta["api_base"],
                "launchd_label": meta["launchd_label"],
                "role": meta["role"],
                "recommendation": meta["recommendation"],
                "running": endpoint_ok,
                "endpoint_ok": endpoint_ok,
                "supports_vision": supports_vision,
                "vision_check_ok": vision_check_ok,
                "vision_check_message": vision_check_message,
                "management_mode": (
                    broker_state.get("management_mode", "broker")
                    if broker_state
                    else runtime_state.get("management_mode", "manual")
                ),
                "runtime_running": (
                    bool(broker_state.get("running", endpoint_ok))
                    if broker_state
                    else runtime_state.get("runtime_running", endpoint_ok)
                ),
                "runtime_warming_up": runtime_state.get("runtime_warming_up", False),
                "runtime_last_used_at": broker_state.get("last_used_at", runtime_state.get("runtime_last_used_at")),
                "runtime_idle_timeout_seconds": broker_state.get(
                    "idle_timeout_seconds",
                    runtime_state.get("runtime_idle_timeout_seconds"),
                ),
                "runtime_idle_deadline_at": broker_state.get(
                    "idle_deadline_at",
                    runtime_state.get("runtime_idle_deadline_at"),
                ),
                "runtime_stop_scheduled": broker_state.get(
                    "stop_scheduled",
                    runtime_state.get("runtime_stop_scheduled", False),
                ),
                "runtime_stop_remaining_seconds": runtime_state.get("runtime_stop_remaining_seconds"),
                "holder_count": int(broker_state.get("holder_count", 0)),
                "holders": holder_names,
                "is_default": False,
            })

        default_target = self._default_target_name()
        default_row = next((row for row in targets if row["name"] == default_target), None)
        running_targets = [row for row in targets if row["running"]]
        if default_row is None:
            default_target = DEFAULT_LOCAL_LLM_TARGET
        elif _has_local_llm_override(values) and not default_row["running"] and len(running_targets) == 1:
            default_target = str(running_targets[0]["name"])

        default_meta = LOCAL_LLM_TARGETS[default_target]
        for row in targets:
            row["is_default"] = row["name"] == default_target

        smart_router_local = _smart_router_local_image_status({row["name"]: row for row in targets})

        return {
            "default_target": default_target,
            "default_model": default_meta["model"],
            "default_api_base": default_meta["api_base"],
            "smart_router_local_text_target": smart_router_local["text_target"],
            "smart_router_local_vision_target": smart_router_local["vision_target"],
            "smart_router_local_image_ready": smart_router_local["image_ready"],
            "smart_router_local_image_mode": smart_router_local["mode"],
            "smart_router_local_image_message": smart_router_local["message"],
            "smart_router_local_vision_runtime_mode": smart_router_local["vision_runtime_mode"],
            "smart_router_local_vision_runtime_running": smart_router_local["vision_runtime_running"],
            "targets": targets,
        }

    def _validate_action(self, action: str, target: str) -> tuple[str, str]:
        action = action.strip().lower()
        target = target.strip().lower()
        if action not in ALLOWED_ACTIONS:
            raise LocalLlmError(f"unknown local LLM action: {action}")
        if target not in ALLOWED_TARGETS:
            raise LocalLlmError(f"unknown local LLM target: {target}")
        if target == "all" and action in ALL_REJECTED_ACTIONS:
            raise LocalLlmError(f"{action} all is not allowed")
        return action, target

    def run_action(self, action: str, target: str) -> dict[str, Any]:
        action, target = self._validate_action(action, target)
        result = self.runner([self.script_path, action, target])
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "local LLM action failed").strip()
            raise LocalLlmError(message, status=500)
        return {
            "ok": True,
            "action": action,
            "target": target,
            "message": (result.stdout or "").strip() or f"{action} {target} completed.",
            "requires_restart": action == "use",
        }


_DEFAULT_CONTROLLER: LocalLlmController | None = None
_DEFAULT_HYBRID_VISION_RUNTIME_MANAGER: HybridVisionRuntimeManager | None = None


def default_hybrid_vision_runtime_manager() -> HybridVisionRuntimeManager:
    global _DEFAULT_HYBRID_VISION_RUNTIME_MANAGER
    if _DEFAULT_HYBRID_VISION_RUNTIME_MANAGER is None:
        _DEFAULT_HYBRID_VISION_RUNTIME_MANAGER = HybridVisionRuntimeManager()
    return _DEFAULT_HYBRID_VISION_RUNTIME_MANAGER


def default_controller() -> LocalLlmController:
    global _DEFAULT_CONTROLLER
    if _DEFAULT_CONTROLLER is None:
        _DEFAULT_CONTROLLER = LocalLlmController()
    return _DEFAULT_CONTROLLER
