"""Tool for pausing a turn until the user answers."""

import json
from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import ArraySchema, StringSchema, tool_parameters_schema

STRUCTURED_BUTTON_CHANNELS = frozenset({"telegram", "websocket"})


class AskUserInterrupt(BaseException):
    """Internal signal: the runner should stop and wait for user input."""

    def __init__(self, question: str, options: list[str] | None = None) -> None:
        self.question = question
        self.options = [str(option) for option in (options or []) if str(option)]
        super().__init__(question)


@tool_parameters(
    tool_parameters_schema(
        question=StringSchema(
            "The question to ask before continuing. Use this only when the task needs the user's answer."
        ),
        options=ArraySchema(
            StringSchema("A possible answer label"),
            description="Optional choices. The user may still reply with free text.",
        ),
        required=["question"],
    )
)
class AskUserTool(Tool):
    """Ask the user a blocking question."""

    @property
    def name(self) -> str:
        return "ask_user"

    @property
    def description(self) -> str:
        return (
            "Pause and ask the user a question when their answer is required to continue. "
            "Use options for likely answers; the user's reply, typed or selected, is returned as the tool result. "
            "For non-blocking notifications or buttons, use the message tool instead."
        )

    @property
    def exclusive(self) -> bool:
        return True

    async def execute(self, question: str, options: list[str] | None = None, **_: Any) -> Any:
        raise AskUserInterrupt(question=question, options=options)


def _tool_call_name(tool_call: dict[str, Any]) -> str:
    function = tool_call.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return function["name"]
    name = tool_call.get("name")
    return name if isinstance(name, str) else ""


def _tool_call_arguments(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = tool_call.get("function")
    raw = function.get("arguments") if isinstance(function, dict) else tool_call.get("arguments")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def pending_ask_user_id(history: list[dict[str, Any]]) -> str | None:
    pending: dict[str, str] = {}
    for message in history:
        if message.get("role") == "assistant":
            for tool_call in message.get("tool_calls") or []:
                if isinstance(tool_call, dict) and isinstance(tool_call.get("id"), str):
                    pending[tool_call["id"]] = _tool_call_name(tool_call)
        elif message.get("role") == "tool":
            tool_call_id = message.get("tool_call_id")
            if isinstance(tool_call_id, str):
                pending.pop(tool_call_id, None)
    for tool_call_id, name in reversed(pending.items()):
        if name == "ask_user":
            return tool_call_id
    return None


def ask_user_tool_result_messages(
    system_prompt: str,
    history: list[dict[str, Any]],
    tool_call_id: str,
    content: str,
) -> list[dict[str, Any]]:
    history = _history_without_visible_ask_user_echo(history, tool_call_id)
    return [
        {"role": "system", "content": system_prompt},
        *history,
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": "ask_user",
            "content": content,
        },
    ]


def _history_without_visible_ask_user_echo(
    history: list[dict[str, Any]],
    tool_call_id: str,
) -> list[dict[str, Any]]:
    ask_index: int | None = None
    question = ""
    options: list[str] = []

    for index, message in enumerate(history):
        if message.get("role") != "assistant":
            continue
        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            if tool_call.get("id") != tool_call_id or _tool_call_name(tool_call) != "ask_user":
                continue
            ask_index = index
            arguments = _tool_call_arguments(tool_call)
            raw_question = arguments.get("question")
            question = str(raw_question).strip() if isinstance(raw_question, str) else ""
            raw_options = arguments.get("options")
            if isinstance(raw_options, list):
                options = [str(option) for option in raw_options if isinstance(option, str)]
            break
        if ask_index is not None:
            break

    if ask_index is None or ask_index + 1 >= len(history):
        return history

    candidate = history[ask_index + 1]
    if _is_visible_ask_user_echo(candidate, question, options):
        return [*history[: ask_index + 1], *history[ask_index + 2 :]]
    return history


def _is_visible_ask_user_echo(
    message: dict[str, Any],
    question: str,
    options: list[str],
) -> bool:
    if message.get("role") != "assistant" or message.get("tool_calls"):
        return False

    content = message.get("content")
    if not isinstance(content, str):
        return False

    normalized = content.strip()
    if not normalized:
        return False

    normalized_question = question.strip()
    if normalized_question and normalized == normalized_question:
        return True

    if not options:
        return False

    numbered = "\n".join(
        f"{index}. {option}" for index, option in enumerate(options, 1)
    )
    fallback = f"{normalized_question}\n\n{numbered}" if normalized_question else numbered
    return normalized == fallback


def ask_user_options_from_messages(messages: list[dict[str, Any]]) -> list[str]:
    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        for tool_call in reversed(message.get("tool_calls") or []):
            if not isinstance(tool_call, dict) or _tool_call_name(tool_call) != "ask_user":
                continue
            options = _tool_call_arguments(tool_call).get("options")
            if isinstance(options, list):
                return [str(option) for option in options if isinstance(option, str)]
    return []


def ask_user_outbound(
    content: str | None,
    options: list[str],
    channel: str,
) -> tuple[str | None, list[list[str]]]:
    if not options:
        return content, []
    if channel in STRUCTURED_BUTTON_CHANNELS:
        return content, [options]
    option_text = "\n".join(f"{index}. {option}" for index, option in enumerate(options, 1))
    return f"{content}\n\n{option_text}" if content else option_text, []
