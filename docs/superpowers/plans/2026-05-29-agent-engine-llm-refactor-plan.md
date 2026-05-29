# Agent Engine LLM Adapter Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify LLM adapters for agent_engine into `src/llm/` with per-provider adapter pattern, starting with DeepSeek.

**Architecture:** Enhance `src/llm/base.py` with `on_chunk` streaming callback and tool-call dict format. Move MockAdapter and CallbackAdapter to separate files. Merge agent_engine's richer DeepSeekAdapter streaming implementation into `src/llm/deepseek.py`. Delete `agent_engine/llm.py` and update all consumers to import from `src.llm`.

**Tech Stack:** Python 3.12+, httpx, Pydantic, pytest, pytest-asyncio

---

### Task 1: Enhance src/llm/base.py

**Files:**
- Modify: `src/llm/base.py`

**Purpose:** Update the LLMAdapter ABC and LLMResponse to support `on_chunk` streaming callback and dict-format tool_calls. Split MockAdapter out to its own file.

- [ ] **Step 1: Rewrite src/llm/base.py**

Replace the entire file:

```python
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

    Implement this to support any LLM provider. Only ``chat()`` is
    required; ``chat_stream()`` defaults to yielding the full response.
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
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens one at a time."""
        ...

    async def close(self) -> None:
        """Optional cleanup. Called to release resources (e.g. httpx client)."""
        pass
```

- [ ] **Step 2: Commit**

```bash
git add src/llm/base.py
git commit -m "refactor: enhance LLMAdapter ABC — add on_chunk, consistent tool_calls dict format"
```

---

### Task 2: Create src/llm/mock.py

**Files:**
- Create: `src/llm/mock.py`

**Purpose:** Split MockAdapter out of base.py to follow the one-file-per-adapter pattern.

- [ ] **Step 1: Write src/llm/mock.py**

```python
"""Mock adapter for testing — echoes the last user message."""
from __future__ import annotations

from typing import Any, AsyncGenerator

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
    ) -> AsyncGenerator[str, None]:
        response = await self.chat(messages, model, temperature, max_tokens)
        for chunk in response.content.split():
            yield chunk + " "
```

- [ ] **Step 2: Remove MockAdapter from src/llm/base.py**

Remove the MockAdapter class from `src/llm/base.py` (lines 43-73 of the original). The file now contains only `LLMResponse` and `LLMAdapter`.

- [ ] **Step 3: Commit**

```bash
git add src/llm/mock.py src/llm/base.py
git commit -m "refactor: split MockAdapter into src/llm/mock.py"
```

---

### Task 3: Create src/llm/callback.py

**Files:**
- Create: `src/llm/callback.py`

**Purpose:** Move CallbackAdapter from agent_engine/llm.py to src/llm/ for unified location. Used by tests to inject fake LLM behavior.

