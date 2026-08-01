"""Shared metadata helpers for scheduled cron session turns."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from nanobot.cron.types import CronJob

CRON_TRIGGER_META = "_cron_trigger"
CRON_DEFER_UNTIL_IDLE_META = "_cron_defer_until_session_idle"
CRON_HISTORY_META = "_cron_turn"
_DOMESTIC_TOP_NEWS_SECTIONS = (
    "정치",
    "경제",
    "사회",
    "국제",
    "스포츠",
    "IT",
    "AI",
    "과학",
)
_DOMESTIC_TOP_NEWS_SECTION_SET = frozenset(_DOMESTIC_TOP_NEWS_SECTIONS)
_DOMESTIC_TOP_NEWS_ITEM_RE = re.compile(
    r"^\s*\d+[.)]\s+\[[^\]]+\]\(https?://[^)]+\)\s*$"
)


def _domestic_top_news_heading(line: str) -> str | None:
    """Return a normalized title-list section heading, if this line is one."""
    normalized = line.strip().strip("#").strip()
    if normalized.startswith("**") and normalized.endswith("**"):
        normalized = normalized[2:-2].strip()
    return normalized if normalized in _DOMESTIC_TOP_NEWS_SECTION_SET else None


def _is_domestic_top_news_response(content: str) -> bool:
    """Check that every domestic top-news section retains five article items."""
    if "국내 주요 뉴스" not in content:
        return False
    section: str | None = None
    item_counts = {name: 0 for name in _DOMESTIC_TOP_NEWS_SECTIONS}
    for line in content.splitlines():
        heading = _domestic_top_news_heading(line)
        if heading is not None:
            section = heading
            continue
        if section is not None and _DOMESTIC_TOP_NEWS_ITEM_RE.match(line):
            item_counts[section] += 1
    return all(item_counts[name] >= 5 for name in _DOMESTIC_TOP_NEWS_SECTIONS)


def is_invalid_cron_response(content: str | None) -> bool:
    """Return True when a cron turn did not produce a final user-facing answer."""
    if not isinstance(content, str) or not content.strip():
        return True
    normalized = content.strip().casefold()
    # Some local tool-call parsers leak this intermediate marker as ordinary
    # text after the tool result instead of returning a structured final turn.
    if normalized.startswith("[calling tool") or normalized.startswith("calling tool"):
        return True
    # The title-list briefing must not be delivered with an incomplete
    # category after invalid or duplicate URLs have been stripped.
    return not _is_domestic_top_news_response(content) if "국내 주요 뉴스" in content else False


_CRON_URL_RE = re.compile(r"https?://[^\s)\]>]+")
_GENERIC_NEWS_PATHS = {
    "",
    "/",
    "/news",
    "/news/list",
    "/world",
    "/search",
    "/national/defense",
    "/economy-finance/economy",
    "/news/pc/main/main.html",
}


def _is_article_link(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    path = parsed.path.rstrip("/").casefold()
    if path in _GENERIC_NEWS_PATHS:
        return False
    host = parsed.netloc.casefold()
    # SBS RSS articles use ``endPage.do?news_id=...`` rather than a numeric
    # path or ``.html`` suffix. Treat this documented article permalink as
    # valid so scheduled briefings do not discard SBS coverage.
    if host == "news.sbs.co.kr":
        return (
            parsed.path.casefold() == "/news/endpage.do"
            and bool(parse_qs(parsed.query).get("news_id"))
        )
    # Yonhap exposes stable article identifiers under /view/.  Its section
    # pages are otherwise easy for a model to mistake for an article source.
    if "yna.co.kr" in host:
        return "/view/" in path
    # Other supported news sites generally expose an article marker or a
    # concrete numeric article id in the path.  Generic landing pages do not.
    return (
        "/article" in path
        or "/view/" in path
        or ".html" in path
        or bool(re.search(r"/\d{5,}(?:/|$)", path))
    )


def sanitize_news_cron_response(content: str | None) -> str:
    """Remove non-article and duplicate links from a news cron response.

    Local models occasionally copy a publisher's home/section URL when the
    search result contains a mixture of article and landing links.  Drop the
    whole linked line when its URL is not an article URL so the Telegram
    briefing never presents a misleading source.
    """
    if not isinstance(content, str) or (
        "뉴스 브리핑" not in content and "국내 주요 뉴스" not in content
    ):
        return content or ""
    seen: set[str] = set()
    kept: list[str] = []
    for line in content.splitlines():
        # Some local models append one closing bracket while copying the last
        # Markdown link. Normalize that harmless copy artifact before URL and
        # completeness validation.
        line = re.sub(r"(\]\(https?://[^)\s]+\))\]+$", r"\1", line)
        line = re.sub(r"(\]\(https?://[^\s\])]+)\]$", r"\1)", line)
        urls = _CRON_URL_RE.findall(line)
        if urls:
            if any(not _is_article_link(url) for url in urls):
                continue
            normalized_urls = [url.rstrip(".,") for url in urls]
            if any(url in seen for url in normalized_urls):
                continue
            seen.update(normalized_urls)
        if "기준 시각" in line:
            now_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime(
                "%Y-%m-%d %H:%M"
            )
            line = re.sub(
                r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} KST",
                f"{now_kst} KST",
                line,
                count=1,
            )
        kept.append(line)

    # Removing invalid links can leave gaps such as 1, 3. Renumber affected
    # legacy sections and every category in the domestic title-list format.
    normalized: list[str] = []
    section: str | None = None
    item_number = 0
    for line in kept:
        domestic_heading = _domestic_top_news_heading(line)
        if domestic_heading is not None:
            section = "domestic_top"
            item_number = 0
        elif "한국 중심 주요 뉴스" in line or "글로벌 뉴스 최대" in line:
            section = "news"
            item_number = 0
        elif section in {"news", "domestic_top"} and line.startswith("**"):
            section = None
        if section in {"news", "domestic_top"}:
            match = re.match(r"^(\s*)\d+[.)](\s+)", line)
            if match:
                item_number += 1
                line = re.sub(
                    r"^(\s*)\d+([.)])(\s+)",
                    rf"\g<1>{item_number}\g<2>\g<3>",
                    line,
                    count=1,
                )
        normalized.append(line)
    return "\n".join(normalized).strip()


def cron_trigger(metadata: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return structured cron trigger metadata when present."""
    raw = (metadata or {}).get(CRON_TRIGGER_META)
    return raw if isinstance(raw, dict) else None


