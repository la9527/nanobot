from __future__ import annotations

import re
from typing import Any

from .config import PolicySettings
from .types import RequestFeatures, RouteDecision, TierName


_RUNTIME_CONTEXT_RE = re.compile(
    r"^\[Runtime Context[^\n]*\]\n.*?\n\[/Runtime Context\]\n*",
    re.DOTALL,
)


def _content_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text
        return ""
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.append(_content_text(item))
        return "\n".join(part for part in parts if part)
    return str(value)


def _strip_runtime_context(text: str) -> str:
    stripped = _RUNTIME_CONTEXT_RE.sub("", text)
    return stripped.strip()


def _attachment_count(messages: list[dict[str, Any]]) -> int:
    count = 0
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") not in {
                "text",
                "input_text",
                "output_text",
            }:
                count += 1
    return count


def _collect_prompt_text(messages: list[dict[str, Any]]) -> str:
    user_parts = [
        _strip_runtime_context(_content_text(message.get("content")))
        for message in messages
        if message.get("role") == "user"
    ]
    return "\n\n".join(part.strip() for part in user_parts if part and part.strip())


def _keyword_hits(prompt: str, keywords: list[str]) -> list[str]:
    prompt_lower = prompt.lower()
    hits: list[str] = []
    for keyword in keywords:
        if keyword.lower() in prompt_lower:
            hits.append(keyword)
    return hits


class RoutingPolicy:
    def __init__(self, settings: PolicySettings):
        self._settings = settings

    def extract_features(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> RequestFeatures:
        prompt = _collect_prompt_text(messages)
        tool_history_count = sum(
            1 for message in messages if message.get("role") == "tool"
        )
        return RequestFeatures(
            prompt_chars=len(prompt),
            message_count=len(messages),
            tool_count=len(tools or []),
            tool_history_count=tool_history_count,
            attachment_count=_attachment_count(messages),
            has_code_block="```" in prompt,
            code_keyword_hits=_keyword_hits(prompt, self._settings.code_keywords),
            tool_keyword_hits=_keyword_hits(prompt, self._settings.tool_keywords),
            full_keyword_hits=_keyword_hits(prompt, self._settings.full_keywords),
        )

    def choose(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> RouteDecision:
        features = self.extract_features(messages=messages, tools=tools)

        score = 0
        reason_codes: list[str] = []

        if features.prompt_chars <= self._settings.short_prompt_chars:
            reason_codes.append("short_prompt")
        elif features.prompt_chars >= self._settings.long_prompt_chars:
            score += self._settings.reasoning_bonus
            reason_codes.append("long_prompt")
        elif features.prompt_chars >= self._settings.medium_prompt_chars:
            score += 2
            reason_codes.append("medium_prompt")

        if features.has_code_block:
            score += self._settings.code_bonus
            reason_codes.append("code_block")

        if features.code_keyword_hits:
            score += self._settings.code_bonus
            reason_codes.append("code_keywords")

        if features.tool_history_count or (features.tool_count and features.tool_keyword_hits):
            score += self._settings.tool_bonus
            reason_codes.append("tooling_signal")

        if features.full_keyword_hits:
            score += self._settings.reasoning_bonus * min(
                2, len(features.full_keyword_hits)
            )
            reason_codes.append("reasoning_keywords")

        if features.message_count >= 12:
            score += self._settings.history_bonus
            reason_codes.append("long_history")

        if features.attachment_count:
            score += self._settings.attachment_bonus
            reason_codes.append("attachments")

        if score >= self._settings.full_score_min:
            tier: TierName = "full"
        elif score > self._settings.local_score_max:
            tier = "mini"
        else:
            tier = "local"

        if tier == "local" and features.tool_history_count:
            tier = "mini"
            reason_codes.append("tool_history_floor")

        return RouteDecision(
            requested_tier=tier,
            score=score,
            reason_codes=reason_codes,
            features=features,
        )