- [ ] **Step 1: Write src/llm/callback.py**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add src/llm/callback.py
git commit -m "feat: add CallbackAdapter to src/llm/callback.py"
```

---

### Task 4: Rewrite src/llm/deepseek.py

**Files:**
- Modify: `src/llm/deepseek.py`

**Purpose:** Replace the existing simple implementation with the richer agent_engine version that supports streaming with tool-call delta accumulation, on_chunk callbacks, 4xx fallback, and sanitized messages.

- [ ] **Step 1: Rewrite src/llm/deepseek.py with full streaming + tool support**

```python
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
        thinking: bool = True,
        reasoning_effort: str = "medium",
    ) -> LLMResponse:
        messages = self._sanitize_messages(messages)

        if on_chunk is not None:
            return await self._chat_streaming_with_tools(
                messages, model, temperature, max_tokens,
                tools=tools, on_chunk=on_chunk,
                thinking=thinking, reasoning_effort=reasoning_effort,
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
        messages = self._sanitize_messages(messages)
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

        return LLMResponse(
            content="".join(content_parts),
            tool_calls=tool_calls,
            usage=usage_data,
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

        choice = data["choices"][0]
        msg = choice["message"]
        content = msg.get("content", "") or ""

        if on_chunk and content:
            on_chunk(content)

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
```

- [ ] **Step 2: Commit**

```bash
git add src/llm/deepseek.py
git commit -m "refactor: merge agent_engine DeepSeekAdapter enhancements into src/llm/deepseek.py"
```

---

### Task 5: Update src/llm/factory.py

**Files:**
- Modify: `src/llm/factory.py`

**Purpose:** Update imports to use the new mock.py location. No other logic changes needed.

- [ ] **Step 1: Fix import in src/llm/factory.py**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add src/llm/factory.py
git commit -m "refactor: update factory imports to use src/llm/mock.py"
```

---

### Task 6: Update src/llm/__init__.py

**Files:**
- Modify: `src/llm/__init__.py`

**Purpose:** Add public re-exports for the new modules.

- [ ] **Step 1: Write src/llm/__init__.py**

```python
from llm.base import LLMAdapter, LLMResponse
from llm.callback import CallbackAdapter
from llm.deepseek import DeepSeekAdapter
from llm.factory import LLMAdapterFactory
from llm.mock import MockAdapter

__all__ = [
    "LLMAdapter",
    "LLMResponse",
    "CallbackAdapter",
    "DeepSeekAdapter",
    "LLMAdapterFactory",
    "MockAdapter",
]
```

- [ ] **Step 2: Commit**

```bash
git add src/llm/__init__.py
git commit -m "refactor: update src/llm/__init__.py public exports"
```

---

### Task 7: Update agent_engine/config.py

**Files:**
- Modify: `agent_engine/config.py`

**Purpose:** Rename the confusing `openai_*` fields to generic `llm_*` names, add temperature/max_tokens.

- [ ] **Step 1: Rewrite the LLM section of agent_engine/config.py**

Replace the `# -- LLM --` section (lines 27-30) with:

```python
    # -- LLM --
    llm_provider: str = "deepseek"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-v4-pro"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
```

Keep all other sections unchanged.

- [ ] **Step 2: Commit**

```bash
git add agent_engine/config.py
git commit -m "refactor: rename EngineConfig LLM fields — openai_* → llm_*"
```

---

### Task 8: Update agent_engine/engine.py

**Files:**
- Modify: `agent_engine/engine.py`

**Purpose:** Switch imports from `agent_engine.llm` to `src.llm.base`. Update `self.llm.chat()` calls to pass model/temperature/max_tokens from config. Adapt tool_calls access from attribute (.name) to dict (["name"]) access.

- [ ] **Step 1: Update imports**

Line 23: Change `from agent_engine.llm import LLMAdapter` to `from llm.base import LLMAdapter`.

- [ ] **Step 2: Update the THINK phase — chat() call**

Replace the `response = await self.llm.chat(context, tool_schemas, on_chunk=on_thought_chunk)` call (line ~236) with:

```python
                response = await self.llm.chat(
                    context,
                    model=self.config.llm_model,
                    temperature=self.config.llm_temperature,
                    max_tokens=self.config.llm_max_tokens,
                    tools=tool_schemas,
                    on_chunk=on_thought_chunk,
                )
```

- [ ] **Step 3: Update tool_calls serialization for memory**

Replace the tool_calls_dicts block (lines ~240-245) with dict access:

```python
                tool_calls_dicts = None
                if response.tool_calls:
                    tool_calls_dicts = [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                        for tc in response.tool_calls
                    ]
```

- [ ] **Step 4: Update ACT phase tool_calls iteration**

Replace `tc_req.name` → `tc_req["name"]`, `tc_req.arguments` → `tc_req["arguments"]`, `tc_req.id` → `tc_req["id"]` throughout the ACT block (lines ~286-329). The changes are:

```python
            if response.tool_calls:
                step.phase = "act"
                for tc_req in response.tool_calls:
                    if not self.safety.check_tool(tc_req["name"]):
                        logger.warning(f"Tool '{tc_req['name']}' blocked by safety")
                        self._debug_phase("ACT", f"{tc_req['name']}: BLOCKED", is_sub=True)
                        continue

                    if not self.safety._run_hooks("before_action", tc_req["name"], tc_req["arguments"]):
                        self._debug_phase("ACT", f"{tc_req['name']}: hook blocked", is_sub=True)
                        continue

                    args_preview = str(tc_req["arguments"])[:80]
                    t_tool = time.monotonic()
                    tool_call = await self.tools.call(tc_req["name"], tc_req["arguments"])
                    t_tool = time.monotonic() - t_tool
                    step.tool_call = tool_call

                    self.observer.emit(Event("tool_call", {
                        "index": step_index,
                        "name": tc_req["name"],
                        "arguments": tc_req["arguments"],
                    }))

                    if tool_call.error:
                        step.observation = f"Tool error: {tool_call.error}"
                        self.state.record_error(tool_call.error)
                        self._debug_phase("ACT", f"{tc_req['name']}: ERROR → {tool_call.error[:100]}", elapsed=t_tool, is_sub=True)
                    else:
                        step.observation = str(tool_call.result)[:1000]
                        self.memory.add("tool", step.observation, name=tc_req["name"], tool_call_id=tc_req["id"])
                        result_preview = step.observation[:100].replace("\n", " ")
                        if len(step.observation) > 100:
                            result_preview += "…"
                        self._debug_phase("ACT", f"{tc_req['name']}({args_preview}) → {result_preview}", elapsed=t_tool, is_sub=True)

                    self.observer.emit(Event("tool_result", {
                        "index": step_index,
                        "result": step.observation,
                        "error": tool_call.error or "",
                        "duration_ms": tool_call.duration_ms,
                    }))

                    self.safety._run_hooks("after_action", tc_req["name"], tool_call.result, tool_call.error)
                    self.state.update_metrics(tool_calls=1)
```

- [ ] **Step 5: Commit**

```bash
git add agent_engine/engine.py
git commit -m "refactor: update engine.py to use src.llm adapters and new config fields"
```

---

### Task 9: Update agent_engine/__init__.py

**Files:**
- Modify: `agent_engine/__init__.py`

**Purpose:** Remove exports that came from the deleted `agent_engine/llm.py`. Keep everything else.

- [ ] **Step 1: Update agent_engine/__init__.py**

Replace the file:

```python
"""agent_engine — A general-purpose autonomous Agent decision system.

Usage:
    from agent_engine import AgentEngine, EngineConfig, ToolRegistry
    from llm.factory import LLMAdapterFactory
    from llm.deepseek import DeepSeekAdapter

    adapter = DeepSeekAdapter(api_key="sk-...")
    engine = AgentEngine(
        llm=adapter,
        config=EngineConfig(),
    )
    engine.tools.register_from_func(my_tool)
    state = await engine.run("Your goal")
"""
__version__ = "0.1.0"

from agent_engine.engine import AgentEngine
from agent_engine.config import EngineConfig
from agent_engine.tools import ToolRegistry, ToolDef
from agent_engine.state import StateManager
from agent_engine.memory import MemoryManager
from agent_engine.reflect import Reflector, Reflection
from agent_engine.observe import Observer, Event
from agent_engine.safety import SafetyChecker
from agent_engine.types import (
    ToolCall,
    Step,
    AgentState,
    Message,
)

__all__ = [
    "AgentEngine",
    "EngineConfig",
    "ToolRegistry",
    "ToolDef",
    "StateManager",
    "MemoryManager",
    "Reflector",
    "Reflection",
    "Observer",
    "Event",
    "SafetyChecker",
    "ToolCall",
    "Step",
    "AgentState",
    "Message",
]
```

- [ ] **Step 2: Commit**

```bash
git add agent_engine/__init__.py
git commit -m "refactor: remove LLM exports from agent_engine/__init__.py"
```

---

### Task 10: Update agent_engine/cli.py

**Files:**
- Modify: `agent_engine/cli.py`

**Purpose:** Build the adapter through `LLMAdapterFactory` instead of directly instantiating `DeepSeekAdapter`. Use new config field names.

- [ ] **Step 1: Update imports**

Replace lines 9-10:
```python
from agent_engine.engine import AgentEngine
from agent_engine.llm import DeepSeekAdapter
from agent_engine.config import EngineConfig
```
with:
```python
from agent_engine.engine import AgentEngine
from agent_engine.config import EngineConfig
from llm.factory import LLMAdapterFactory
from core.models import LLMConfig
```

- [ ] **Step 2: Update build_engine()**

Replace the config creation and adapter instantiation in `build_engine()`:

```python
def build_engine(args) -> AgentEngine:
    """Build an AgentEngine from CLI arguments."""
    config = EngineConfig(
        max_steps=args.max_steps,
        reflect_interval=args.reflect_interval,
        llm_api_key=args.api_key or "",
        llm_base_url=args.base_url,
        llm_model=args.model,
        log_format="json" if args.json_log else "text",
        workspace_dir=args.workspace,
        debug=args.debug,
    )

    if not args.api_key:
        print("No API key provided. Use --api-key or set AGENT_ENGINE_LLM_API_KEY env var.")
        sys.exit(1)

    llm_config = LLMConfig(
        provider="deepseek",
        name=args.model,
        base_url=args.base_url,
    )
    adapter = LLMAdapterFactory.create(llm_config, args.api_key)

    engine = AgentEngine(llm=adapter, config=config)
    ...
```

- [ ] **Step 3: Commit**

```bash
git add agent_engine/cli.py
git commit -m "refactor: use LLMAdapterFactory in CLI instead of direct DeepSeekAdapter"
```

---

### Task 11: Update src/core/agent.py

**Files:**
- Modify: `src/core/agent.py` (lines ~130-144)

**Purpose:** Update `create_engine()` to import from `src.llm` and use new config field names.

- [ ] **Step 1: Update imports in create_engine()**

Replace lines 130-133:
```python
        from agent_engine.engine import AgentEngine
        from agent_engine.llm import DeepSeekAdapter as EngineDeepSeekAdapter
        from agent_engine.config import EngineConfig
        from agent_engine.tools import ToolRegistry
```
with:
```python
        from agent_engine.engine import AgentEngine
        from agent_engine.config import EngineConfig
        from agent_engine.tools import ToolRegistry
        from llm.factory import LLMAdapterFactory
        from core.models import LLMConfig
```

- [ ] **Step 2: Update adapter creation**

Replace lines ~135-143:
```python
        engine_llm = EngineDeepSeekAdapter(
            api_key=api_key,
            base_url=self.config.model.base_url or "https://api.deepseek.com",
            model=self.config.model.name,
        )
        engine_config = EngineConfig(
            openai_api_key=api_key,
            openai_base_url=self.config.model.base_url or "https://api.deepseek.com",
            openai_model=self.config.model.name,
        )
```
with:
```python
        llm_config = LLMConfig(
            provider=self.config.model.provider or "deepseek",
            name=self.config.model.name,
            base_url=self.config.model.base_url or "https://api.deepseek.com",
        )
        engine_llm = LLMAdapterFactory.create(llm_config, api_key)
        engine_config = EngineConfig(
            llm_api_key=api_key,
            llm_base_url=self.config.model.base_url or "https://api.deepseek.com",
            llm_model=self.config.model.name,
            llm_temperature=self.config.model.temperature,
            llm_max_tokens=self.config.model.max_tokens,
        )
```

- [ ] **Step 3: Commit**

```bash
git add src/core/agent.py
git commit -m "refactor: use LLMAdapterFactory in agent.create_engine()"
```

---

### Task 12: Clean src/ui/session_panel.py imports

**Files:**
- Modify: `src/ui/session_panel.py` (lines 35-38)

**Purpose:** Remove unused imports — engine creation now goes through `agent.create_engine()`.

- [ ] **Step 1: Remove unused agent_engine imports**

Replace lines 35-38:
```python
from agent_engine.engine import AgentEngine
from agent_engine.config import EngineConfig
from agent_engine.tools import ToolRegistry
from agent_engine.llm import DeepSeekAdapter
```
Delete these 4 lines entirely. They are unused; actual engine creation is via `agent.create_engine(api_key)` at line 161.

- [ ] **Step 2: Commit**

```bash
git add src/ui/session_panel.py
git commit -m "chore: remove unused agent_engine imports from session_panel.py"
```

---

### Task 13: Delete agent_engine/llm.py

**Files:**
- Delete: `agent_engine/llm.py`

**Purpose:** All LLM adapter code now lives in `src/llm/`.

- [ ] **Step 1: Delete the file**

```bash
git rm agent_engine/llm.py
```

- [ ] **Step 2: Commit**

```bash
git commit -m "refactor: delete agent_engine/llm.py — adapters now in src/llm/"
```

---

### Task 14: Update agent_engine/tests/test_llm.py

**Files:**
- Modify: `agent_engine/tests/test_llm.py`

**Purpose:** Update imports to use `src.llm` modules. Update types to use `dict` for tool_calls instead of `ToolCallRequest`.

- [ ] **Step 1: Update imports**

Replace lines 1-4:
```python
"""Tests for src/llm adapters (previously agent_engine.llm)."""
import pytest
from llm.base import LLMAdapter, LLMResponse
from llm.callback import CallbackAdapter
from llm.deepseek import DeepSeekAdapter
```

- [ ] **Step 2: Update TestLLMResponse tests for dict tool_calls**

Replace the class:
```python
class TestLLMResponse:
    def test_response_defaults(self):
        r = LLMResponse(content="hello")
        assert r.content == "hello"
        assert r.tool_calls == []
        assert r.usage is None

    def test_response_with_tool_calls(self):
        tc = {"id": "1", "name": "search", "arguments": {"q": "test"}}
        r = LLMResponse(content="", tool_calls=[tc])
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0]["name"] == "search"
```

- [ ] **Step 3: Update CallbackAdapter tests**

Update `TestCallbackAdapter` — the tests need to pass `model` to `chat()` and check response with dict tool_calls:

```python
class TestCallbackAdapter:
    @pytest.mark.asyncio
    async def test_callback_adapter_passthrough(self):
        async def my_chat(messages, tools=None):
            return "response from callback"

        adapter = CallbackAdapter(my_chat)
        resp = await adapter.chat([{"role": "user", "content": "hi"}], model="test")
        assert resp.content == "response from callback"
        assert resp.tool_calls == []

    @pytest.mark.asyncio
    async def test_callback_adapter_with_tools(self):
        async def my_chat(messages, tools=None):
            return "used tools: " + str(len(tools) if tools else 0)

        adapter = CallbackAdapter(my_chat)
        resp = await adapter.chat(
            [{"role": "user", "content": "hi"}],
            model="test",
            tools=[{"name": "t"}],
        )
        assert "1" in resp.content

    @pytest.mark.asyncio
    async def test_callback_adapter_streaming(self):
        async def my_chat(messages, tools=None):
            for c in "hello":
                yield c

        adapter = CallbackAdapter(my_chat)
        chunks = []
        async for chunk in adapter.chat_stream(
            [{"role": "user", "content": "hi"}], model="test",
        ):
            chunks.append(chunk)
        assert "".join(chunks) == "hello"

    @pytest.mark.asyncio
    async def test_chat_on_chunk_with_async_generator(self):
        """CallbackAdapter.chat() calls on_chunk for each chunk from an async generator."""

        async def my_chat(messages, tools=None):
            for c in "streaming":
                yield c

        adapter = CallbackAdapter(my_chat)
        received: list[str] = []

        resp = await adapter.chat(
            [{"role": "user", "content": "hi"}],
            model="test",
            on_chunk=lambda chunk: received.append(chunk),
        )
        assert resp.content == "streaming"
        assert received == list("streaming")

    @pytest.mark.asyncio
    async def test_chat_on_chunk_with_awaitable(self):
        """CallbackAdapter.chat() calls on_chunk once with the full result from a coroutine."""

        async def my_chat(messages, tools=None):
            return "full response"

        adapter = CallbackAdapter(my_chat)
        received: list[str] = []

        resp = await adapter.chat(
            [{"role": "user", "content": "hi"}],
            model="test",
            on_chunk=lambda chunk: received.append(chunk),
        )
        assert resp.content == "full response"
        assert received == ["full response"]
```

- [ ] **Step 4: Update DeepSeekAdapter tests for dict tool_calls and model param**

Replace `TestToolCallDeltaAccumulation` — change `resp.tool_calls[0].id` → `resp.tool_calls[0]["id"]`, add `model="test"`:

```python
class TestToolCallDeltaAccumulation:
    """Unit tests for tool call delta accumulation in streaming responses."""

    @staticmethod
    def _make_sse_line(data: dict) -> str:
        import json
        return "data: " + json.dumps(data)

    @staticmethod
    def _make_mock_stream(sse_lines: list[str]):
        from unittest.mock import AsyncMock, MagicMock

        mock_response = MagicMock()
        async def _aiter_lines():
            for line in sse_lines:
                yield line
        mock_response.aiter_lines = _aiter_lines

        mock_response_cls = MagicMock()
        mock_response_cls.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_cls.__aexit__ = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_response_cls)
        return mock_client

    @pytest.mark.asyncio
    async def test_tool_call_deltas_assembled_from_sse_stream(self):
        """Verify tool call deltas arriving across multiple SSE chunks are correctly
        assembled into dict-format tool calls."""
        from unittest.mock import AsyncMock

        sse_lines = [
            self._make_sse_line({"choices": [{"delta": {"content": "Let me search that"}}]}),
            self._make_sse_line({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "search"}}]}}]}),
            self._make_sse_line({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"q":'}}]}}]}),
            self._make_sse_line({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"test"}'}}]}}]}),
            self._make_sse_line({"choices": [{"delta": {"content": "."}}]}),
            "data: [DONE]",
        ]

        mock_client = self._make_mock_stream(sse_lines)

        adapter = DeepSeekAdapter(api_key="test-key")
        adapter._get_client = AsyncMock(return_value=mock_client)

        received: list[str] = []
        resp = await adapter.chat(
            [{"role": "user", "content": "search for test"}],
            model="deepseek-chat",
            tools=[{"name": "search", "description": "Search", "parameters": {"type": "object", "properties": {}}}],
            on_chunk=lambda c: received.append(c),
        )

        assert resp.content == "Let me search that."
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0]["id"] == "call_1"
        assert resp.tool_calls[0]["name"] == "search"
        assert resp.tool_calls[0]["arguments"] == {"q": "test"}
        assert received == ["Let me search that", "."]

    @pytest.mark.asyncio
    async def test_tool_call_deltas_multiple_tools(self):
        """Verify multiple parallel tool calls are correctly separated by index."""
        from unittest.mock import AsyncMock

        sse_lines = [
            self._make_sse_line({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call_a", "function": {"name": "calc"}},
                {"index": 1, "id": "call_b", "function": {"name": "search"}},
            ]}}]}),
            self._make_sse_line({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": '{"expr":"2+2"}'}},
            ]}}]}),
            self._make_sse_line({"choices": [{"delta": {"tool_calls": [
                {"index": 1, "function": {"arguments": '{"q":"test"}'}},
            ]}}]}),
            "data: [DONE]",
        ]

        mock_client = self._make_mock_stream(sse_lines)

        adapter = DeepSeekAdapter(api_key="test-key")
        adapter._get_client = AsyncMock(return_value=mock_client)

        resp = await adapter.chat(
            [{"role": "user", "content": "calc and search"}],
            model="deepseek-chat",
            tools=[
                {"name": "calc", "description": "Calculate", "parameters": {"type": "object", "properties": {}}},
                {"name": "search", "description": "Search", "parameters": {"type": "object", "properties": {}}},
            ],
            on_chunk=lambda c: None,
        )

        assert len(resp.tool_calls) == 2
        assert resp.tool_calls[0]["name"] == "calc"
        assert resp.tool_calls[0]["arguments"] == {"expr": "2+2"}
        assert resp.tool_calls[1]["name"] == "search"
        assert resp.tool_calls[1]["arguments"] == {"q": "test"}
```

- [ ] **Step 5: Commit**

```bash
git add agent_engine/tests/test_llm.py
git commit -m "test: update test_llm.py for src/llm adapters and dict tool_calls"
```

---

### Task 15: Update agent_engine/tests/test_engine.py

**Files:**
- Modify: `agent_engine/tests/test_engine.py`

**Purpose:** Update imports, use dict tool_calls, pass model param.

- [ ] **Step 1: Update imports**

Replace lines 1-7:
```python
"""Tests for agent_engine.engine."""
import asyncio
import pytest
from agent_engine.engine import AgentEngine
from llm.callback import CallbackAdapter
from llm.base import LLMResponse
from agent_engine.config import EngineConfig
```

- [ ] **Step 2: Update test_max_steps_stops tool_calls**

Replace the ToolCallRequest import + usage with dict:
```python
    @pytest.mark.asyncio
    async def test_max_steps_stops(self):
        """Agent should stop when max_steps is reached."""
        def double(x):
            return x * 2

        async def chat(messages, tools=None):
            return LLMResponse(
                content="Still working...",
                tool_calls=[{"id": "1", "name": "double", "arguments": {"x": 2}}],
            )

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=3, reflect_interval=10),
        )
        engine.tools.register_from_func(double)
        state = await engine.run("An impossible task")
        assert state.status == "failed"
        assert len(state.steps) >= 3
```

- [ ] **Step 3: Update test_emergency_stop tool_calls**

```python
    @pytest.mark.asyncio
    async def test_emergency_stop(self):
        """Requesting stop should halt the agent."""
        def noop():
            pass

        stop_after = 5

        async def chat(messages, tools=None):
            nonlocal stop_after
            stop_after -= 1
            if stop_after <= 0:
                engine.request_stop()
            return LLMResponse(
                content="Working...",
                tool_calls=[{"id": "1", "name": "noop", "arguments": {}}],
            )

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=30, reflect_interval=100),
        )
        engine.tools.register_from_func(noop)

        state = await engine.run("Some goal")
        assert state.status == "stopped"
```

- [ ] **Step 5: Commit**

```bash
git add agent_engine/tests/test_engine.py
git commit -m "test: update test_engine.py imports and dict tool_calls"
```

---

### Task 16: Update agent_engine/tests/test_reflect.py

**Files:**
- Modify: `agent_engine/tests/test_reflect.py` (line 83)

**Purpose:** Update the import of CallbackAdapter.

- [ ] **Step 1: Update the import**

Replace line 83:
```python
    from agent_engine.llm import CallbackAdapter
```
with:
```python
    from llm.callback import CallbackAdapter
```

- [ ] **Step 2: Commit**

```bash
git add agent_engine/tests/test_reflect.py
git commit -m "test: update test_reflect.py import to use llm.callback"
```

---

### Task 17: Run tests and verify

**Files:** None (verification only)

- [ ] **Step 1: Run agent_engine tests**

```bash
pytest agent_engine/tests/ -v
```
Expected: All tests pass (except any that need real API keys).

- [ ] **Step 2: Run GUI-side tests**

```bash
pytest tests/ -v
```
Expected: All tests pass.

- [ ] **Step 3: Run app health check**

```bash
python main.py --health
```
Expected: PASS.

- [ ] **Step 4: Commit any fixes if needed**

```bash
git add -A
git commit -m "fix: test adjustments after LLM refactor"
```

---

### Task 18: Final verification and cleanup

- [ ] **Step 1: Verify no remaining references to agent_engine.llm**

```bash
rg "agent_engine\.llm" --type py -l
```
Expected: No results (only doc/plan files may remain).

- [ ] **Step 2: Verify no remaining references to openai_api_key in code**

```bash
rg "openai_api_key" --type py -l
```
Expected: No results.

- [ ] **Step 3: Final commit if any stragglers fixed**

```bash
git add -A && git commit -m "chore: final cleanup after LLM refactor"
```
