"""Mock adapter for testing — echoes the last user message."""
from __future__ import annotations

from typing import Any, AsyncGenerator, Callable

from llm.base import LLMAdapter, LLMResponse


class MockAdapter(LLMAdapter):
    """Echoes the last user message as a response. For testing without API keys."""

    def __init__(self) -> None:
        super().__init__()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        on_chunk: Callable[[str], None] | None = None,
        on_thought: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = str(msg.get("content", ""))
                break
        content = f"Mock response: {last_user}".strip()
        return LLMResponse(content=content, tool_calls=[], raw={"mock": True})

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        on_thought: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        response = await self.chat(messages, model, temperature, max_tokens)
        for chunk in response.content.split():
            yield chunk + " "
