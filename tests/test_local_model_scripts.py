from pathlib import Path
import subprocess
import json


def test_local_models_help_lists_supported_targets():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/local-models/local-models.sh"

    proc = subprocess.run(
        ["/bin/zsh", str(script_path), "help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    output = proc.stdout
    assert "local model" in output.lower()
    assert "benchmark" in output.lower()
    assert "lfm2" in output.lower()
    assert "qwen36" in output.lower()
    assert "qwen35-base-mlx-4bit" in output.lower()
    assert "qwen3-vl-4b" in output.lower()
    assert "qwen3-vl-8b" in output.lower()
    lines = [line.strip().lower() for line in output.splitlines()]
    assert "install <lfm2|qwen35-base-mlx-4bit|qwen36|qwen3-vl-4b|qwen3-vl-8b>        install and start one launchd service" in lines
    assert "start <lfm2|qwen35-base-mlx-4bit|qwen36|qwen3-vl-4b|qwen3-vl-8b>          start one installed launchd service" in lines


def test_local_models_help_lists_broker_actions():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/local-models/local-models.sh"

    proc = subprocess.run(
        ["/bin/zsh", str(script_path), "help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    output = proc.stdout.lower()
    assert "lease-status" in output
    assert "reconcile" in output


def test_local_models_lease_status_prints_broker_state(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/local-models/local-models.sh"
    broker_state_root = tmp_path / "vision-runtime-broker"
    broker_state_root.mkdir()
    (broker_state_root / "qwen3-vl-4b.json").write_text(
        json.dumps(
            {
                "target": "qwen3-vl-4b",
                "model": "mlx-community/Qwen3-VL-4B-Instruct-4bit",
                "api_base": "http://127.0.0.1:1252/v1",
                "running": True,
                "last_used_at": 42.0,
                "idle_timeout_seconds": 300.0,
                "holders": {
                    "smart-router-local": {
                        "acquired_at": 40.0,
                        "last_used_at": 42.0,
                        "expires_at": 900.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        ["/bin/zsh", str(script_path), "lease-status", "qwen3-vl-4b"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env={
            **subprocess.os.environ,
            "NANOBOT_VISION_RUNTIME_BROKER_STATE_ROOT": str(broker_state_root),
        },
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["qwen3-vl-4b"]["holder_count"] == 1
    assert "smart-router-local" in payload["qwen3-vl-4b"]["holders"]


def test_local_models_reconcile_drops_expired_holders(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/local-models/local-models.sh"
    broker_state_root = tmp_path / "vision-runtime-broker"
    broker_state_root.mkdir()
    (broker_state_root / "qwen3-vl-8b.json").write_text(
        json.dumps(
            {
                "target": "qwen3-vl-8b",
                "model": "mlx-community/Qwen3-VL-8B-Instruct-4bit",
                "api_base": "http://127.0.0.1:1254/v1",
                "running": True,
                "last_used_at": 42.0,
                "idle_timeout_seconds": 300.0,
                "holders": {
                    "photo-ranker:pid-9": {
                        "acquired_at": 1.0,
                        "last_used_at": 2.0,
                        "expires_at": 3.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        ["/bin/zsh", str(script_path), "reconcile", "qwen3-vl-8b"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env={
            **subprocess.os.environ,
            "NANOBOT_VISION_RUNTIME_BROKER_STATE_ROOT": str(broker_state_root),
        },
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["qwen3-vl-8b"]["holder_count"] == 0
    assert payload["qwen3-vl-8b"]["holders"] == {}


def test_local_models_rejects_start_all():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/local-models/local-models.sh"

    proc = subprocess.run(
        ["/bin/zsh", str(script_path), "start", "all"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    assert "start all is not allowed" in proc.stderr.lower()


def test_local_models_rejects_install_all():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/local-models/local-models.sh"

    proc = subprocess.run(
        ["/bin/zsh", str(script_path), "install", "all"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    assert "install all is not allowed" in proc.stderr.lower()


def test_lfm2_wrapper_uses_rapid_mlx_and_official_mlx_repo():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/local-models/start-lfm2-llama-cpp.sh"

    content = script_path.read_text(encoding="utf-8")

    assert 'LiquidAI/LFM2-24B-A2B-MLX-4bit' in content
    assert 'rapid-mlx' in content
    assert '--no-thinking' in content
    assert 'llama-server' not in content
    assert 'RAPID_MLX_HF_HOME' in content
    assert 'RAPID_MLX_HUGGINGFACE_HUB_CACHE' in content
    assert 'RAPID_MLX_TRANSFORMERS_CACHE' in content
    assert '${HF_HOME:-' not in content


def test_start_local_model_services_refreshes_local_wrapper_scripts():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/local-models/start-local-model-services.sh"

    content = script_path.read_text(encoding="utf-8")

    assert 'check_memory_headroom_for_model "$model"' in content
    assert 'cp "$SCRIPT_DIR/common.sh" "$LOCAL_SCRIPT_DIR/common.sh"' in content
    assert 'cp "$(model_source_script "$model")" "$(model_local_script "$model")"' in content


def test_cleanup_model_install_state_removes_legacy_plist_files():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/local-models/common.sh"

    content = script_path.read_text(encoding="utf-8")

    assert 'rm -f "$legacy_plist"' in content
    assert '"$TARGET_DIR/com.zeroclaw.llama-cpp.plist"' in content


def test_photo_mcp_wrappers_use_my_mcp_servers_root():
    repo_root = Path(__file__).resolve().parents[2]
    shared_wrapper = repo_root / "infra/scripts/run-photos-mcp-app.sh"
    source_wrapper = repo_root / "infra/scripts/run-photo-source-mcp.sh"
    ranker_wrapper = repo_root / "infra/scripts/run-photo-ranker-mcp.sh"

    shared_content = shared_wrapper.read_text(encoding="utf-8")
    source_content = source_wrapper.read_text(encoding="utf-8")
    ranker_content = ranker_wrapper.read_text(encoding="utf-8")

    assert 'PHOTOS_MCP_ROOT="/Volumes/ExtData/my-mcp-servers/photos-mcp"' in shared_content
    assert 'PHOTOS_MCP_HOME="${PHOTOS_MCP_HOME:-$HOME/.photos-mcp}"' in shared_content
    assert 'LOCAL_STANDALONE_BUNDLE_PATH="$PHOTOS_MCP_ROOT/dist-framework-standalone/PhotosMcp.app"' in shared_content
    assert 'LOCAL_STANDALONE_BUNDLE_ALT_PATH="$PHOTOS_MCP_ROOT/dist-framework-standalone/photos-mcp.app"' in shared_content
    assert 'run-photos-mcp-app.sh' in source_content
    assert "/Volumes/ExtData/MyOpenClawRepo/mcp-servers/photo-source" not in source_content
    assert 'run-photos-mcp-app.sh' in ranker_content
    assert "/Volumes/ExtData/MyOpenClawRepo/mcp-servers/photo-ranker" not in ranker_content


def test_photo_ranker_wrapper_defaults_to_shared_local_vision_endpoint():
    repo_root = Path(__file__).resolve().parents[2]
    ranker_wrapper = repo_root / "infra/scripts/run-photos-mcp-app.sh"

    content = ranker_wrapper.read_text(encoding="utf-8")

    assert 'PHOTOS_MCP_RUNTIME_ROOT="${PHOTOS_MCP_RUNTIME_ROOT:-${NANOBOT_PHOTOS_MCP_RUNTIME_ROOT:-$PHOTOS_MCP_HOME/runtime}}"' in content
    assert 'PHOTOS_MCP_CACHE_ROOT="${PHOTOS_MCP_CACHE_ROOT:-${NANOBOT_PHOTOS_MCP_CACHE_ROOT:-$PHOTOS_MCP_HOME/cache}}"' in content
    assert 'PHOTO_RANKER_RUNTIME_ROOT="${PHOTO_RANKER_RUNTIME_ROOT:-$PHOTOS_MCP_ROOT/.runtime/photo-ranker}"' in content
    assert 'PHOTO_RANKER_VLM_CACHE_ROOT="${PHOTO_RANKER_VLM_CACHE_ROOT:-$PHOTOS_MCP_ROOT/.model-cache/huggingface}"' in content
    assert 'PHOTO_RANKER_MODEL_CACHE_ROOT="${PHOTO_RANKER_MODEL_CACHE_ROOT:-$PHOTOS_MCP_ROOT/.model-cache/models/photo-ranker}"' in content
    assert 'PHOTO_SOURCE_CACHE_ROOT="${PHOTO_SOURCE_CACHE_ROOT:-$PHOTOS_MCP_ROOT/.model-cache/photo-source}"' in content
    assert 'if [[ -z "${PHOTO_RANKER_VLM_BACKEND:-}" ]]; then' in content
    assert 'export PHOTO_RANKER_VLM_BACKEND="openai_compat"' in content
    assert 'export PHOTO_RANKER_VLM_API_BASE="${PHOTO_RANKER_VLM_API_BASE:-http://127.0.0.1:1252/v1}"' in content
    assert 'export PHOTO_RANKER_VLM_MODEL="${PHOTO_RANKER_VLM_MODEL:-mlx-community/Qwen3-VL-4B-Instruct-4bit}"' in content
    assert 'export PHOTO_RANKER_VLM_TARGET="${PHOTO_RANKER_VLM_TARGET:-qwen3-vl-4b}"' in content
    assert 'PHOTO_RANKER_VLM_AUTO_UNLOAD="${PHOTO_RANKER_VLM_AUTO_UNLOAD:-1}"' in content
    assert 'export HF_HOME="$PHOTO_RANKER_VLM_CACHE_ROOT"' in content


def test_photo_mcp_install_script_uses_self_contained_photos_mcp_root():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/install-nanobot-photo-mcps.sh"

    content = script_path.read_text(encoding="utf-8")

    assert 'PHOTOS_MCP_ROOT="/Volumes/ExtData/my-mcp-servers/photos-mcp"' in content
    assert 'PHOTOS_MCP_DIR="$PHOTOS_MCP_ROOT"' in content
    assert 'uv sync --python "$PYTHON_VERSION" --directory "$PHOTOS_MCP_DIR" --extra app --extra apple --extra vlm --extra review' in content
    assert 'uv sync --python "$PYTHON_VERSION" --directory "$PHOTOS_MCP_DIR" --extra app --extra apple --extra vlm --extra aesthetic --extra face --extra review' in content
    assert 'MY_PHOTOS_MCP_ROOT="/Volumes/ExtData/my-mcp-servers/mcp-my-photos"' not in content
    assert 'PHOTO_SOURCE_DIR="$MY_PHOTOS_MCP_ROOT/photo-source"' not in content
    assert 'PHOTO_RANKER_DIR="$MY_PHOTOS_MCP_ROOT/photo-ranker"' not in content
    assert "/Volumes/ExtData/MyOpenClawRepo/mcp-servers/photo-source" not in content
    assert "/Volumes/ExtData/MyOpenClawRepo/mcp-servers/photo-ranker" not in content


def test_photo_mcp_install_script_installs_vlm_runtime_and_cache_dirs():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/install-nanobot-photo-mcps.sh"

    content = script_path.read_text(encoding="utf-8")

    assert 'PHOTOS_MCP_HOME="${PHOTOS_MCP_HOME:-$HOME/.photos-mcp}"' in content
    assert 'PHOTO_RANKER_RUNTIME_ROOT="${PHOTO_RANKER_RUNTIME_ROOT:-$PHOTOS_MCP_ROOT/.runtime/photo-ranker}"' in content
    assert 'PHOTO_RANKER_VLM_CACHE_ROOT="${PHOTO_RANKER_VLM_CACHE_ROOT:-$PHOTOS_MCP_ROOT/.model-cache/huggingface}"' in content
    assert 'PHOTO_RANKER_MODEL_CACHE_ROOT="${PHOTO_RANKER_MODEL_CACHE_ROOT:-$PHOTOS_MCP_ROOT/.model-cache/models/photo-ranker}"' in content
    assert 'PHOTO_SOURCE_CACHE_ROOT="${PHOTO_SOURCE_CACHE_ROOT:-$PHOTOS_MCP_ROOT/.model-cache/photo-source}"' in content
    assert 'mkdir -p "$PHOTOS_MCP_RUNTIME_ROOT" "$PHOTOS_MCP_CACHE_ROOT" "$PHOTO_RANKER_RUNTIME_ROOT" "$PHOTO_RANKER_VLM_CACHE_ROOT" "$PHOTO_RANKER_MODEL_CACHE_ROOT" "$PHOTO_SOURCE_CACHE_ROOT"' in content
    assert '--extra vlm' in content
    assert '--extra app --extra apple --extra vlm --extra review' in content


def test_use_local_model_stops_other_targets_before_activation():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/local-models/use-local-model.sh"

    content = script_path.read_text(encoding="utf-8")

    assert '"$SCRIPT_DIR/stop-local-model-services.sh" all' in content
    assert '"$SCRIPT_DIR/start-local-model-services.sh" "$target"' in content


def test_qwen36_wrapper_uses_mlx_vlm_server_runtime():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/local-models/start-qwen36-mlx.sh"

    content = script_path.read_text(encoding="utf-8")

    assert 'MLX_VLM_PYTHON="$(ensure_mlx_vlm_runtime)"' in content
    assert '"$MLX_VLM_PYTHON" -m mlx_vlm server' in content
    assert 'MLX_SERVER_BIN="$(ensure_mlx_runtime)"' not in content


def test_qwen3_vl_wrappers_use_rapid_mlx_multimodal_serve_path():
    repo_root = Path(__file__).resolve().parents[2]
    qwen3_vl_4b = repo_root / "infra/scripts/local-models/start-qwen3-vl-4b-rapid-mlx.sh"
    qwen3_vl_8b = repo_root / "infra/scripts/local-models/start-qwen3-vl-8b-rapid-mlx.sh"

    content_4b = qwen3_vl_4b.read_text(encoding="utf-8")
    content_8b = qwen3_vl_8b.read_text(encoding="utf-8")

    assert 'serve qwen3-vl-4b' in content_4b
    assert '--mllm' in content_4b
    assert 'RAPID_MLX_VENV_DIR' in content_4b
    assert 'RAPID_MLX_STORAGE_ROOT' in content_4b
    assert 'LOCAL_MODEL_RUNTIME_CACHE_ROOT' in content_4b

    assert 'serve qwen3-vl-8b' in content_8b
    assert '--mllm' in content_8b
    assert 'RAPID_MLX_VENV_DIR' in content_8b
    assert 'RAPID_MLX_STORAGE_ROOT' in content_8b
    assert 'LOCAL_MODEL_RUNTIME_CACHE_ROOT' in content_8b