from __future__ import annotations

from core.models import LLMConfig
from llm.base import LLMAdapter
from llm.deepseek import DeepSeekAdapter
from llm.mock import MockAdapter


class LLMAdapterFactory:
    @staticmethod
    def create(config: LLMConfig, api_key: str) -> LLMAdapter:
        provider = (config.provider or "").lower()
        if provider == "deepseek":
            if not api_key:
                return MockAdapter()
            return DeepSeekAdapter(
                api_key=api_key,
                base_url=config.base_url or "https://api.deepseek.com",
                timeout=config.timeout_seconds,
            )
        if provider == "mock":
            return MockAdapter()
        raise ValueError(f"Unsupported provider: {config.provider}")
