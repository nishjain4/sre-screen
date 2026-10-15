"""LLM provider interface.

The orchestration layer only depends on ``LLMProvider.complete``; switching vendors
(or using a framework's model wrapper) means adding one provider class.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

DEFAULT_MAX_COMPLETION_TOKENS = 4096


class LLMError(Exception):
    pass


@dataclass
class Message:
    role: Literal["system", "user", "assistant"]
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


class LLMProvider(ABC):
    name: str = "llm"
    model: str = ""

    @property
    def available(self) -> bool:
        """False for the offline provider: callers fall back to heuristics."""
        return True

    @abstractmethod
    async def complete(self, messages: list[Message], *, json_mode: bool = False, temperature: float = 0.2,
                       max_completion_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS,
                       model: str | None = None) -> str: ...

    async def complete_json(self, messages: list[Message], **kwargs: Any) -> dict[str, Any]:
        text = await self.complete(messages, json_mode=True, **kwargs)
        return parse_json(text)

    async def aclose(self) -> None:
        return None

    @property
    def label(self) -> str:
        return f"{self.name}:{self.model}" if self.model else self.name


def parse_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from model output (tolerates code fences / leading prose)."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise LLMError("model did not return JSON")
        try:
            value = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"invalid JSON from model: {exc}") from exc
    if not isinstance(value, dict):
        raise LLMError("expected a JSON object")
    return value
