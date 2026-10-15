"""Amazon Bedrock Converse API provider."""
from __future__ import annotations

import asyncio
import logging

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings
from app.llm.base import DEFAULT_MAX_COMPLETION_TOKENS, LLMError, LLMProvider, Message

logger = logging.getLogger(__name__)
_MAX_CONTINUATIONS = 8


class BedrockProvider(LLMProvider):
    name = "bedrock"

    def __init__(self, settings: Settings) -> None:
        if not settings.aws_region or not settings.bedrock_model_id:
            raise LLMError("Amazon Bedrock model ID and AWS region are required")

        self.model = settings.bedrock_model_id
        self.max_retries = settings.llm_max_retries
        access_key_id = settings.aws_access_key_id.get_secret_value() if settings.aws_access_key_id else None
        secret_access_key = (
            settings.aws_secret_access_key.get_secret_value()
            if settings.aws_secret_access_key
            else None
        )
        session_token = settings.aws_session_token.get_secret_value() if settings.aws_session_token else None
        session = boto3.Session(
            profile_name=settings.aws_profile or None,
            region_name=settings.aws_region,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
            aws_session_token=session_token or None,
        )
        self.client = session.client(
            "bedrock-runtime",
            config=Config(
                connect_timeout=10,
                read_timeout=settings.llm_timeout_seconds,
                retries={"max_attempts": self.max_retries, "mode": "standard"},
            ),
        )

    async def complete(
        self,
        messages: list[Message],
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_completion_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS,
        model: str | None = None,
    ) -> str:
        system = [{"text": message.content} for message in messages if message.role == "system"]
        if json_mode:
            system.append({"text": "Return only a valid JSON object. Do not include Markdown fences or prose."})

        request_messages = [
            {
                "role": "assistant" if message.role == "assistant" else "user",
                "content": [{"text": message.content}],
            }
            for message in messages
            if message.role != "system"
        ]
        original_messages = request_messages
        parts: list[str] = []
        for continuation in range(_MAX_CONTINUATIONS + 1):
            try:
                response = await asyncio.to_thread(
                    self.client.converse,
                    modelId=model or self.model,
                    messages=request_messages,
                    system=system,
                    inferenceConfig={
                        "maxTokens": max_completion_tokens,
                        "temperature": temperature,
                    },
                )
            except (BotoCoreError, ClientError) as exc:
                logger.warning("Amazon Bedrock request failed: %s", exc)
                raise LLMError(f"Amazon Bedrock request failed: {exc}") from exc

            stop_reason = response.get("stopReason")
            if stop_reason in {"guardrail_intervened", "content_filtered"}:
                raise LLMError(f"Amazon Bedrock response incomplete (stopReason={stop_reason}); "
                               "the response was filtered and cannot be completed automatically")
            if stop_reason not in {None, "end_turn", "stop_sequence", "max_tokens"}:
                raise LLMError(f"Amazon Bedrock response incomplete (stopReason={stop_reason})")
            output = response.get("output", {}).get("message", {}).get("content", [])
            text = "".join(block["text"] for block in output if "text" in block)
            if not text:
                raise LLMError("Amazon Bedrock returned no text content")
            parts.append(text)
            usage = response.get("usage", {})
            logger.debug(
                "Amazon Bedrock %s tokens in=%s out=%s",
                model or self.model, usage.get("inputTokens"), usage.get("outputTokens"),
            )
            if stop_reason != "max_tokens":
                return "".join(parts)
            if continuation == _MAX_CONTINUATIONS:
                raise LLMError("Amazon Bedrock response incomplete (stopReason=max_tokens) after "
                               f"{_MAX_CONTINUATIONS} continuations; no partial answer was accepted")
            logger.info("Amazon Bedrock output reached token limit; continuing response (%s/%s)",
                        continuation + 1, _MAX_CONTINUATIONS)
            # Keep the entire prefix, including partial JSON strings, for exact suffix continuation.
            request_messages = [
                *original_messages,
                {"role": "assistant", "content": [{"text": "".join(parts)}]},
                {"role": "user", "content": [{"text": (
                    "Your response reached the output token limit. Continue from the exact next character "
                    "after your preceding response. Return only the remaining suffix, not a new answer. "
                    "Do not repeat the prefix, restart JSON, or add Markdown fences. "
                    "Finish the original task, including any unfinished JSON string or object."
                )}]},
            ]
        raise AssertionError("unreachable Bedrock continuation state")
