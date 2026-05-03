from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from nanobot.agent.memory import MemoryStore
from nanobot.i18n import translate as _t
from nanobot.session.memory_correction_nlp import memory_correction_nlp_pack


MEMORY_CORRECTION_DEFAULT_LOCALE = "ko-KR"
MEMORY_CORRECTION_NLP = memory_correction_nlp_pack(MEMORY_CORRECTION_DEFAULT_LOCALE)


@dataclass(frozen=True)
class MemoryCorrectionRequest:
    action: str
    phrase: str
    detail: str | None
    task_title: str | None


@dataclass(frozen=True)
class MemoryCorrectionResult:
    reply: str
    applied: bool


def parse_memory_correction_message(content: str) -> MemoryCorrectionRequest | None:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return None

    header = lines[0]
    phrase, action, inline_detail = _match_header(header)
    if phrase is None or action is None:
        return None

    fields: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()

    detail_field = MEMORY_CORRECTION_NLP.detail_fields[action]
    detail = inline_detail or fields.get(detail_field)
    if detail and _is_placeholder(detail):
        detail = None

    task_title = fields.get(MEMORY_CORRECTION_NLP.task_title_field) or None
    if task_title and _is_placeholder(task_title):
        task_title = None

    return MemoryCorrectionRequest(
        action=action,
        phrase=phrase,
        detail=detail.strip() if detail else None,
        task_title=task_title.strip() if task_title else None,
    )


def apply_memory_correction(
    workspace: Path,
    request: MemoryCorrectionRequest,
    *,
    locale: str | None = MEMORY_CORRECTION_DEFAULT_LOCALE,
) -> MemoryCorrectionResult:
    store = MemoryStore(workspace)

    if request.action == "remember":
        if not request.detail:
            return MemoryCorrectionResult(
                reply=_t("memory_correction.remember.missing_detail", locale=locale),
                applied=False,
            )
        updated, changed = _append_memory_entry(store.read_memory(), request.detail)
        if changed:
            store.write_memory(updated)
            return MemoryCorrectionResult(
                reply=_t("memory_correction.remember.applied", locale=locale, detail=request.detail),
                applied=True,
            )
        return MemoryCorrectionResult(
            reply=_t("memory_correction.remember.duplicate", locale=locale, detail=request.detail),
            applied=False,
        )

    if request.action == "forget":
        if not request.detail:
            return MemoryCorrectionResult(
                reply=_t("memory_correction.forget.missing_detail", locale=locale),
                applied=False,
            )
        user_content = store.read_user()
        memory_content = store.read_memory()
        next_user, removed_user = _remove_entry(user_content, request.detail)
        next_memory, removed_memory = _remove_entry(memory_content, request.detail)
        if removed_user:
            store.write_user(next_user)
        if removed_memory:
            store.write_memory(next_memory)
        if removed_user or removed_memory:
            targets = []
            if removed_user:
                targets.append("USER.md")
            if removed_memory:
                targets.append("memory/MEMORY.md")
            joined = ", ".join(targets)
            return MemoryCorrectionResult(
                reply=_t("memory_correction.forget.removed", locale=locale, targets=joined, detail=request.detail),
                applied=True,
            )
        return MemoryCorrectionResult(
            reply=_t("memory_correction.forget.not_found", locale=locale, detail=request.detail),
            applied=False,
        )

    if request.action == "not-default":
        if not request.detail:
            return MemoryCorrectionResult(
                reply=_t("memory_correction.not_default.missing_detail", locale=locale),
                applied=False,
            )
        updated, changed = _append_special_instruction(store.read_user(), request.detail)
        if changed:
            store.write_user(updated)
            return MemoryCorrectionResult(
                reply=_t("memory_correction.not_default.applied", locale=locale, detail=request.detail),
                applied=True,
            )
        return MemoryCorrectionResult(
            reply=_t("memory_correction.not_default.duplicate", locale=locale, detail=request.detail),
            applied=False,
        )

    if request.action == "project-complete":
        detail = request.detail
        if not detail and request.task_title:
            detail = f"{request.task_title} {MEMORY_CORRECTION_NLP.project_complete_suffix}"
        if not detail:
            return MemoryCorrectionResult(
                reply=_t("memory_correction.project_complete.missing_detail", locale=locale),
                applied=False,
            )
        entry = f"{MEMORY_CORRECTION_NLP.project_complete_entry_prefix}: {detail}"
        updated, changed = _append_memory_entry(store.read_memory(), entry)
        if changed:
            store.write_memory(updated)
            return MemoryCorrectionResult(
                reply=_t("memory_correction.project_complete.applied", locale=locale, detail=detail),
                applied=True,
            )
        return MemoryCorrectionResult(
            reply=_t("memory_correction.project_complete.duplicate", locale=locale, detail=detail),
            applied=False,
        )

    return MemoryCorrectionResult(reply=_t("memory_correction.unsupported", locale=locale), applied=False)


