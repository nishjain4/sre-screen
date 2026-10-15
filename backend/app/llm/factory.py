"""Select the LLM provider from settings."""
from __future__ import annotations

import logging

from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.offline_provider import OfflineProvider

logger = logging.getLogger(__name__)


def create_llm(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "bedrock" and settings.llm_configured:
        from app.llm.bedrock_provider import BedrockProvider

        return BedrockProvider(settings)
    if settings.llm_provider == "bedrock":
        logger.warning("Bedrock model or AWS region not set - using offline heuristic analysis")
    return OfflineProvider()
