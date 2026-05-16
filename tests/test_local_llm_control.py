from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from nanobot.local_llm_control import LocalLlmController, LocalLlmError


def test_status_defaults_to_qwen36_without_override(tmp_path: Path) -> None:
    controller = LocalLlmController(nanobot_home=tmp_path)

    payload = controller.status()

    assert payload["default_target"] == "qwen36"
    assert payload["default_model"] == "mlx-community/Qwen3.6-35B-A3B-4bit"
    assert payload["default_api_base"] == "http://127.0.0.1:1246/v1"
    rows = {row["name"]: row for row in payload["targets"]}
    assert rows["qwen36"]["is_default"] is True
    assert rows["lfm2"]["is_default"] is False


def test_status_reads_local_llm_override_file(tmp_path: Path) -> None:
    (tmp_path / "local-llm.env").write_text(
        "NANOBOT_LOCAL_LLM_TARGET=lfm2\n"
        "LOCAL_LLM_BASE_URL=http://127.0.0.1:1242/v1\n"
        "LOCAL_LLM_MODEL=LiquidAI/LFM2-24B-A2B-GGUF:Q4_0\n",
        encoding="utf-8",
    )
    controller = LocalLlmController(nanobot_home=tmp_path)

    payload = controller.status()

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
    assert payload["default_model"] == "LiquidAI/LFM2-24B-A2B-GGUF:Q4_0"
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
