"""Global configuration for the Agent decision engine.

All configurable parameters live here, loadable from environment
variables or .env files via pydantic-settings.
"""
from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineConfig(BaseSettings):
    """Configuration for the Agent decision engine.

    Every parameter can be overridden via environment variable
    (uppercase, prefixed with AGENT_ENGINE_) or a .env file
    in the working directory.
    """
    model_config = SettingsConfigDict(
        env_prefix="AGENT_ENGINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- LLM --
    llm_provider: str = "deepseek"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-v4-pro"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096

    # -- Safety --
    max_steps: int = 50
    tool_whitelist: str = ""  # comma-separated; empty = allow all

    # -- Reflection --
    reflect_interval: int = 3

    # -- Memory --
    compress_trigger_tokens: int = 6000
    compress_target_tokens: int = 3000

    # -- Logging --
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"
    debug: bool = False

    # -- Workspace --
    workspace_dir: str = "./workspace"

    @property
    def tool_whitelist_set(self) -> set[str] | None:
        """Parse the comma-separated whitelist string into a set."""
        if not self.tool_whitelist.strip():
            return None
        return {t.strip() for t in self.tool_whitelist.split(",") if t.strip()}
