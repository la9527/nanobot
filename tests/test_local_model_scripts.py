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