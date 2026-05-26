from __future__ import annotations

from core.models import LLMConfig
from llm.base import LLMAdapter, MockAdapter
from llm.openai_compat import OpenAICompatAdapter


class LLMAdapterFactory:
    @staticmethod
    def create(config: LLMConfig, api_key: str) -> LLMAdapter:
        provider = (config.provider or "").lower()
        if provider in {"openai", "openai_compat", "custom"}:
            if not api_key:
                return MockAdapter()
            return OpenAICompatAdapter(
                base_url=config.base_url,
                api_key=api_key,
                timeout=config.timeout_seconds,
            )
        if provider == "mock":
            return MockAdapter()
        raise ValueError(f"Unsupported provider: {config.provider}")
