from __future__ import annotations

from string import Formatter
from typing import Any


DEFAULT_LOCALE = "en"
FALLBACK_LOCALE = "en"


_CATALOG: dict[str, dict[str, str]] = {
    "en": {
        "calendar.automation.not_configured": "Calendar automation is not configured. Set N8N_BASE_URL and the Calendar webhook env vars first.",
        "calendar.buttons.approve": "Approve",
        "calendar.buttons.cancel": "Cancel",
        "calendar.buttons.force_create": "Request approval anyway",
        "calendar.buttons.reschedule": "Enter a new time",
        "calendar.conflict.choices_text": "- Choices: Request approval anyway / Enter a new time / Cancel",
        "calendar.conflict.continue_prompt": "Choose how to continue before approval.",
        "calendar.conflict.extra_count": " plus {count} more",
        "calendar.event.untitled": "Untitled event",
        "calendar.input.cancelled": "Calendar create input was cancelled.",
        "calendar.input.end_after_start": "Calendar create needs an end time later than the start time. Reply with a later ISO end time, or choose Cancel.",
        "calendar.input.end_prompt": "Calendar create needs an end time. Reply with an ISO time like 2026-05-02T16:00:00+09:00, or choose Cancel.",
        "calendar.input.invalid_time": "The {field} time must be ISO format, for example 2026-05-02T15:00:00+09:00.",
        "calendar.input.start_prompt": "Calendar create needs a start time. Reply with an ISO time like 2026-05-02T15:00:00+09:00, or choose Cancel.",
        "calendar.input.title_prompt": "Calendar create needs a title. Reply with the event title, or choose Cancel to stop.",
        "calendar.help.natural_delete": "- Natural delete: `2026-05-02 3 PM dentist calendar event delete`",
        "calendar.help.natural_update": "- Natural update: `2026-05-02 3 PM dentist calendar event move to 4 PM`",
        "calendar.natural.delete_missing": "Calendar delete needs a title and date. For example: 2026-05-05 3 PM dentist calendar event delete",
        "calendar.natural.delete_purpose": "delete",
        "calendar.natural.delete_target_not_found": "Could not find an event to delete.",
        "calendar.natural.update_missing": "Calendar update needs a title, date, current time, and new time. For example: 2026-05-05 3 PM dentist calendar event move to 4 PM",
        "calendar.natural.update_purpose": "update",
        "calendar.natural.update_target_not_found": "Could not find an event to update.",
        "calendar.request.cancelled_before_approval": "Calendar create request was cancelled before approval.",
        "calendar.target.find_candidates_message": "Find calendar candidates.",
        "calendar.target.multiple_header": "Multiple events can be {purpose}. Please provide a more specific title and time.",
        "calendar.target.not_found": "Could not find an event to {purpose}: '{title}'. Please provide a more specific date and time.",
        "calendar.webhook.summary_request": "Summarize today's schedule.",
        "calendar.webhook.summary_unavailable": "Could not retrieve today's calendar summary.",
    },
    "ko": {
        "calendar.automation.not_configured": "Calendar automation is not configured. Set N8N_BASE_URL and the Calendar webhook env vars first.",
        "calendar.buttons.approve": "승인",
        "calendar.buttons.cancel": "취소",
        "calendar.buttons.force_create": "그래도 생성 승인 요청",
        "calendar.buttons.reschedule": "새 시간 다시 입력",
        "calendar.conflict.choices_text": "- Choices: 그래도 생성 승인 요청 / 새 시간 다시 입력 / 취소",
        "calendar.conflict.continue_prompt": "Choose how to continue before approval.",
        "calendar.conflict.extra_count": " 외 {count}건",
        "calendar.event.untitled": "제목 없는 일정",
        "calendar.input.cancelled": "Calendar create input was cancelled.",
        "calendar.input.end_after_start": "Calendar create needs an end time later than the start time. Reply with a later ISO end time, or choose 취소.",
        "calendar.input.end_prompt": "Calendar create needs an end time. Reply with an ISO time like 2026-05-02T16:00:00+09:00, or choose 취소.",
        "calendar.input.invalid_time": "The {field} time must be ISO format, for example 2026-05-02T15:00:00+09:00.",
        "calendar.input.start_prompt": "Calendar create needs a start time. Reply with an ISO time like 2026-05-02T15:00:00+09:00, or choose 취소.",
        "calendar.input.title_prompt": "Calendar create needs a title. Reply with the event title, or choose 취소 to stop.",
        "calendar.help.natural_delete": "- Natural delete: `2026-05-02 오후 3시 치과 일정 삭제해줘`",
        "calendar.help.natural_update": "- Natural update: `2026-05-02 오후 3시 치과 일정을 오후 4시로 변경해줘`",
        "calendar.natural.delete_missing": "Calendar delete needs a title and date. For example: 2026-05-05 오후 3시 치과 일정 삭제해줘",
        "calendar.natural.delete_purpose": "삭제",
        "calendar.natural.delete_target_not_found": "삭제할 일정을 찾지 못했습니다.",
        "calendar.natural.update_missing": "Calendar update needs a title, date, current time, and new time. For example: 2026-05-05 오후 3시 치과 일정을 오후 4시로 변경해줘",
        "calendar.natural.update_purpose": "변경",
        "calendar.natural.update_target_not_found": "변경할 일정을 찾지 못했습니다.",
        "calendar.request.cancelled_before_approval": "Calendar create request was cancelled before approval.",
        "calendar.target.find_candidates_message": "일정 후보를 찾아줘",
        "calendar.target.multiple_header": "{purpose}할 일정 후보가 여러 개입니다. 제목과 시간을 더 구체적으로 알려주세요.",
        "calendar.target.not_found": "{purpose}할 일정 '{title}' 을 찾지 못했습니다. 날짜와 시간을 더 구체적으로 알려주세요.",
        "calendar.webhook.summary_request": "오늘 일정 요약해줘",
        "calendar.webhook.summary_unavailable": "오늘 일정 요약을 가져오지 못했습니다.",
    },
}


def normalize_locale(locale: str | None) -> str:
    text = str(locale or "").strip()
    if not text:
        return DEFAULT_LOCALE
    normalized = text.replace("_", "-").lower()
    if normalized.startswith("ko"):
        return "ko"
    if normalized.startswith("en"):
        return "en"
    return normalized.split("-", 1)[0] or DEFAULT_LOCALE


def translate(key: str, *, locale: str | None = None, **values: Any) -> str:
    normalized = normalize_locale(locale)
    template = _CATALOG.get(normalized, {}).get(key)
    if template is None:
        template = _CATALOG[FALLBACK_LOCALE].get(key, key)
    if not values:
        return template
    allowed = {name for _, name, _, _ in Formatter().parse(template) if name}
    return template.format(**{name: values.get(name, "") for name in allowed})
