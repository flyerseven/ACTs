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
        on_chunk: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        """Send messages and return a complete response.

        If on_chunk is provided, it is called with each text chunk
        as it arrives (streaming), while still returning the complete
        response with tool calls at the end.
        """
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

    async def chat(self, messages: list[dict], tools: list[dict] | None = None, on_chunk: Callable[[str], None] | None = None) -> LLMResponse:
        result = self._chat_fn(messages, tools)
        if hasattr(result, "__aiter__"):
            content = ""
            async for chunk in result:
                content += chunk
                if on_chunk:
                    on_chunk(chunk)
            return LLMResponse(content=content)
        content = await result
        if on_chunk:
            on_chunk(content)
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

    async def chat(self, messages: list[dict], tools: list[dict] | None = None, on_chunk: Callable[[str], None] | None = None) -> LLMResponse:
        if on_chunk is not None:
            return await self._chat_streaming_with_tools(messages, tools, on_chunk)

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

    async def _iter_sse_deltas(self, response) -> AsyncGenerator[dict, None]:
        """Yield parsed SSE data dicts from a streaming response.

        Handles SSE line format: skips non-``data:`` lines, handles the
        ``[DONE]`` sentinel, and silently skips malformed JSON lines.
        """
        import json
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                yield data
            except json.JSONDecodeError:
                continue

    async def _chat_streaming_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        on_chunk: Callable[[str], None],
    ) -> LLMResponse:
        """Stream response chunks via on_chunk while accumulating full content
        and extracting tool calls from streamed deltas.

        Note: Unlike the non-streaming ``chat()`` method, automatic retries
        are intentionally NOT performed once chunks start flowing through
        ``on_chunk``, because partial content may have already been delivered
        to the consumer and cannot be replayed.  Only the initial connection
        setup (before any chunk is yielded) is retried up to ``max_retries``.
        """
        import json

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
            payload["tool_choice"] = "auto"

        content_parts: list[str] = []
        tool_call_deltas: dict[int, dict] = {}
        usage_data: dict = {}

        # Retry initial connection setup — safe because no chunks have been
        # yielded to the consumer yet.
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                client = await self._get_client()
                async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as resp:
                    resp.raise_for_status()
                    # Connection established; process stream.  No further
                    # retries beyond this point because on_chunk may already
                    # have delivered content to the caller.
                    async for data in self._iter_sse_deltas(resp):
                        try:
                            delta = data["choices"][0].get("delta", {})

                            content_delta = delta.get("content", "")
                            if content_delta:
                                content_parts.append(content_delta)
                                on_chunk(content_delta)

                            tc_deltas = delta.get("tool_calls", [])
                            for tc in tc_deltas:
                                idx = tc.get("index", 0)
                                if idx not in tool_call_deltas:
                                    tool_call_deltas[idx] = {"id": "", "name": "", "arguments_str": ""}
                                if "id" in tc and tc["id"]:
                                    tool_call_deltas[idx]["id"] = tc["id"]
                                func = tc.get("function", {})
                                if "name" in func and func["name"]:
                                    tool_call_deltas[idx]["name"] = func["name"]
                                if "arguments" in func and func["arguments"]:
                                    tool_call_deltas[idx]["arguments_str"] += func["arguments"]

                            if data.get("usage"):
                                usage_data = data["usage"]
                        except (KeyError, IndexError):
                            continue

                # Stream completed successfully — exit retry loop
                break
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                last_error = str(e)
                logger.warning(f"OpenAI streaming error (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries:
                    # Reset accumulators for retry
                    content_parts.clear()
                    tool_call_deltas.clear()
                    usage_data.clear()
                    continue
                raise RuntimeError(
                    f"OpenAIAdapter streaming: all {self.max_retries + 1} attempts failed. "
                    f"Last error: {last_error}"
                )

        tool_calls: list[ToolCallRequest] = []
        for idx in sorted(tool_call_deltas.keys()):
            tc_data = tool_call_deltas[idx]
            try:
                args = json.loads(tc_data["arguments_str"])
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCallRequest(
                id=tc_data["id"],
                name=tc_data["name"],
                arguments=args,
            ))

        return LLMResponse(
            content="".join(content_parts),
            tool_calls=tool_calls,
            usage=usage_data,
        )

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
            async for data in self._iter_sse_deltas(resp):
                try:
                    delta = data["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (KeyError, IndexError):
                    continue

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
