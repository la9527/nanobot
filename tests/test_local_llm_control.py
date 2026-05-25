from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.request import Request

import pytest

from nanobot.local_llm_control import LocalLlmController, LocalLlmError


def test_status_defaults_to_qwen36_without_override(tmp_path: Path) -> None:
    controller = LocalLlmController(nanobot_home=tmp_path)

    payload = controller.status()

    assert payload["default_target"] == "qwen36"
    assert payload["default_model"] == "mlx-community/Qwen3.6-35B-A3B-4bit"
    assert payload["default_api_base"] == "http://127.0.0.1:1246/v1"
    rows = {row["name"]: row for row in payload["targets"]}
    assert "qwen35-base-mlx-4bit" in rows
    assert "qwen3-vl-4b" in rows
    assert "qwen3-vl-8b" in rows
    assert rows["qwen36"]["runtime"] == "mlx_vlm.server"
    assert rows["qwen35-base-mlx-4bit"]["runtime"] == "mlx_lm.server"
    assert rows["qwen3-vl-4b"]["runtime"] == "rapid-mlx"
    assert rows["qwen3-vl-8b"]["runtime"] == "rapid-mlx"
    assert rows["qwen36"]["is_default"] is True
    assert rows["lfm2"]["is_default"] is False


def test_status_reads_local_llm_override_file(tmp_path: Path) -> None:
    (tmp_path / "local-llm.env").write_text(
        "NANOBOT_LOCAL_LLM_TARGET=lfm2\n"
        "LOCAL_LLM_BASE_URL=http://127.0.0.1:1242/v1\n"
        "LOCAL_LLM_MODEL=LiquidAI/LFM2-24B-A2B-MLX-4bit\n",
        encoding="utf-8",
    )
    controller = LocalLlmController(nanobot_home=tmp_path)

    from nanobot import local_llm_control

    original_endpoint_ok = local_llm_control._endpoint_ok
    local_llm_control._endpoint_ok = lambda api_base: False
    try:
        payload = controller.status()
    finally:
        local_llm_control._endpoint_ok = original_endpoint_ok

    assert payload["default_target"] == "lfm2"
    rows = {row["name"]: row for row in payload["targets"]}
    assert rows["lfm2"]["is_default"] is True
    assert rows["qwen36"]["is_default"] is False


def test_status_prefers_only_running_target_when_override_target_is_down(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "local-llm.env").write_text(
        "NANOBOT_LOCAL_LLM_TARGET=qwen36\n"
        "LOCAL_LLM_BASE_URL=http://127.0.0.1:1246/v1\n"
        "LOCAL_LLM_MODEL=mlx-community/Qwen3.6-35B-A3B-4bit\n",
        encoding="utf-8",
    )

    def fake_endpoint_ok(api_base: str) -> bool:
        return api_base == "http://127.0.0.1:1242/v1"

    monkeypatch.setattr("nanobot.local_llm_control._endpoint_ok", fake_endpoint_ok)
    controller = LocalLlmController(nanobot_home=tmp_path)

    payload = controller.status()

    assert payload["default_target"] == "lfm2"
    assert payload["default_model"] == "LiquidAI/LFM2-24B-A2B-MLX-4bit"
    rows = {row["name"]: row for row in payload["targets"]}
    assert rows["lfm2"]["running"] is True
    assert rows["lfm2"]["is_default"] is True
    assert rows["qwen36"]["running"] is False
    assert rows["qwen36"]["is_default"] is False


def test_use_action_calls_allowlisted_script_and_marks_restart(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout="Updated ~/.nanobot/local-llm.env for qwen36\n",
            stderr="",
        )

    controller = LocalLlmController(
        script_path="/tmp/local-models.sh",
        nanobot_home=tmp_path,
        runner=runner,
    )

    response = controller.run_action("use", "qwen36")

    assert calls == [["/tmp/local-models.sh", "use", "qwen36"]]
    assert response["ok"] is True
    assert response["action"] == "use"
    assert response["target"] == "qwen36"
    assert response["requires_restart"] is True


def test_rejects_unsafe_action_and_all_for_mutating_actions(tmp_path: Path) -> None:
    controller = LocalLlmController(nanobot_home=tmp_path)

    with pytest.raises(LocalLlmError):
        controller.run_action("shell", "qwen36")

    with pytest.raises(LocalLlmError):
        controller.run_action("start", "all")


