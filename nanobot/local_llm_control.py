"""Local LLM runtime control helpers shared by WebUI and slash commands."""

from __future__ import annotations

import base64
import subprocess
import json
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_LOCAL_LLM_TARGET = "qwen36"
LOCAL_LLM_ENV_FILENAME = "local-llm.env"
DEFAULT_SCRIPT_PATH = "/Volumes/ExtData/Nanobot/infra/scripts/local-models/local-models.sh"

ALLOWED_ACTIONS = {"status", "start", "stop", "restart", "smoke", "use"}
ALLOWED_TARGETS = {"lfm2", "qwen35-base-mlx-4bit", "qwen36", "all"}
ALL_REJECTED_ACTIONS = {"start", "restart", "smoke", "use"}

_VISION_CHECK_TTL_SECONDS = 30.0
_VISION_CHECK_CACHE: dict[tuple[str, str], tuple[float, tuple[bool, bool, str]]] = {}
_VISION_PROBE_IMAGE_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sA"
    "AAAASUVORK5CYII="
)
_VISION_PROBE_IMAGE_BYTES = base64.b64decode(_VISION_PROBE_IMAGE_B64)
_VISION_PROBE_IMAGE_PATH = Path(tempfile.gettempdir()) / "nanobot-vision-probe.png"

LOCAL_LLM_TARGETS: dict[str, dict[str, str]] = {
    "lfm2": {
        "label": "LFM2",
        "provider": "llama.cpp",
        "runtime": "llama.cpp",
        "model": "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0",
        "api_base": "http://127.0.0.1:1242/v1",
        "launchd_label": "com.nanobot.local-model-lfm2",
    },
    "qwen36": {
        "label": "Qwen3.6",
        "provider": "vllm",
        "runtime": "mlx_vlm.server",
        "model": "mlx-community/Qwen3.6-35B-A3B-4bit",
        "api_base": "http://127.0.0.1:1246/v1",
        "launchd_label": "com.nanobot.local-model-qwen36",
    },
    "qwen35-base-mlx-4bit": {
        "label": "Qwen3.5 Base",
        "provider": "vllm",
        "runtime": "mlx_lm.server",
        "model": "mlx-community/Qwen3.5-27B-4bit",
        "api_base": "http://127.0.0.1:1248/v1",
        "launchd_label": "com.nanobot.local-model-qwen35-base-mlx-4bit",
    },
}

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class LocalLlmError(RuntimeError):
    """Raised when a local LLM control request is invalid or fails."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


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
    ) -> None:
        self.nanobot_home = Path(nanobot_home).expanduser() if nanobot_home is not None else Path.home() / ".nanobot"
        self.script_path = str(script_path)
        self.runner = runner or _default_runner

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
            targets.append({
                "name": name,
                "label": meta["label"],
                "provider": meta["provider"],
                "runtime": meta["runtime"],
                "model": meta["model"],
                "api_base": meta["api_base"],
                "launchd_label": meta["launchd_label"],
                "running": endpoint_ok,
                "endpoint_ok": endpoint_ok,
                "supports_vision": supports_vision,
                "vision_check_ok": vision_check_ok,
                "vision_check_message": vision_check_message,
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

        return {
            "default_target": default_target,
            "default_model": default_meta["model"],
            "default_api_base": default_meta["api_base"],
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


def default_controller() -> LocalLlmController:
    global _DEFAULT_CONTROLLER
    if _DEFAULT_CONTROLLER is None:
        _DEFAULT_CONTROLLER = LocalLlmController()
    return _DEFAULT_CONTROLLER
