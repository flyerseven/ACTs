"""LLM adapter abstraction for the Agent decision engine.

Provides:
- LLMAdapter (ABC): abstract interface for any LLM backend
- LLMResponse: unified response type
- OpenAIAdapter: built-in httpx-based OpenAI-compatible client
- CallbackAdapter: wraps a user-provided async function
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Callable

import httpx
from loguru import logger

from agent_engine.types import ToolCallRequest


class LLMResponse:
    """Unified response from any LLM backend."""

    __slots__ = ("content", "tool_calls", "usage")

    def __init__(self, content: str = "", tool_calls: list[ToolCallRequest] | None = None, usage: dict | None = None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage = usage or {}


class LLMAdapter(ABC):
    """Abstract interface for LLM backends.

    Implement this to support any LLM provider. Only `chat()` is
    required; `chat_stream()` defaults to yielding the full response.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Send messages and return a complete response."""
        ...

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens. Default implementation yields
        the full response from chat() as a single chunk."""
        resp = await self.chat(messages, tools)
        yield resp.content


class CallbackAdapter(LLMAdapter):
    """Adapter that wraps a user-provided async chat function.

    The callback can either return a string or yield string chunks.
    """

    def __init__(self, chat_fn: Callable):
        self._chat_fn = chat_fn

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        result = self._chat_fn(messages, tools)
        if hasattr(result, "__aiter__"):
            # It's an async generator — collect all chunks
            content = ""
            async for chunk in result:
                content += chunk
            return LLMResponse(content=content)
        content = await result
        return LLMResponse(content=content)

    async def chat_stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncGenerator[str, None]:
        result = self._chat_fn(messages, tools)
        if hasattr(result, "__aiter__"):
            async for chunk in result:
                yield chunk
        else:
            content = await result
            yield content


class OpenAIAdapter(LLMAdapter):
    """Built-in OpenAI-compatible API client using httpx.

    Supports any OpenAI-compatible endpoint (OpenAI, Azure, local LLMs).
    Includes retry logic for transient errors.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        max_retries: int = 3,
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
            payload["tool_choice"] = "auto"

        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                client = await self._get_client()
                resp = await client.post(f"{self.base_url}/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()

                choice = data["choices"][0]
                msg = choice["message"]
                content = msg.get("content", "") or ""

                tool_calls: list[ToolCallRequest] = []
                raw_tool_calls = msg.get("tool_calls", [])
                if raw_tool_calls:
                    import json
                    for tc in raw_tool_calls:
                        func = tc["function"]
                        try:
                            args = json.loads(func["arguments"])
                        except json.JSONDecodeError:
                            args = {}
                        tool_calls.append(ToolCallRequest(
                            id=tc.get("id", ""),
                            name=func["name"],
                            arguments=args,
                        ))

                return LLMResponse(
                    content=content,
                    tool_calls=tool_calls,
                    usage=data.get("usage", {}),
                )
            except httpx.HTTPStatusError as e:
                last_error = str(e)
                logger.warning(f"OpenAI HTTP error (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries:
                    continue
            except httpx.RequestError as e:
                last_error = str(e)
                logger.warning(f"OpenAI request error (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries:
                    continue

        raise RuntimeError(f"OpenAIAdapter: all {self.max_retries + 1} attempts failed. Last error: {last_error}")

    async def chat_stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncGenerator[str, None]:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]

        client = await self._get_client()
        async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    import json
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
