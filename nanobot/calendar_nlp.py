from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CalendarNaturalLanguagePack:
    create_keywords: tuple[str, ...]
    create_verbs: tuple[str, ...]
    mutation_verbs: tuple[str, ...]
    delete_verbs: tuple[str, ...]
    update_verbs: tuple[str, ...]
    approve_words: tuple[str, ...]
    cancel_words: tuple[str, ...]
    cancel_command_aliases: frozenset[str]
    input_cancel_words: frozenset[str]
    weekday_index: dict[str, int]
    relative_day_offsets: tuple[tuple[str, int], ...]
    korean_year_date_pattern: str
    month_day_pattern: str
    next_weekday_pattern: str
    time_pattern: str
    morning_marker: str
    afternoon_marker: str
    half_marker: str
    one_hour_pattern: str
    hour_duration_pattern: str
    minute_duration_pattern: str
    create_title_removal_patterns: tuple[str, ...]
    create_title_tokens: tuple[str, ...]
    mutation_title_removal_patterns: tuple[str, ...]
    mutation_title_tokens: tuple[str, ...]
    title_strip_chars: str
    mutation_title_strip_chars: str


KO_CALENDAR_NLP = CalendarNaturalLanguagePack(
    create_keywords=("일정", "예약", "캘린더"),
    create_verbs=("잡아", "등록", "추가", "넣어", "만들", "생성", "예약"),
    mutation_verbs=("삭제", "지워", "취소", "옮겨", "변경", "수정", "미뤄", "당겨"),
    delete_verbs=("삭제", "지워", "취소"),
    update_verbs=("옮겨", "변경", "수정", "미뤄", "당겨"),
    approve_words=("승인", "확정", "진행", "좋아", "맞아", "그래", "ok", "okay", "yes"),
    cancel_words=("취소", "반려", "거절", "거부", "아니", "하지마", "하지 마", "cancel", "deny", "no"),
    cancel_command_aliases=frozenset(("취소",)),
    input_cancel_words=frozenset(("취소", "cancel", "stop", "abort")),
    weekday_index={
        "월": 0,
        "화": 1,
        "수": 2,
        "목": 3,
        "금": 4,
        "토": 5,
        "일": 6,
    },
    relative_day_offsets=(("모레", 2), ("내일", 1), ("오늘", 0)),
    korean_year_date_pattern=r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일",
    month_day_pattern=r"(?<!년\s)(\d{1,2})\s*월\s*(\d{1,2})\s*일",
    next_weekday_pattern=r"다음\s*([월화수목금토일])\s*요일",
    time_pattern=r"(오전|오후)?\s*(\d{1,2})\s*시(?!간)\s*(반|\d{1,2}\s*분)?",
    morning_marker="오전",
    afternoon_marker="오후",
    half_marker="반",
    one_hour_pattern=r"한\s*시간",
    hour_duration_pattern=r"(\d{1,2})\s*시간(?:\s*(\d{1,2})\s*분)?",
    minute_duration_pattern=r"(\d{1,3})\s*분\s*(?:동안|짜리)?",
    create_title_removal_patterns=(
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일",
        r"\d{1,2}\s*월\s*\d{1,2}\s*일",
        r"다음\s*[월화수목금토일]\s*요일",
        r"오늘|내일|모레",
        r"(오전|오후)?\s*\d{1,2}\s*시(?!간)\s*(반|\d{1,2}\s*분)?\s*(부터|에)?",
        r"\b\d{1,2}:\d{2}\b\s*(부터|에)?",
        r"한\s*시간",
        r"\d{1,2}\s*시간(?:\s*\d{1,2}\s*분)?",
        r"\d{1,3}\s*분\s*(동안|짜리)?",
    ),
    create_title_tokens=(
        "캘린더",
        "일정",
        "예약",
        "등록",
        "추가",
        "넣어줘",
        "넣어",
        "잡아줘",
        "잡아",
        "만들어줘",
        "만들어",
        "생성해줘",
        "생성",
        "해줘",
        "해주세요",
        "부탁해",
    ),
    mutation_title_removal_patterns=(
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일",
        r"\d{1,2}\s*월\s*\d{1,2}\s*일",
        r"다음\s*[월화수목금토일]\s*요일",
        r"오늘|내일|모레",
        r"(오전|오후)?\s*\d{1,2}\s*시(?!간)\s*(반|\d{1,2}\s*분)?\s*(부터|에|로|으로)?",
        r"\b\d{1,2}:\d{2}\b\s*(부터|에|로|으로)?",
        r"한\s*시간",
        r"\d{1,2}\s*시간(?:\s*\d{1,2}\s*분)?",
        r"\d{1,3}\s*분\s*(동안|짜리)?",
    ),
    mutation_title_tokens=(
        "캘린더",
        "일정",
        "예약",
        "변경해줘",
        "변경",
        "수정해줘",
        "수정",
        "옮겨줘",
        "옮겨",
        "미뤄줘",
        "미뤄",
        "당겨줘",
        "당겨",
        "삭제해줘",
        "삭제",
        "지워줘",
        "지워",
        "취소해줘",
        "취소",
        "해줘",
        "해주세요",
        "부탁해",
    ),
    title_strip_chars=" 은는이가을를에으로 ",
    mutation_title_strip_chars=" 은는이가을를에으로로 ",
)


def calendar_nlp_pack(locale: str | None = None) -> CalendarNaturalLanguagePack:
    return KO_CALENDAR_NLP