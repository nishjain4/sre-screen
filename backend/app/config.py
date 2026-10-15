"""Application settings (environment variables / .env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BACKEND_DIR / "config"

VERSION = "1.0.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # --- service ---------------------------------------------------------
    app_name: str = "Bot Svc SRE"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])
    api_key: str | None = None                      # if set, X-API-Key is required
    database_path: Path = BACKEND_DIR / "data" / "investigations.db"
    max_concurrent_investigations: int = 5

    # --- AI layer ----------------------------------------------------------
    llm_provider: Literal["bedrock", "offline"] = "bedrock"
    bedrock_model_id: str = "eu.amazon.nova-lite-v1:0"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3
    llm_max_context_chars: int = 16000           # follow-up chat context budget
    orchestrator: str = "native"

    # --- tool execution ------------------------------------------------------
    tool_timeout_seconds: float = 30.0
    skill_timeout_seconds: float = 120.0
    tool_concurrency: int = 6
    max_auto_skills: int = 8
    # --- Bedrock credentials ---------------------------------------------------
    aws_region: str = "us-east-1"
    aws_profile: str | None = None
    aws_access_key_id: SecretStr | None = None
    aws_secret_access_key: SecretStr | None = None
    aws_session_token: SecretStr | None = None

    # --- Gitea MCP / skills ------------------------------------------------------
    mcp_config_path: Path = CONFIG_DIR / "mcp_servers.yaml"
    gitea_url: str | None = None
    gitea_token: str | None = None
    gitea_owner: str | None = None
    gitea_repo: str | None = None
    templates_path: Path = CONFIG_DIR / "templates.yaml"

    @property
    def llm_configured(self) -> bool:
        return self.llm_provider == "bedrock" and bool(self.aws_region and self.bedrock_model_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
