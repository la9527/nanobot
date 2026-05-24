from pathlib import Path
import subprocess


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
    lines = [line.strip().lower() for line in output.splitlines()]
    assert "install <lfm2|qwen35-base-mlx-4bit|qwen36>        install and start one launchd service" in lines
    assert "start <lfm2|qwen35-base-mlx-4bit|qwen36>          start one installed launchd service" in lines


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


def test_lfm2_llama_cpp_default_cache_path_uses_nanobot_infra_storage():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/local-models/start-lfm2-llama-cpp.sh"

    content = script_path.read_text(encoding="utf-8")

    assert "/Volumes/ExtData/Nanobot/infra/.local-model-cache/llama-cpp-storage" in content
    assert "/Volumes/ExtData/AI_Project/LLM_Test/.cache/llama-cpp-storage" not in content


def test_start_local_model_services_refreshes_local_wrapper_scripts():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "infra/scripts/local-models/start-local-model-services.sh"

    content = script_path.read_text(encoding="utf-8")

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


def test_photo_ranker_wrapper_sets_dedicated_vlm_runtime_paths():
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
    assert 'export PHOTO_RANKER_VLM_BACKEND="mlx"' in content
    assert 'export PHOTO_RANKER_VLM_MODEL="${PHOTO_RANKER_VLM_MODEL:-mlx-community/Qwen2.5-VL-7B-Instruct-4bit}"' in content
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