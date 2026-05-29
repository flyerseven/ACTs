from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable


@dataclass
class LLMResponse:
    """Unified response from any LLM backend.

    tool_calls uses a plain dict format:
        [{"id": "call_1", "name": "search", "arguments": {"q": "test"}}]
    """
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMAdapter(ABC):
    """Abstract interface for LLM backends.

    Implement this to support any LLM provider. Both ``chat()`` and
    ``chat_stream()`` are required.
    """

    def __init__(self) -> None:
        self.last_usage: dict[str, int] | None = None

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        """Send messages and return a complete response.

        If on_chunk is provided, it is called with each text chunk
        as it arrives (streaming), while still returning the complete
        response including tool calls at the end.
        """
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        on_thought: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens one at a time.

        If *on_thought* is provided, it is called with reasoning/thinking
        text as it arrives (supported by providers like DeepSeek that
        return ``reasoning_content`` in SSE deltas).
        """
        ...

    async def close(self) -> None:
        """Optional cleanup. Called to release resources (e.g. httpx client)."""
        pass
