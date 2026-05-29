"""DeepSeek API adapter with thinking (chain-of-thought) and reasoning_effort support.

DeepSeek uses an OpenAI-compatible chat completions endpoint.
Reference: https://api.deepseek.com
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Callable

import httpx

from llm.base import LLMAdapter, LLMResponse


class DeepSeekAdapter(LLMAdapter):
    """DeepSeek API client using httpx.

    Supports thinking mode (chain-of-thought reasoning) and
    reasoning_effort tuning.  DeepSeek models:
      - deepseek-v4-pro  (strongest reasoning)
      - deepseek-v4-flash (balanced speed/capability)
      - deepseek-chat     (general chat, deprecated)
      - deepseek-reasoner (reasoning-specialized, deprecated)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        timeout: int = 120,
        max_retries: int = 3,
    ) -> None:
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
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

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── public API ──────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        on_chunk: Callable[[str], None] | None = None,
        on_thought: Callable[[str], None] | None = None,
        thinking: bool = True,
        reasoning_effort: str = "medium",
    ) -> LLMResponse:
        messages = self._sanitize_messages(messages)

        if on_chunk is not None:
            return await self._chat_streaming_with_tools(
                messages, model, temperature, max_tokens,
                tools=tools, on_chunk=on_chunk,
                thinking=thinking, reasoning_effort=reasoning_effort,
                on_thought=on_thought,
            )

        payload = self._build_payload(
            messages, model, temperature, max_tokens,
            tools=tools, stream=False,
            thinking=thinking, reasoning_effort=reasoning_effort,
        )

        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                client = await self._get_client()
                resp = await client.post(
                    f"{self.base_url}/chat/completions", json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return self._parse_response(data)
            except httpx.HTTPStatusError as e:
                body = self._extract_error(e.response)
                last_error = f"HTTP {e.response.status_code}: {body[:800]}"
                if 400 <= e.response.status_code < 500:
                    raise RuntimeError(f"DeepSeekAdapter: {last_error}") from e
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
            except httpx.RequestError as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue

        raise RuntimeError(
            f"DeepSeekAdapter: all {self.max_retries + 1} attempts failed. "
            f"Last error: {last_error}"
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        thinking: bool = True,
        reasoning_effort: str = "medium",
        on_thought: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        messages = self._sanitize_messages(messages)
        payload = self._build_payload(
            messages, model, temperature, max_tokens,
            stream=True, thinking=thinking, reasoning_effort=reasoning_effort,
        )

        client = await self._get_client()
        async with client.stream(
            "POST", f"{self.base_url}/chat/completions", json=payload,
        ) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise RuntimeError(
                    f"DeepSeek request failed ({resp.status_code}): "
                    f"{body.decode('utf-8', errors='ignore')}"
                )

            async for data in self._iter_sse_deltas(resp):
                try:
                    delta = data["choices"][0].get("delta", {})
                    usage = data.get("usage")
                    if usage:
                        self.last_usage = usage
                    # Capture reasoning/thinking content
                    reasoning = delta.get("reasoning_content", "")
                    if reasoning and on_thought:
                        on_thought(reasoning)
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (KeyError, IndexError):
                    continue

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cleaned = []
        for msg in messages:
            if msg.get("tool_calls") and msg.get("content") is None:
                msg = {k: v for k, v in msg.items() if k != "content"}
            cleaned.append(msg)
        return cleaned

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
        thinking: bool = True,
        reasoning_effort: str = "medium",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
        if thinking:
            payload["thinking"] = {"type": "enabled"}
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        return payload

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "") or ""

        tool_calls: list[dict[str, Any]] = []
        for tc in msg.get("tool_calls", []):
            func = tc.get("function", {})
            try:
                args = json.loads(func.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append({
                "id": tc.get("id", ""),
                "name": func.get("name", ""),
                "arguments": args,
            })

        usage = data.get("usage")
        self.last_usage = usage
        return LLMResponse(content=content, raw=data, usage=usage, tool_calls=tool_calls)

    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            body = response.json()
            return body.get("error", {}).get("message", "")
        except ValueError:
            return response.text or "Unknown error"

    @staticmethod
    async def _iter_sse_deltas(response) -> AsyncGenerator[dict, None]:
        """Yield parsed SSE data dicts from a streaming response."""
        async for line in response.aiter_lines():
            if not line or not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                yield json.loads(data_str)
            except json.JSONDecodeError:
                continue

    async def _chat_streaming_with_tools(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]] | None,
        on_chunk: Callable[[str], None],
        thinking: bool = True,
        reasoning_effort: str = "medium",
        on_thought: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        """Stream via SSE, delivering chunks via on_chunk while accumulating
        tool-call deltas.  Only retries connection setup (before any chunk
        is yielded); once chunks flow, no further retries are attempted."""
        payload = self._build_payload(
            messages, model, temperature, max_tokens,
            tools=tools, stream=True,
            thinking=thinking, reasoning_effort=reasoning_effort,
        )

        content_parts: list[str] = []
        tool_call_deltas: dict[int, dict] = {}
        usage_data: dict = {}

        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                client = await self._get_client()
                async with client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for data in self._iter_sse_deltas(resp):
                        try:
                            delta = data["choices"][0].get("delta", {})

                            # Capture reasoning/thinking content
                            reasoning = delta.get("reasoning_content", "")
                            if reasoning and on_thought:
                                on_thought(reasoning)

                            content_delta = delta.get("content", "")
                            if content_delta:
                                content_parts.append(content_delta)
                                on_chunk(content_delta)

                            tc_deltas = delta.get("tool_calls", [])
                            for tc in tc_deltas:
                                idx = tc.get("index", 0)
                                if idx not in tool_call_deltas:
                                    tool_call_deltas[idx] = {
                                        "id": "", "name": "", "arguments_str": "",
                                    }
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

                break  # stream completed successfully
            except httpx.HTTPStatusError as e:
                body = self._extract_error(e.response)
                last_error = f"HTTP {e.response.status_code}: {body[:800]}"
                if 400 <= e.response.status_code < 500 and attempt == 0:
                    return await self._chat_non_streaming(
                        messages, model, temperature, max_tokens,
                        tools=tools, on_chunk=on_chunk,
                        thinking=thinking, reasoning_effort=reasoning_effort,
                    )
                if 400 <= e.response.status_code < 500:
                    raise RuntimeError(f"DeepSeekAdapter: {last_error}") from e
                if attempt < self.max_retries:
                    content_parts.clear()
                    tool_call_deltas.clear()
                    usage_data.clear()
                    continue
                raise RuntimeError(
                    f"DeepSeekAdapter streaming: all {self.max_retries + 1} "
                    f"attempts failed. Last error: {last_error}"
                ) from e
            except httpx.RequestError as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    content_parts.clear()
                    tool_call_deltas.clear()
                    usage_data.clear()
                    continue
                raise RuntimeError(
                    f"DeepSeekAdapter streaming: all {self.max_retries + 1} "
                    f"attempts failed. Last error: {last_error}"
                ) from e

        tool_calls: list[dict[str, Any]] = []
        for idx in sorted(tool_call_deltas.keys()):
            tc_data = tool_call_deltas[idx]
            try:
                args = json.loads(tc_data["arguments_str"])
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({
                "id": tc_data["id"],
                "name": tc_data["name"],
                "arguments": args,
            })

        self.last_usage = usage_data
        return LLMResponse(
            content="".join(content_parts),
            tool_calls=tool_calls,
            usage=usage_data,
            raw=usage_data,
        )

    async def _chat_non_streaming(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]] | None,
        on_chunk: Callable[[str], None] | None,
        thinking: bool = True,
        reasoning_effort: str = "medium",
    ) -> LLMResponse:
        """Fallback: non-streaming request, then deliver content via on_chunk."""
        payload = self._build_payload(
            messages, model, temperature, max_tokens,
            tools=tools, stream=False,
            thinking=thinking, reasoning_effort=reasoning_effort,
        )

        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}/chat/completions", json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        result = self._parse_response(data)
        if on_chunk and result.content:
            on_chunk(result.content)
        return result