def test_status_reports_vision_capability_for_running_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_endpoint_ok(api_base: str) -> bool:
        return api_base in {
            "http://127.0.0.1:1246/v1",
            "http://127.0.0.1:1248/v1",
        }

    def fake_vision_probe(api_base: str, model: str) -> tuple[bool, bool, str]:
        if api_base.endswith(":1246/v1"):
            return False, True, "Only 'text' content type is supported."
        if api_base.endswith(":1248/v1"):
            return True, True, "vision probe passed"
        return False, False, "endpoint unavailable"

    monkeypatch.setattr("nanobot.local_llm_control._endpoint_ok", fake_endpoint_ok)
    monkeypatch.setattr("nanobot.local_llm_control._probe_vision_capability", fake_vision_probe)
    controller = LocalLlmController(nanobot_home=tmp_path)

    payload = controller.status()

    rows = {row["name"]: row for row in payload["targets"]}
    assert rows["qwen36"]["supports_vision"] is False
    assert rows["qwen36"]["vision_check_ok"] is True
    assert rows["qwen36"]["vision_check_message"] == "Only 'text' content type is supported."
    assert rows["qwen35-base-mlx-4bit"]["supports_vision"] is True
    assert rows["qwen35-base-mlx-4bit"]["vision_check_ok"] is True
    assert rows["qwen35-base-mlx-4bit"]["vision_check_message"] == "vision probe passed"
    assert rows["lfm2"]["supports_vision"] is False
    assert rows["lfm2"]["vision_check_ok"] is False


def test_probe_vision_capability_reports_timeout_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot import local_llm_control

    local_llm_control._VISION_CHECK_CACHE.clear()

    def fake_urlopen(request: Request | str, timeout: float = 0.0):
        if isinstance(request, str):
            raise AssertionError("models endpoint should not be probed in this test")
        raise TimeoutError("timed out")

    monkeypatch.setattr(local_llm_control, "urlopen", fake_urlopen)

    supports_vision, vision_check_ok, vision_check_message = local_llm_control._probe_vision_capability(
        "http://127.0.0.1:1246/v1",
        "mlx-community/Qwen3.6-35B-A3B-4bit",
    )

    assert supports_vision is False
    assert vision_check_ok is False
    assert vision_check_message == "vision probe timed out"


def test_probe_vision_capability_uses_local_image_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot import local_llm_control

    local_llm_control._VISION_CHECK_CACHE.clear()
    monkeypatch.setattr(local_llm_control, "_vision_probe_image_path", lambda: "/tmp/nanobot-vision-probe.png")

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b"{}"

    seen: dict[str, object] = {}

    def fake_urlopen(request: Request | str, timeout: float = 0.0):
        if isinstance(request, str):
            raise AssertionError("models endpoint should not be probed in this test")
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response()

    monkeypatch.setattr(local_llm_control, "urlopen", fake_urlopen)

    supports_vision, vision_check_ok, vision_check_message = local_llm_control._probe_vision_capability(
        "http://127.0.0.1:1246/v1",
        "mlx-community/Qwen3.6-35B-A3B-4bit",
    )

    assert supports_vision is True
    assert vision_check_ok is True
    assert vision_check_message == "vision probe passed"
    payload = seen["payload"]
    assert payload["messages"][0]["content"][1]["image_url"]["url"] == "/tmp/nanobot-vision-probe.png"


def test_accepts_qwen35_target_now_supported(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    controller = LocalLlmController(
        script_path="/tmp/local-models.sh",
        nanobot_home=tmp_path,
        runner=runner,
    )

    response = controller.run_action("use", "qwen35-base-mlx-4bit")

    assert response["ok"] is True
    assert response["target"] == "qwen35-base-mlx-4bit"
    assert calls == [["/tmp/local-models.sh", "use", "qwen35-base-mlx-4bit"]]


def test_accepts_qwen3_vl_8b_target_now_supported(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    controller = LocalLlmController(
        script_path="/tmp/local-models.sh",
        nanobot_home=tmp_path,
        runner=runner,
    )

    response = controller.run_action("use", "qwen3-vl-8b")

    assert response["ok"] is True
    assert response["target"] == "qwen3-vl-8b"
    assert calls == [["/tmp/local-models.sh", "use", "qwen3-vl-8b"]]
