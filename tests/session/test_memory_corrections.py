from __future__ import annotations

from pathlib import Path

from nanobot.session.memory_corrections import (
    MemoryCorrectionRequest,
    apply_memory_correction,
    parse_memory_correction_message,
)


def test_parse_memory_correction_uses_korean_nlp_pack() -> None:
    request = parse_memory_correction_message(
        "기억해\n내용: Telegram 채널을 우선 사용한다\n현재 task: memory correction",
    )

    assert request is not None
    assert request.action == "remember"
    assert request.detail == "Telegram 채널을 우선 사용한다"
    assert request.task_title == "memory correction"


def test_apply_memory_correction_can_reply_in_english(tmp_path: Path) -> None:
    result = apply_memory_correction(
        tmp_path,
        MemoryCorrectionRequest(
            action="remember",
            phrase="기억해",
            detail="Prefer short replies",
            task_title=None,
        ),
        locale="en-US",
    )

    assert result.applied is True
    assert result.reply == "Added it to memory/MEMORY.md: Prefer short replies"


def test_forget_removes_special_instruction_by_partial_match(tmp_path: Path) -> None:
    (tmp_path / "USER.md").write_text(
        "## Special Instructions\n\n- 답변 길이는 기본적으로 간결하게 유지\n",
        encoding="utf-8",
    )

    result = apply_memory_correction(
        tmp_path,
        MemoryCorrectionRequest(
            action="forget",
            phrase="잊어",
            detail="기본적으로 간결하게 유지",
            task_title=None,
        ),
    )

    assert result.applied is True
    assert "USER.md" in result.reply
    user_text = (tmp_path / "USER.md").read_text(encoding="utf-8")
    assert "답변 길이는 기본적으로 간결하게 유지" not in user_text


def test_forget_removes_project_memory_entry_by_partial_match(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text(
        "# MEMORY\n\n- 프로젝트 종료: websocket session follow-up 완료\n",
        encoding="utf-8",
    )

    result = apply_memory_correction(
        tmp_path,
        MemoryCorrectionRequest(
            action="forget",
            phrase="잊어",
            detail="websocket session follow-up",
            task_title=None,
        ),
    )

    assert result.applied is True
    assert "memory/MEMORY.md" in result.reply
    memory_text = (memory_dir / "MEMORY.md").read_text(encoding="utf-8")
    assert "websocket session follow-up 완료" not in memory_text