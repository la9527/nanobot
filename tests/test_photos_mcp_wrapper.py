from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


def test_run_photos_mcp_app_dry_run_reports_shared_bundle_and_legacy_servers() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/run-photos-mcp-app.sh"

    env = os.environ.copy()
    env["PHOTOS_MCP_DRY_RUN"] = "1"

    proc = subprocess.run(
        ["/bin/zsh", str(script_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["app_name"] == "PhotosMcp"
    assert payload["bundle_id"] == "com.nanobot.photos-mcp"
    assert payload["legacy_servers"] == ["photo-source", "photo-ranker"]
    assert payload["photos_mcp_home"].endswith("/.photos-mcp")
    assert payload["photos_mcp_runtime_root"].endswith("/.photos-mcp/runtime")
    assert payload["photos_mcp_cache_root"].endswith("/.photos-mcp/cache")
    assert payload["photo_ranker_runtime_root"].endswith("/.photos-mcp/runtime/photo-ranker")
    assert payload["photo_ranker_vlm_cache_root"].endswith("/.photos-mcp/cache/vlm")
    assert payload["launch_mode"] in {"bundle", "source"}
    assert payload["launch_behavior"] == "background"
    assert payload["launch_log_path"].endswith("/.photos-mcp/logs/launcher.log")
    if payload["launch_mode"] == "bundle":
        assert payload["terminal_helper_python_bin"].endswith("/Contents/MacOS/python")


def test_run_photos_mcp_app_dry_run_prefers_explicit_bundle_override(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/run-photos-mcp-app.sh"
    bundle_root = tmp_path / "PhotosMcp.app" / "Contents" / "MacOS"
    bundle_root.mkdir(parents=True)
    executable_path = bundle_root / "PhotosMcp"
    executable_path.write_text("#!/bin/zsh\nexit 0\n", encoding="utf-8")
    executable_path.chmod(0o755)
    python_path = bundle_root / "python"
    python_path.write_text("#!/bin/zsh\nexit 0\n", encoding="utf-8")
    python_path.chmod(0o755)

    env = os.environ.copy()
    env["PHOTOS_MCP_DRY_RUN"] = "1"
    env["PHOTOS_MCP_BUNDLE_PATH"] = str(tmp_path / "PhotosMcp.app")

    proc = subprocess.run(
        ["/bin/zsh", str(script_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["launch_mode"] == "bundle"
    assert payload["launch_behavior"] == "background"
    assert payload["bundle_variant"] == "configured"
    assert payload["bundle_path"] == str(tmp_path / "PhotosMcp.app")
    assert payload["terminal_helper_python_bin"] == str(python_path)


def test_run_photos_mcp_app_dry_run_supports_foreground_override() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/run-photos-mcp-app.sh"

    env = os.environ.copy()
    env["PHOTOS_MCP_DRY_RUN"] = "1"
    env["PHOTOS_MCP_FOREGROUND"] = "1"

    proc = subprocess.run(
        ["/bin/zsh", str(script_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["launch_behavior"] == "foreground"