def _match_header(header: str) -> tuple[str | None, str | None, str | None]:
    for phrase, action in MEMORY_CORRECTION_NLP.action_by_phrase.items():
        if header == phrase:
            return phrase, action, None
        if header.startswith(f"{phrase}:"):
            detail = header.split(":", 1)[1].strip() or None
            return phrase, action, detail
    return None, None, None


def _is_placeholder(value: str) -> bool:
    stripped = value.strip()
    return stripped.startswith("[") and stripped.endswith("]")


def _append_memory_entry(content: str, detail: str) -> tuple[str, bool]:
    bullet = f"- {detail.strip()}"
    lines = content.splitlines()
    if any(line.strip() == bullet for line in lines):
        return _ensure_trailing_newline(content), False

    if not content.strip():
        return f"# MEMORY\n\n{bullet}\n", True

    base = content.rstrip("\n")
    return f"{base}\n{bullet}\n", True


def _append_special_instruction(content: str, detail: str) -> tuple[str, bool]:
    bullet = f"- {detail.strip()}"
    lines = content.splitlines()
    if any(line.strip() == bullet for line in lines):
        return _ensure_trailing_newline(content), False

    if not lines:
        return f"## Special Instructions\n\n{bullet}\n", True

    insert_at = None
    for index, line in enumerate(lines):
        if line.strip() == "## Special Instructions":
            insert_at = index + 1
            break

    if insert_at is None:
        base = content.rstrip("\n")
        return f"{base}\n\n## Special Instructions\n\n{bullet}\n", True

    next_lines = lines[:insert_at]
    while insert_at < len(lines) and not lines[insert_at].strip():
        next_lines.append(lines[insert_at])
        insert_at += 1
    next_lines.append(bullet)
    next_lines.extend(lines[insert_at:])
    return _ensure_trailing_newline("\n".join(next_lines)), True


def _remove_entry(content: str, detail: str) -> tuple[str, bool]:
    if not content.strip():
        return content, False
    target = detail.strip()
    target_normalized = _normalize_entry_text(target)
    kept: list[str] = []
    removed = False
    for line in content.splitlines():
        stripped = line.strip()
        if _matches_entry_line(stripped, target, target_normalized):
            removed = True
            continue
        kept.append(line)
    next_content = "\n".join(kept).rstrip() + "\n"
    return next_content, removed


def _matches_entry_line(stripped_line: str, target: str, target_normalized: str) -> bool:
    if not stripped_line:
        return False
    if stripped_line == f"- {target}" or stripped_line == target:
        return True

    entry = stripped_line[2:].strip() if stripped_line.startswith("- ") else stripped_line
    entry_normalized = _normalize_entry_text(entry)
    if not entry_normalized or not target_normalized:
        return False
    if entry_normalized == target_normalized:
        return True
    if len(target_normalized) < 4:
        return False
    return entry_normalized.startswith(target_normalized) or target_normalized in entry_normalized


def _normalize_entry_text(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"^[-*]\s+", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" .,!?:;\"'`()[]{}")


def _ensure_trailing_newline(content: str) -> str:
    if not content:
        return ""
    return content if content.endswith("\n") else f"{content}\n"