"""Framer module — structures raw user text into a FramedDecision or FramerClarification."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from src.contracts import FramedDecision, FramerClarification, FramerOutput
from src.llm.client import LLMClient, Message, get_llm_client

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "framer.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()
_MAX_RETRIES = 2


def _build_user_message(raw_input: str) -> str:
    return f"<user_decision>\n{raw_input.strip()}\n</user_decision>"


def _parse_response(text: str) -> FramerOutput:
    content = text.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])

    data = json.loads(content)
    response_type = data.get("type")

    if response_type == "framed_decision":
        return FramedDecision.model_validate(data["data"])
    elif response_type == "clarification":
        return FramerClarification.model_validate(data["data"])
    else:
        raise ValueError(f"Unknown response type: {response_type!r}")


def _inject_validation_error(error: str) -> str:
    return (
        f"Your previous response failed schema validation: {error}\n\n"
        "Return corrected JSON. Do not include any other text."
    )


class Framer:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm or get_llm_client()

    async def frame(self, raw_user_input: str) -> FramerOutput:
        messages: list[Message] = [
            Message(role="user", content=_build_user_message(raw_user_input))
        ]

        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            raw_text = await self._llm.complete(
                system=_SYSTEM_PROMPT,
                messages=messages,
                max_tokens=1024,
            )

            try:
                return _parse_response(raw_text)
            except (json.JSONDecodeError, ValidationError, KeyError, ValueError) as exc:
                last_error = exc
                if attempt < _MAX_RETRIES:
                    messages.append(Message(role="assistant", content=raw_text))
                    messages.append(
                        Message(role="user", content=_inject_validation_error(str(exc)))
                    )

        raise FramerParseError(
            f"Framer failed to produce valid output after {_MAX_RETRIES + 1} attempts. "
            f"Last error: {last_error}"
        )


class FramerParseError(Exception):
    pass
