"""Framer module — structures raw user text into a FramedDecision or FramerClarification."""
from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic
from pydantic import ValidationError

from src.contracts import FramedDecision, FramerClarification, FramerOutput

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "framer.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

_MODEL = "claude-sonnet-4-6"
_MAX_RETRIES = 2


def _build_user_message(raw_input: str) -> str:
    return f"<user_decision>\n{raw_input.strip()}\n</user_decision>"


def _parse_response(text: str) -> FramerOutput:
    """Parse and validate a JSON response from the LLM into a typed contract."""
    # Strip markdown code fences if present
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
    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._client = client or anthropic.AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        )

    async def frame(self, raw_user_input: str) -> FramerOutput:
        messages: list[dict] = [
            {"role": "user", "content": _build_user_message(raw_user_input)}
        ]

        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            response = await self._client.messages.create(
                model=_MODEL,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=messages,
            )

            raw_text = response.content[0].text

            try:
                return _parse_response(raw_text)
            except (json.JSONDecodeError, ValidationError, KeyError, ValueError) as exc:
                last_error = exc
                if attempt < _MAX_RETRIES:
                    # Append the failed response and a correction prompt
                    messages.append({"role": "assistant", "content": raw_text})
                    messages.append(
                        {
                            "role": "user",
                            "content": _inject_validation_error(str(exc)),
                        }
                    )

        # After max retries, return a clarification asking user to rephrase
        raise FramerParseError(
            f"Framer failed to produce valid output after {_MAX_RETRIES + 1} attempts. "
            f"Last error: {last_error}"
        )


class FramerParseError(Exception):
    """Raised when the Framer cannot produce valid output after all retries."""