def is_cron_turn(metadata: Mapping[str, Any] | None) -> bool:
    return cron_trigger(metadata) is not None


def defer_cron_until_session_idle(metadata: Mapping[str, Any] | None) -> bool:
    return bool(
        is_cron_turn(metadata)
        and (metadata or {}).get(CRON_DEFER_UNTIL_IDLE_META) is True
    )


def cron_run_id(metadata: Mapping[str, Any] | None) -> str | None:
    trigger = cron_trigger(metadata)
    if not trigger:
        return None
    value = trigger.get("run_id")
    return value if isinstance(value, str) and value else None


def cron_history_overrides(metadata: Mapping[str, Any] | None) -> tuple[str | None, dict[str, Any]]:
    """Return session-history text/metadata overrides for a cron turn."""
    trigger = cron_trigger(metadata)
    if not trigger:
        return None, {}
    persist_content = trigger.get("persist_content")
    text = (
        persist_content
        if isinstance(persist_content, str) and persist_content.strip()
        else None
    )
    return text, {
        CRON_HISTORY_META: True,
        "cron_job_id": trigger.get("job_id"),
        "cron_job_name": trigger.get("job_name"),
        "cron_run_id": trigger.get("run_id"),
        "cron_prompt_ref": trigger.get("prompt_ref"),
    }


def is_bound_cron_job(job: CronJob) -> bool:
    """True for session-bound cron jobs with complete delivery context."""
    payload = job.payload
    if (
        payload.kind != "agent_turn"
        or not payload.session_key
        or not payload.origin_channel
        or not payload.origin_chat_id
    ):
        return False
    return not (
        payload.deliver
        or payload.channel
        or payload.to
        or payload.channel_meta
    )
