from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryCorrectionNaturalLanguagePack:
    action_by_phrase: dict[str, str]
    detail_fields: dict[str, str]
    task_title_field: str
    project_complete_suffix: str
    project_complete_entry_prefix: str


KO_MEMORY_CORRECTION_NLP = MemoryCorrectionNaturalLanguagePack(
    action_by_phrase={
        "기억해": "remember",
        "잊어": "forget",
        "이건 기본 선호가 아님": "not-default",
        "이 프로젝트는 끝났어": "project-complete",
    },
    detail_fields={
        "remember": "내용",
        "forget": "내용",
        "not-default": "수정할 기본 선호",
        "project-complete": "프로젝트 메모",
    },
    task_title_field="현재 task",
    project_complete_suffix="완료",
    project_complete_entry_prefix="프로젝트 종료",
)


def memory_correction_nlp_pack(locale: str | None = None) -> MemoryCorrectionNaturalLanguagePack:
    return KO_MEMORY_CORRECTION_NLP


def memory_correction_actions(locale: str | None = None) -> list[dict[str, str]]:
    pack = memory_correction_nlp_pack(locale)
    phrase_by_action = {action: phrase for phrase, action in pack.action_by_phrase.items()}
    return [
        {
            "code": "remember",
            "phrase": phrase_by_action["remember"],
            "target": "owner_profile_or_project_memory",
            "store": "USER.md or memory/MEMORY.md",
        },
        {
            "code": "forget",
            "phrase": phrase_by_action["forget"],
            "target": "owner_profile_or_project_memory",
            "store": "USER.md or memory/MEMORY.md",
        },
        {
            "code": "not-default",
            "phrase": phrase_by_action["not-default"],
            "target": "owner_profile",
            "store": "USER.md",
        },
        {
            "code": "project-complete",
            "phrase": phrase_by_action["project-complete"],
            "target": "project_memory_or_task_summary",
            "store": "memory/MEMORY.md or session.metadata",
        },
    ]