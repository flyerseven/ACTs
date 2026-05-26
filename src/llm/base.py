from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncGenerator


@dataclass
class LLMResponse:
    content: str
    raw: dict[str, Any]
    usage: dict[str, int] | None = None


class LLMAdapter(ABC):
    def __init__(self) -> None:
        self.last_usage: dict[str, int] | None = None

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        raise NotImplementedError


class MockAdapter(LLMAdapter):
    def __init__(self) -> None:
        super().__init__()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = str(msg.get("content", ""))
                break
        content = f"Mock response: {last_user}".strip()
        return LLMResponse(content=content, raw={"mock": True})

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
    ):
        response = await self.chat(messages, model, temperature, max_tokens)
        for chunk in response.content.split():
            yield chunk + " "
