"""Provider used when no LLM is configured: callers detect ``available=False`` and use heuristics."""
from __future__ import annotations

from app.llm.base import DEFAULT_MAX_COMPLETION_TOKENS, LLMError, LLMProvider, Message


class OfflineProvider(LLMProvider):
    name = "offline"
    model = "heuristic"

    @property
    def available(self) -> bool:
        return False

    async def complete(self, messages: list[Message], *, json_mode: bool = False, temperature: float = 0.2,
                       max_completion_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS,
                       model: str | None = None) -> str:
        raise LLMError("no LLM configured (set LLM_PROVIDER=bedrock and configure AWS credentials)")
