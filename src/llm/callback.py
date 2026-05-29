"""Callback adapter — wraps a user-provided async function as an LLMAdapter."""
from __future__ import annotations

from typing import Any, AsyncGenerator, Callable

from llm.base import LLMAdapter, LLMResponse


class CallbackAdapter(LLMAdapter):
    """Adapter that wraps a user-provided async chat function.

    The callback receives ``(messages, tools)`` and can return:
        - ``str`` — treated as the response content
        - ``LLMResponse`` — returned directly
        - An async generator yielding ``str`` chunks

    Extra keyword arguments (model, temperature, max_tokens, on_chunk)
    are accepted but only ``messages`` and ``tools`` are forwarded to
    the wrapped function.
    """

    def __init__(self, chat_fn: Callable) -> None:
        super().__init__()
        self._chat_fn = chat_fn

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        result = self._chat_fn(messages, tools)
        if hasattr(result, "__aiter__"):
            content = ""
            async for chunk in result:
                content += chunk
                if on_chunk:
                    on_chunk(chunk)
            return LLMResponse(content=content)

        content = await result
        if isinstance(content, LLMResponse):
            return content
        if on_chunk:
            on_chunk(content)
        return LLMResponse(content=content)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        on_thought: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        result = self._chat_fn(messages, None)
        if hasattr(result, "__aiter__"):
            async for chunk in result:
                yield chunk
        else:
            content = await result
            if isinstance(content, LLMResponse):
                yield content.content
            else:
                yield content
