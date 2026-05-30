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
                body = await self._extract_error(e.response)
                last_error = f"HTTP {e.response.status_code}: {body[:800]}"
                self._log_api_error(e.response.status_code, body, payload, stage="non-stream")
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

        self.last_finish_reason = ""

        client = await self._get_client()
        async with client.stream(
            "POST", f"{self.base_url}/chat/completions", json=payload,
        ) as resp:
            if resp.status_code >= 400:
                body_bytes = await resp.aread()
                body = body_bytes.decode("utf-8", errors="ignore")
                self._log_api_error(resp.status_code, body, payload, stage="chat_stream")
                raise RuntimeError(
                    f"DeepSeek request failed ({resp.status_code}): {body}"
                )

            async for data in self._iter_sse_deltas(resp):
                try:
                    delta = data["choices"][0].get("delta", {})
                    usage = data.get("usage")
                    if usage:
                        self.last_usage = usage
                    finish_reason = data["choices"][0].get("finish_reason", "")
                    if finish_reason:
                        self.last_finish_reason = finish_reason
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
            arguments_raw = func.get("arguments", "{}")
            # Some providers (e.g. DeepSeek non-streaming) may return
            # ``arguments`` as an already-parsed dict instead of a JSON
            # string.  Handle both forms.
            if isinstance(arguments_raw, dict):
                args = arguments_raw
            elif isinstance(arguments_raw, str):
                try:
                    args = json.loads(arguments_raw)
                except json.JSONDecodeError:
                    args = {}
            else:
                args = {}
            tool_calls.append({
                "id": tc.get("id", ""),
                "name": func.get("name", ""),
                "arguments": args,
            })

        usage = data.get("usage")
        finish_reason = choice.get("finish_reason", "")
        self.last_usage = usage
        if finish_reason:
            self.last_finish_reason = finish_reason
        return LLMResponse(content=content, raw=data, usage=usage, tool_calls=tool_calls, finish_reason=finish_reason)

    @staticmethod
    async def _extract_error(response: httpx.Response) -> str:
        # Read body first — essential for streaming responses where
        # `.content` / `.text` / `.json()` all raise ResponseNotRead
        # before `.read()` or `.aread()` has been called.
        await response.aread()
        try:
            body = response.json()
            return body.get("error", {}).get("message", "")
        except ValueError:
            return response.text or f"HTTP {response.status_code}"

    @staticmethod
    def _compact_request(messages: list[dict], model: str,
                         tools: list[dict] | None = None,
                         stream: bool = True) -> str:
        """Build a compact, safe-to-log summary of an LLM request.

        Returns a multi-line string showing model, stream flag, message
        structure (role + content length per message), and tool names.
        Never includes message content or the API key header.
        """
        lines = [f"model={model} stream={stream}"]
        for i, msg in enumerate(messages):
            role = msg.get("role", "?")
            content = msg.get("content") or ""
            tc_count = len(msg.get("tool_calls", []))
            tc_id = msg.get("tool_call_id", "")
            name = msg.get("name", "")
            extras = []
            if tc_count:
                tc_names = [tc.get("function", {}).get("name", "?")
                            for tc in msg.get("tool_calls", [])]
                extras.append(f"tool_calls={tc_names}")
            if tc_id:
                extras.append(f"tool_call_id={tc_id}")
            if name:
                extras.append(f"name={name}")
            extra = (" " + " ".join(extras)) if extras else ""
            lines.append(
                f"  [{i}] {role}: {len(content)} chars{extra}"
            )
        if tools:
            tool_names = [t.get("name", t.get("function", {}).get("name", "?"))
                          for t in tools]
            lines.append(f"  tools={tool_names}")
        return "\n".join(lines)

    def _log_api_error(self, status: int, response_body: str,
                       payload: dict, stage: str = "stream") -> None:
        """Log a compact summary of a failed API request + response at ERROR level.

        Safe: only logs message structure (roles + lengths), never content or keys.
        """
        from loguru import logger as _logger
        messages = payload.get("messages", [])
        model = payload.get("model", "?")
        tools_raw = payload.get("tools", [])
        tools_spec: list[dict] = []
        for t in tools_raw:
            if "function" in t:
                tools_spec.append(t["function"])
            else:
                tools_spec.append(t)
        stream = payload.get("stream", False)
        req_summary = self._compact_request(messages, model, tools_spec, stream)
        _logger.error(
            "LLM API error [{}] HTTP {}\n── Request ──\n{}\n── Response body ──\n{}",
            stage, status, req_summary, response_body[:2000],
        )

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
        from loguru import logger as _tc_logger

        payload = self._build_payload(
            messages, model, temperature, max_tokens,
            tools=tools, stream=True,
            thinking=thinking, reasoning_effort=reasoning_effort,
        )

        content_parts: list[str] = []
        tool_call_deltas: dict[int, dict] = {}
        usage_data: dict = {}
        had_reasoning: bool = False  # True if any reasoning_content delta seen
        finish_reason: str = ""

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
                            if reasoning:
                                had_reasoning = True
                                if on_thought:
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
                                    _tc_logger.debug(
                                        "SSE tool_call[{}] start: raw_delta_keys={}",
                                        idx, list(tc.keys()),
                                    )
                                if "id" in tc and tc["id"]:
                                    tool_call_deltas[idx]["id"] = tc["id"]
                                func = tc.get("function", {})
                                if "name" in func and func["name"]:
                                    tool_call_deltas[idx]["name"] = func["name"]
                                if "arguments" in func and func["arguments"]:
                                    tool_call_deltas[idx]["arguments_str"] += func["arguments"]

                            fr = data["choices"][0].get("finish_reason", "")
                            if fr:
                                finish_reason = fr

                            if data.get("usage"):
                                usage_data = data["usage"]
                        except (KeyError, IndexError):
                            continue

                # ── Streaming completed successfully ──

                # Assemble tool calls from accumulated SSE deltas.
                content = "".join(content_parts)
                tool_calls: list[dict[str, Any]] = []
                malformed_args: list[int] = []
                for idx in sorted(tool_call_deltas.keys()):
                    tc_data = tool_call_deltas[idx]
                    try:
                        args = json.loads(tc_data["arguments_str"])
                    except json.JSONDecodeError:
                        args = {}
                        if tc_data["name"] and tc_data["arguments_str"]:
                            malformed_args.append(idx)
                        _tc_logger.warning(
                            "SSE tool_call[{}] bad JSON args_str ({!r}…), defaulting to {{}}",
                            idx, tc_data["arguments_str"][:200],
                        )
                    _tc_logger.debug(
                        "SSE tool_call[{}] final: id={!r} name={!r} args_str_len={} args_keys={}",
                        idx, tc_data["id"], tc_data["name"],
                        len(tc_data["arguments_str"]), list(args.keys()) if isinstance(args, dict) else "?",
                    )
                    tool_calls.append({
                        "id": tc_data["id"],
                        "name": tc_data["name"],
                        "arguments": args,
                    })

                # Retry 1: thinking consumed all tokens → retry without thinking.
                if (
                    had_reasoning
                    and not content
                    and not tool_calls
                    and attempt == 0
                    and thinking
                ):
                    _tc_logger.warning(
                        "Model produced reasoning but no content/tool_calls — "
                        "thinking likely consumed all {} tokens. "
                        "Retrying with thinking=disabled.",
                        max_tokens,
                    )
                    self.last_finish_reason = "thinking_exhausted"
                    content_parts.clear()
                    tool_call_deltas.clear()
                    usage_data.clear()
                    had_reasoning = False
                    finish_reason = ""
                    thinking = False
                    reasoning_effort = ""
                    payload = self._build_payload(
                        messages, model, temperature, max_tokens,
                        tools=tools, stream=True,
                        thinking=False, reasoning_effort="",
                    )
                    continue

                # Retry 2: malformed tool-call JSON → retry non-streaming.
                if malformed_args and attempt == 0:
                    _tc_logger.warning(
                        "SSE tool_call malformed JSON for indices {} — retrying non-streaming",
                        malformed_args,
                    )
                    return await self._chat_non_streaming(
                        messages, model, temperature, max_tokens,
                        tools=tools, on_chunk=on_chunk,
                        thinking=thinking, reasoning_effort=reasoning_effort,
                    )

                self.last_usage = usage_data
                self.last_finish_reason = finish_reason
                return LLMResponse(
                    content=content,
                    tool_calls=tool_calls,
                    usage=usage_data,
                    raw=usage_data,
                    finish_reason=finish_reason,
                )
                # ── End of successful streaming path ──

            except httpx.HTTPStatusError as e:
                body = await self._extract_error(e.response)
                last_error = f"HTTP {e.response.status_code}: {body[:800]}"
                self._log_api_error(e.response.status_code, body, payload, stage="stream")
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
                    finish_reason = ""
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
                    finish_reason = ""
                    continue
                raise RuntimeError(
                    f"DeepSeekAdapter streaming: all {self.max_retries + 1} "
                    f"attempts failed. Last error: {last_error}"
                ) from e

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
        from loguru import logger as _ns_logger

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

        # ── Raw diagnostics: log the non-streaming response structure ──
        raw_msg = data.get("choices", [{}])[0].get("message", {})
        raw_tool_calls = raw_msg.get("tool_calls", [])
        if raw_tool_calls:
            for i, tc in enumerate(raw_tool_calls):
                fn = tc.get("function", {})
                raw_args = fn.get("arguments", "")
                _ns_logger.debug(
                    "non-stream RAW tool_call[{}]: name={!r} "
                    "arguments_type={} arguments_len={} arguments_repr={!r}",
                    i, fn.get("name", ""),
                    type(raw_args).__name__,
                    len(raw_args) if isinstance(raw_args, (str, dict)) else 0,
                    str(raw_args)[:300],
                )
        else:
            _ns_logger.debug(
                "non-stream RAW: content={} chars, tool_calls_count=0, "
                "finish_reason={}",
                len(raw_msg.get("content", "") or ""),
                data.get("choices", [{}])[0].get("finish_reason", ""),
            )

        result = self._parse_response(data)

        # Debug: log non-streaming tool call details for diagnostics
        if result.tool_calls:
            for i, tc in enumerate(result.tool_calls):
                _ns_logger.debug(
                    "non-stream tool_call[{}]: name={!r} args_keys={} args_total_chars={}",
                    i, tc["name"], list(tc["arguments"].keys()),
                    sum(len(str(v)) for v in tc["arguments"].values()),
                )
        else:
            _ns_logger.debug(
                "non-stream response: content={} chars, no tool_calls",
                len(result.content),
            )

        if on_chunk and result.content:
            on_chunk(result.content)
        return result
