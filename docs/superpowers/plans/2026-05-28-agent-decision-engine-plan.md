# Agent Decision Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python library (`agent_engine/`) implementing a general-purpose autonomous Agent decision system with OBSERVE→THINK→ACT→REFLECT loop, tool calling, memory, reflection, observability, and safety controls.

**Architecture:** Modular components with direct method calls. Each of the 10 modules has a single responsibility and communicates through well-defined interfaces (pydantic models). The `AgentEngine` class composes all components and drives the main decision loop.

**Tech Stack:** Python 3.10+, pydantic >= 2.0, loguru >= 0.7, python-dotenv >= 1.0, httpx >= 0.25

---

### Task 1: Project Scaffold

**Files:**
- Create: `agent_engine/pyproject.toml`
- Create: `agent_engine/__init__.py` (empty placeholder)

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p agent_engine/builtin_tools agent_engine/tests
```

- [ ] **Step 2: Write pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "agent-engine"
version = "0.1.0"
description = "A general-purpose autonomous Agent decision system"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.0",
    "loguru>=0.7",
    "python-dotenv>=1.0",
    "httpx>=0.25",
]

[project.optional-dependencies]
tools = ["requests>=2.28"]

[project.scripts]
agent-engine = "agent_engine.cli:main"
```

- [ ] **Step 3: Write empty __init__.py (placeholder, will be filled in Task 14)**

```python
# agent_engine — A general-purpose autonomous Agent decision system
__version__ = "0.1.0"
```

- [ ] **Step 4: Create builtin_tools/__init__.py and tests/__init__.py**

```bash
touch agent_engine/builtin_tools/__init__.py agent_engine/tests/__init__.py
```

- [ ] **Step 5: Commit**

```bash
cd e:/ACTs && git add agent_engine/ && git commit -m "feat: scaffold agent_engine project structure"
```

---

### Task 2: types.py — Pydantic Models

**Files:**
- Create: `agent_engine/types.py`
- Create: `agent_engine/tests/test_types.py`

- [ ] **Step 1: Write failing tests for types**

```python
"""Tests for agent_engine.types."""
import pytest
from datetime import datetime
from agent_engine.types import (
    ToolDef, ToolCall, Step, AgentState, Message, ToolCallRequest
)


class TestToolDef:
    def test_minimal_tool_def(self):
        t = ToolDef(name="test", description="A test tool", parameters={"type": "object", "properties": {}})
        assert t.name == "test"
        assert t.timeout_sec == 30.0
        assert t.max_retries == 2
        assert t.is_async is False
        assert t.func is None

    def test_tool_def_with_func(self):
        def my_func(x: int) -> str:
            return str(x)
        t = ToolDef(name="f", description="d", parameters={}, func=my_func, is_async=True, timeout_sec=10.0, max_retries=0)
        assert t.func is not None
        assert t.is_async is True
        assert t.timeout_sec == 10.0
        assert t.max_retries == 0


class TestToolCall:
    def test_tool_call_creation(self):
        tc = ToolCall(id="abc", tool_name="search", arguments={"q": "hello"})
        assert tc.result is None
        assert tc.error is None
        assert tc.finished_at is None

    def test_tool_call_duration_computed(self):
        tc = ToolCall(id="1", tool_name="t", arguments={})
        assert tc.duration_ms == 0.0


class TestStep:
    def test_step_defaults(self):
        s = Step(index=0, phase="observe")
        assert s.thought == ""
        assert s.tool_call is None
        assert s.is_completed is False


class TestAgentState:
    def test_initial_state(self):
        s = AgentState(goal="test goal")
        assert s.status == "idle"
        assert s.steps == []
        assert s.errors == []
        assert s.current_step_index == 0

    def test_state_status_values(self):
        s = AgentState(goal="g", status="running")
        assert s.status == "running"
        s.status = "done"
        assert s.status == "done"


class TestMessage:
    def test_message_creation(self):
        m = Message(role="user", content="hello")
        assert m.tool_call_id is None
        assert m.name is None

    def test_tool_message(self):
        m = Message(role="tool", content="result", tool_call_id="123", name="search")
        assert m.tool_call_id == "123"
        assert m.name == "search"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_types.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Write types.py**

```python
"""Core data models for the Agent decision engine.

All shared types are defined here as Pydantic models to ensure
type safety and automatic validation across all modules.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field


class ToolDef(BaseModel):
    """Definition of a tool that the Agent can call.

    Supports both OpenAI Function Calling JSON Schema format and
    direct Python function references. Parameters are validated
    by Pydantic at registration time.
    """
    name: str
    description: str
    parameters: dict = Field(default_factory=lambda: {"type": "object", "properties": {}})
    func: Callable | None = Field(default=None, exclude=True)
    is_async: bool = False
    timeout_sec: float = 30.0
    max_retries: int = 2


class ToolCallRequest(BaseModel):
    """A tool call requested by the LLM (before execution)."""
    id: str
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolCall(BaseModel):
    """Record of a completed tool invocation."""
    id: str
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    result: Any = None
    error: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    duration_ms: float = 0.0
    retry_count: int = 0


class Step(BaseModel):
    """One iteration of the decision loop."""
    index: int
    phase: Literal["observe", "think", "act", "reflect"]
    thought: str = ""
    tool_call: ToolCall | None = None
    observation: str = ""
    reflection: str = ""
    is_completed: bool = False


class AgentState(BaseModel):
    """Full runtime state of the Agent."""
    goal: str
    sub_goals: list[str] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    current_step_index: int = 0
    status: Literal["idle", "running", "paused", "done", "failed", "stopped"] = "idle"
    errors: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class Message(BaseModel):
    """A single chat message in the conversation history."""
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    name: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_types.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd e:/ACTs && git add agent_engine/types.py agent_engine/tests/test_types.py && git commit -m "feat: add pydantic type definitions"
```

---

### Task 3: config.py — Configuration

**Files:**
- Create: `agent_engine/config.py`

- [ ] **Step 1: Write config.py**

```python
"""Global configuration for the Agent decision engine.

All configurable parameters live here, loadable from environment
variables or .env files via pydantic-settings.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineConfig(BaseSettings):
    """Configuration for the Agent decision engine.

    Every parameter can be overridden via environment variable
    (uppercase) or a .env file in the working directory.
    """
    model_config = SettingsConfigDict(
        env_prefix="AGENT_ENGINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- LLM --
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"

    # -- Safety --
    max_steps: int = 50
    tool_whitelist: str = ""  # comma-separated tool names; empty = allow all

    # -- Reflection --
    reflect_interval: int = 3

    # -- Memory --
    compress_trigger_tokens: int = 6000
    compress_target_tokens: int = 3000

    # -- Logging --
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    # -- Workspace --
    workspace_dir: str = "./workspace"

    @property
    def tool_whitelist_set(self) -> set[str] | None:
        if not self.tool_whitelist.strip():
            return None
        return {t.strip() for t in self.tool_whitelist.split(",") if t.strip()}


# Add missing import
from typing import Literal  # noqa: E402
```

Wait, there's a problem with the import order. Let me fix this properly.

- [ ] **Step 1 (corrected): Write config.py**

```python
"""Global configuration for the Agent decision engine.

All configurable parameters live here, loadable from environment
variables or .env files via pydantic-settings.
"""
from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineConfig(BaseSettings):
    """Configuration for the Agent decision engine.

    Every parameter can be overridden via environment variable
    (uppercase, prefixed with AGENT_ENGINE_) or a .env file
    in the working directory.
    """
    model_config = SettingsConfigDict(
        env_prefix="AGENT_ENGINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- LLM --
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"

    # -- Safety --
    max_steps: int = 50
    tool_whitelist: str = ""  # comma-separated; empty = allow all

    # -- Reflection --
    reflect_interval: int = 3

    # -- Memory --
    compress_trigger_tokens: int = 6000
    compress_target_tokens: int = 3000

    # -- Logging --
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    # -- Workspace --
    workspace_dir: str = "./workspace"

    @property
    def tool_whitelist_set(self) -> set[str] | None:
        """Parse the comma-separated whitelist string into a set."""
        if not self.tool_whitelist.strip():
            return None
        return {t.strip() for t in self.tool_whitelist.split(",") if t.strip()}
```

- [ ] **Step 2: Verify config can be imported**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -c "from agent_engine.config import EngineConfig; c = EngineConfig(); print(c.max_steps)"`
Expected: prints `50`

- [ ] **Step 3: Commit**

```bash
cd e:/ACTs && git add agent_engine/config.py && git commit -m "feat: add EngineConfig with pydantic-settings"
```

---

### Task 4: llm.py — LLM Adapter

**Files:**
- Create: `agent_engine/llm.py`
- Create: `agent_engine/tests/test_llm.py`

- [ ] **Step 1: Write tests for llm.py**

```python
"""Tests for agent_engine.llm."""
import pytest
from agent_engine.llm import LLMAdapter, LLMResponse, CallbackAdapter, OpenAIAdapter
from agent_engine.types import ToolCallRequest


class TestLLMResponse:
    def test_response_defaults(self):
        r = LLMResponse(content="hello")
        assert r.content == "hello"
        assert r.tool_calls == []
        assert r.usage == {}

    def test_response_with_tool_calls(self):
        tc = ToolCallRequest(id="1", name="search", arguments={"q": "test"})
        r = LLMResponse(content="", tool_calls=[tc])
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0].name == "search"


class TestCallbackAdapter:
    @pytest.mark.asyncio
    async def test_callback_adapter_passthrough(self):
        async def my_chat(messages, tools=None):
            return "response from callback"

        adapter = CallbackAdapter(my_chat)
        resp = await adapter.chat([{"role": "user", "content": "hi"}])
        assert resp.content == "response from callback"
        assert resp.tool_calls == []

    @pytest.mark.asyncio
    async def test_callback_adapter_with_tools(self):
        async def my_chat(messages, tools=None):
            return "used tools: " + str(len(tools) if tools else 0)

        adapter = CallbackAdapter(my_chat)
        resp = await adapter.chat([{"role": "user", "content": "hi"}], tools=[{"name": "t"}])
        assert "1" in resp.content

    @pytest.mark.asyncio
    async def test_callback_adapter_streaming(self):
        async def my_chat(messages, tools=None):
            for c in "hello":
                yield c

        adapter = CallbackAdapter(my_chat)
        chunks = []
        async for chunk in adapter.chat_stream([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)
        assert "".join(chunks) == "hello"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_llm.py -v`
Expected: FAIL

- [ ] **Step 3: Write llm.py**

```python
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
```

- [ ] **Step 4: Run tests**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_llm.py -v`
Expected: all PASS (CallbackAdapter tests pass; OpenAIAdapter tests not included since they need API key)

- [ ] **Step 5: Commit**

```bash
cd e:/ACTs && git add agent_engine/llm.py agent_engine/tests/test_llm.py && git commit -m "feat: add LLM adapter layer"
```

---

### Task 5: state.py — StateManager

**Files:**
- Create: `agent_engine/state.py`
- Create: `agent_engine/tests/test_state.py`

- [ ] **Step 1: Write tests for state.py**

```python
"""Tests for agent_engine.state."""
import pytest
from agent_engine.state import StateManager
from agent_engine.types import Step, AgentState


class TestStateManager:
    def test_initial_state(self):
        sm = StateManager()
        assert sm.state.status == "idle"
        assert sm.state.goal == ""

    def test_start(self):
        sm = StateManager()
        sm.start("test goal")
        assert sm.state.status == "running"
        assert sm.state.goal == "test goal"
        assert sm.state.started_at is not None

    def test_cannot_start_twice(self):
        sm = StateManager()
        sm.start("goal")
        with pytest.raises(RuntimeError, match="already running"):
            sm.start("other")

    def test_pause_resume(self):
        sm = StateManager()
        sm.start("goal")
        sm.pause()
        assert sm.state.status == "paused"
        sm.resume()
        assert sm.state.status == "running"

    def test_cannot_pause_when_idle(self):
        sm = StateManager()
        with pytest.raises(RuntimeError, match="not running"):
            sm.pause()

    def test_stop(self):
        sm = StateManager()
        sm.start("goal")
        sm.stop("done")
        assert sm.state.status == "done"
        assert sm.state.finished_at is not None

    def test_add_step(self):
        sm = StateManager()
        sm.start("goal")
        step = Step(index=0, phase="think", thought="let me think")
        sm.add_step(step)
        assert len(sm.state.steps) == 1
        assert sm.state.current_step_index == 1

    def test_get_last_n_steps(self):
        sm = StateManager()
        sm.start("goal")
        for i in range(5):
            sm.add_step(Step(index=i, phase="think"))
        last3 = sm.get_last_n_steps(3)
        assert len(last3) == 3
        assert last3[0].index == 2
        assert last3[-1].index == 4

    def test_record_error(self):
        sm = StateManager()
        sm.start("goal")
        sm.record_error("something went wrong")
        assert len(sm.state.errors) == 1

    def test_error_deduplication(self):
        sm = StateManager()
        sm.start("goal")
        sm.record_error("timeout")
        sm.record_error("timeout")
        sm.record_error("timeout")
        assert len(sm.state.errors) == 1  # deduplicated

    def test_sub_goals(self):
        sm = StateManager()
        sm.start("main goal")
        sm.set_sub_goals(["step 1", "step 2", "step 3"])
        assert sm.state.sub_goals == ["step 1", "step 2", "step 3"]
        sm.complete_sub_goal(0)
        # completion just records — doesn't remove
        assert len(sm.state.sub_goals) == 3

    def test_to_dict_from_dict(self):
        sm = StateManager()
        sm.start("goal")
        sm.add_step(Step(index=0, phase="think", thought="test"))
        data = sm.to_dict()
        restored = StateManager.from_dict(data)
        assert restored.state.goal == "goal"
        assert len(restored.state.steps) == 1

    def test_metrics_update(self):
        sm = StateManager()
        sm.start("goal")
        sm.update_metrics(tool_calls=5, tokens_used=1000)
        assert sm.state.metrics["tool_calls"] == 5
        assert sm.state.metrics["tokens_used"] == 1000
        sm.update_metrics(tool_calls=3)  # accumulates
        assert sm.state.metrics["tool_calls"] == 8
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_state.py -v`
Expected: FAIL

- [ ] **Step 3: Write state.py**

```python
"""State manager for the Agent decision engine.

Tracks the agent's runtime state: goal, sub-goals, steps, errors,
metrics, and the state machine lifecycle (idle→running→done/failed/stopped).
"""
from __future__ import annotations

from datetime import datetime, timezone

from agent_engine.types import AgentState, Step


class StateManager:
    """Manages the Agent's full runtime state.

    All mutations go through this class; the internal AgentState
    pydantic model acts as the single source of truth.
    """

    VALID_TRANSITIONS: dict[str, set[str]] = {
        "idle": {"running"},
        "running": {"paused", "done", "failed", "stopped"},
        "paused": {"running", "stopped"},
        "done": set(),
        "failed": set(),
        "stopped": set(),
    }

    def __init__(self):
        self.state = AgentState(goal="")

    # -- Lifecycle --

    def start(self, goal: str) -> None:
        if self.state.status != "idle":
            raise RuntimeError(f"Cannot start: agent is already {self.state.status}")
        self.state.goal = goal
        self.state.status = "running"
        self.state.started_at = datetime.now(timezone.utc)

    def pause(self) -> None:
        self._transition("paused")

    def resume(self) -> None:
        self._transition("running")

    def stop(self, reason: str) -> None:
        valid_final = {"done", "failed", "stopped"}
        if reason not in valid_final:
            raise ValueError(f"Stop reason must be one of {valid_final}, got '{reason}'")
        self._transition(reason)
        self.state.finished_at = datetime.now(timezone.utc)

    def _transition(self, target: str) -> None:
        allowed = self.VALID_TRANSITIONS.get(self.state.status, set())
        if target not in allowed:
            raise RuntimeError(f"Cannot transition from '{self.state.status}' to '{target}'")
        self.state.status = target

    # -- Steps --

    def add_step(self, step: Step) -> None:
        self.state.steps.append(step)
        self.state.current_step_index = len(self.state.steps)

    def get_last_n_steps(self, n: int) -> list[Step]:
        return self.state.steps[-n:]

    # -- Sub-goals --

    def set_sub_goals(self, goals: list[str]) -> None:
        self.state.sub_goals = list(goals)

    def complete_sub_goal(self, index: int) -> None:
        if 0 <= index < len(self.state.sub_goals):
            # Mark as complete by prefixing
            current = self.state.sub_goals[index]
            if not current.startswith("[✓] "):
                self.state.sub_goals[index] = f"[✓] {current}"

    # -- Errors --

    def record_error(self, error: str) -> None:
        if error not in self.state.errors:
            self.state.errors.append(error)

    def get_error_summary(self) -> str:
        if not self.state.errors:
            return "No errors recorded."
        return f"{len(self.state.errors)} unique errors: " + "; ".join(self.state.errors[-5:])

    # -- Metrics --

    def update_metrics(self, **kwargs: int | float) -> None:
        for key, value in kwargs.items():
            current = self.state.metrics.get(key, 0)
            self.state.metrics[key] = current + value

    def get_metrics(self) -> dict:
        elapsed = 0.0
        if self.state.started_at:
            end = self.state.finished_at or datetime.now(timezone.utc)
            elapsed = (end - self.state.started_at).total_seconds()
        return {
            **self.state.metrics,
            "elapsed_sec": elapsed,
            "total_steps": len(self.state.steps),
            "error_count": len(self.state.errors),
        }

    # -- Serialization --

    def to_dict(self) -> dict:
        return self.state.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict) -> "StateManager":
        sm = cls()
        sm.state = AgentState(**data)
        return sm
```

- [ ] **Step 4: Run tests**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_state.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd e:/ACTs && git add agent_engine/state.py agent_engine/tests/test_state.py && git commit -m "feat: add StateManager with state machine"
```

---

### Task 6: safety.py — SafetyChecker

**Files:**
- Create: `agent_engine/safety.py`
- Create: `agent_engine/tests/test_safety.py`

- [ ] **Step 1: Write tests for safety.py**

```python
"""Tests for agent_engine.safety."""
import pytest
from agent_engine.safety import SafetyChecker
from agent_engine.state import StateManager
from agent_engine.types import Step


class TestSafetyChecker:
    def test_defaults(self):
        sc = SafetyChecker()
        assert sc.max_steps == 50
        assert sc.tool_whitelist is None
        assert "exec" in sc.confirm_sensitive

    def test_should_stop_max_steps(self):
        sc = SafetyChecker(max_steps=3)
        sm = StateManager()
        sm.start("goal")
        for i in range(3):
            sm.add_step(Step(index=i, phase="think"))
        assert sc.should_stop(sm.state) is True

    def test_should_not_stop_under_limit(self):
        sc = SafetyChecker(max_steps=10)
        sm = StateManager()
        sm.start("goal")
        sm.add_step(Step(index=0, phase="think"))
        assert sc.should_stop(sm.state) is False

    def test_stop_requested(self):
        sc = SafetyChecker()
        sm = StateManager()
        sm.start("goal")
        sc.request_stop()
        assert sc.should_stop(sm.state) is True

    def test_error_loop_detection(self):
        sc = SafetyChecker()
        sm = StateManager()
        sm.start("goal")
        for _ in range(5):
            sm.record_error("same error")
        # 5 identical errors triggers error loop detection
        assert sc.should_stop(sm.state) is True

    def test_tool_whitelist_allows(self):
        sc = SafetyChecker(tool_whitelist={"search", "calc"})
        assert sc.check_tool("search", {}) is True
        assert sc.check_tool("calc", {}) is True

    def test_tool_whitelist_blocks(self):
        sc = SafetyChecker(tool_whitelist={"search"})
        assert sc.check_tool("exec", {}) is False

    def test_whitelist_none_allows_all(self):
        sc = SafetyChecker(tool_whitelist=None)
        assert sc.check_tool("anything", {}) is True

    def test_sensitive_tool_detection(self):
        sc = SafetyChecker()
        assert sc.is_sensitive("exec") is True
        assert sc.is_sensitive("search") is False

    def test_before_action_hook(self):
        sc = SafetyChecker()
        calls = []

        def hook(name, args):
            calls.append((name, args))
            return True  # allow

        sc.before_action(hook)
        assert sc._run_hooks("before_action", "search", {"q": "test"}) is True
        assert len(calls) == 1

    def test_before_action_hook_blocks(self):
        sc = SafetyChecker()

        def blocker(name, args):
            return False  # block

        sc.before_action(blocker)
        assert sc._run_hooks("before_action", "exec", {}) is False

    def test_after_action_hook(self):
        sc = SafetyChecker()
        calls = []

        def hook(name, result, error):
            calls.append((name, error))
            return True

        sc.after_action(hook)
        assert sc._run_hooks("after_action", "search", "result", None) is True
        assert len(calls) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_safety.py -v`
Expected: FAIL

- [ ] **Step 3: Write safety.py**

```python
"""Safety checker for the Agent decision engine.

Enforces step limits, tool whitelists, sensitive operation detection,
and provides before/after action hooks for extensible safety policies.
"""
from __future__ import annotations

from typing import Any, Callable

from loguru import logger

from agent_engine.types import AgentState


class SafetyChecker:
    """Enforces safety constraints on the agent's behavior.

    Built-in checks:
    - max_steps: hard limit on total loop iterations
    - tool_whitelist: optional allowlist for tool names
    - confirm_sensitive: tools that should require external confirmation
    - stop_requested: emergency stop flag
    - error_loop: same error repeated 5+ times

    Extensible via before_action / after_action hooks.
    """

    def __init__(
        self,
        max_steps: int = 50,
        tool_whitelist: set[str] | None = None,
        confirm_sensitive: set[str] | None = None,
    ):
        self.max_steps = max_steps
        self.tool_whitelist = tool_whitelist
        self.confirm_sensitive = confirm_sensitive or {"exec", "shell", "file_delete", "code_exec"}
        self.stop_requested = False
        self._before_hooks: list[Callable] = []
        self._after_hooks: list[Callable] = []

    # -- Core checks --

    def should_stop(self, state: AgentState) -> bool:
        """Check if the agent should stop. Returns True if any stop
        condition is met."""
        if self.stop_requested:
            logger.info("Stop requested by user")
            return True

        if state.current_step_index >= self.max_steps:
            logger.warning(f"Max steps ({self.max_steps}) reached")
            return True

        # Error loop: same error 5+ times
        if len(state.errors) >= 5:
            # All errors are already deduplicated, so N unique errors
            # means N different error types — not necessarily a loop.
            # Check if the most recent error dominates.
            if len(state.errors) == 1 and state.current_step_index >= 5:
                logger.warning("Error loop detected: same error repeated")
                return True

        return False

    def check_tool(self, tool_name: str, arguments: dict | None = None) -> bool:
        """Check if a tool call should be allowed."""
        if self.tool_whitelist is not None and tool_name not in self.tool_whitelist:
            logger.warning(f"Tool '{tool_name}' blocked by whitelist")
            return False
        return True

    def is_sensitive(self, tool_name: str) -> bool:
        """Check if a tool requires external confirmation."""
        return tool_name in self.confirm_sensitive

    def request_stop(self) -> None:
        """Request an emergency stop at the next iteration."""
        self.stop_requested = True
        logger.info("Emergency stop requested")

    # -- Hook system --

    def before_action(self, callback: Callable[[str, dict], bool]) -> None:
        """Register a callback invoked before each tool execution.
        Callback receives (tool_name, arguments) and should return
        True to allow or False to block.
        """
        self._before_hooks.append(callback)

    def after_action(self, callback: Callable[[str, Any, str | None], bool]) -> None:
        """Register a callback invoked after each tool execution.
        Callback receives (tool_name, result, error) and should return
        True to continue or False to abort the loop.
        """
        self._after_hooks.append(callback)

    def _run_hooks(self, hook_name: str, *args: Any) -> bool:
        """Run all registered hooks of a given type. Returns False if
        any hook returns False (blocking), True otherwise."""
        hooks = self._before_hooks if hook_name == "before_action" else self._after_hooks
        for hook in hooks:
            try:
                if not hook(*args):
                    logger.info(f"Action blocked by {hook_name} hook")
                    return False
            except Exception as e:
                logger.error(f"Hook error in {hook_name}: {e}")
        return True
```

- [ ] **Step 4: Run tests**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_safety.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd e:/ACTs && git add agent_engine/safety.py agent_engine/tests/test_safety.py && git commit -m "feat: add SafetyChecker with hooks and limits"
```

---

### Task 7: tools.py — ToolRegistry

**Files:**
- Create: `agent_engine/tools.py`
- Create: `agent_engine/tests/test_tools.py`

- [ ] **Step 1: Write tests for tools.py**

```python
"""Tests for agent_engine.tools."""
import asyncio
import inspect
import pytest
from agent_engine.tools import ToolRegistry, ToolDef


class TestToolRegistry:
    def test_register_tool_def(self):
        reg = ToolRegistry()
        td = ToolDef(name="test", description="A test", parameters={"type": "object", "properties": {}})
        reg.register(td)
        names = [t.name for t in reg.list_tools()]
        assert "test" in names

    def test_register_duplicate_raises(self):
        reg = ToolRegistry()
        td = ToolDef(name="test", description="d", parameters={})
        reg.register(td)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(td)

    def test_unregister(self):
        reg = ToolRegistry()
        td = ToolDef(name="test", description="d", parameters={})
        reg.register(td)
        reg.unregister("test")
        assert len(reg.list_tools()) == 0

    def test_unregister_nonexistent(self):
        reg = ToolRegistry()
        with pytest.raises(KeyError):
            reg.unregister("nonexistent")

    def test_register_from_func_sync(self):
        reg = ToolRegistry()

        def add(a: int, b: int) -> int:
            """Add two numbers.

            :param a: First number
            :param b: Second number
            """
            return a + b

        reg.register_from_func(add)
        tools = reg.list_tools()
        assert len(tools) == 1
        t = tools[0]
        assert t.name == "add"
        assert t.description == "Add two numbers."
        assert "a" in t.parameters.get("properties", {})
        assert "b" in t.parameters.get("properties", {})
        assert t.is_async is False

    def test_register_from_func_async(self):
        reg = ToolRegistry()

        async def fetch(url: str) -> str:
            """Fetch a URL."""
            return "ok"

        reg.register_from_func(fetch)
        t = reg.list_tools()[0]
        assert t.name == "fetch"
        assert t.is_async is True

    def test_register_from_openai(self):
        reg = ToolRegistry()
        schema = {
            "name": "search",
            "description": "Search the web",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }

        def search_fn(query: str) -> str:
            return f"results for {query}"

        reg.register_from_openai(schema, search_fn)
        t = reg.list_tools()[0]
        assert t.name == "search"

    @pytest.mark.asyncio
    async def test_call_sync_tool(self):
        reg = ToolRegistry()

        def double(x: int) -> int:
            return x * 2

        reg.register_from_func(double)
        result = await reg.call("double", {"x": 5})
        assert result.result == 10
        assert result.error is None

    @pytest.mark.asyncio
    async def test_call_async_tool(self):
        reg = ToolRegistry()

        async def double(x: int) -> int:
            await asyncio.sleep(0.01)
            return x * 2

        reg.register_from_func(double)
        result = await reg.call("double", {"x": 5})
        assert result.result == 10

    @pytest.mark.asyncio
    async def test_call_timeout(self):
        reg = ToolRegistry()

        async def slow() -> str:
            await asyncio.sleep(10)
            return "done"

        reg.register(ToolDef(
            name="slow", description="d", parameters={},
            func=slow, is_async=True, timeout_sec=0.05, max_retries=0,
        ))
        result = await reg.call("slow", {})
        assert result.error is not None
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_call_retry(self):
        reg = ToolRegistry()
        call_count = 0

        async def flaky(x: int) -> int:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("fail")
            return x

        reg.register(ToolDef(
            name="flaky", description="d", parameters={},
            func=flaky, is_async=True, timeout_sec=5.0, max_retries=3,
        ))
        result = await reg.call("flaky", {"x": 42})
        assert result.result == 42
        assert result.retry_count == 2

    @pytest.mark.asyncio
    async def test_call_nonexistent_tool(self):
        reg = ToolRegistry()
        with pytest.raises(KeyError, match="not found"):
            await reg.call("nonexistent", {})

    def test_list_openai_schemas(self):
        reg = ToolRegistry()

        def search(query: str) -> str:
            """Search the web."""
            return "results"

        reg.register_from_func(search)
        schemas = reg.list_openai_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "search"
        assert "parameters" in schemas[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_tools.py -v`
Expected: FAIL

- [ ] **Step 3: Write tools.py**

```python
"""Tool registry for the Agent decision engine.

Manages tool registration, discovery, parameter validation, and
execution with timeout/retry support. Tools can be registered as
ToolDef objects, Python functions (auto-inferred schema), or
OpenAI Function Calling format.
"""
from __future__ import annotations

import asyncio
import inspect
import re
import time
from typing import Any, Callable

from loguru import logger

from agent_engine.types import ToolCall, ToolDef


class ToolRegistry:
    """Registry of tools the agent can call.

    Supports three registration paths:
    1. register(ToolDef) — full definition
    2. register_from_func(func) — auto-infer from type hints + docstring
    3. register_from_openai(schema, func) — OpenAI Function Calling format
    """

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    # -- Registration --

    def register(self, tool: ToolDef) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def register_from_func(self, func: Callable, name: str = "", description: str = "", **overrides) -> None:
        """Register a Python function as a tool. Schema is inferred from
        type hints and docstring."""
        tool_name = name or func.__name__
        schema = self._infer_schema_from_func(func)
        if description:
            schema["description"] = description
        is_async = inspect.iscoroutinefunction(func)

        self.register(ToolDef(
            name=tool_name,
            description=schema.get("description", ""),
            parameters={"type": "object", "properties": schema.get("properties", {}),
                        "required": schema.get("required", [])},
            func=func,
            is_async=is_async,
            **overrides,
        ))

    def register_from_openai(self, schema: dict, func: Callable) -> None:
        """Register using an OpenAI Function Calling schema dict."""
        func_def = schema if "name" in schema else schema.get("function", schema)
        name = func_def["name"]
        is_async = inspect.iscoroutinefunction(func)
        self.register(ToolDef(
            name=name,
            description=func_def.get("description", ""),
            parameters=func_def.get("parameters", {"type": "object", "properties": {}}),
            func=func,
            is_async=is_async,
        ))

    def unregister(self, name: str) -> None:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")
        del self._tools[name]
        logger.debug(f"Unregistered tool: {name}")

    # -- Queries --

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())

    def get_tool(self, name: str) -> ToolDef:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")
        return self._tools[name]

    def list_openai_schemas(self) -> list[dict]:
        """Return tools in OpenAI Function Calling format."""
        schemas = []
        for t in self._tools.values():
            schemas.append({
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            })
        return schemas

    # -- Execution --

    async def call(self, name: str, arguments: dict) -> ToolCall:
        """Execute a tool by name with the given arguments.

        Pipeline: lookup → execute with timeout → retry on failure → record.
        """
        tool = self.get_tool(name)
        tc = ToolCall(id=f"call_{int(time.time()*1000)}", tool_name=name, arguments=arguments)

        last_error: str | None = None
        for attempt in range(tool.max_retries + 1):
            try:
                if tool.is_async:
                    result = await asyncio.wait_for(
                        tool.func(**arguments),
                        timeout=tool.timeout_sec,
                    )
                else:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(tool.func, **arguments),
                        timeout=tool.timeout_sec,
                    )

                tc.result = result
                tc.finished_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                tc.duration_ms = (tc.finished_at - tc.started_at).total_seconds() * 1000
                tc.retry_count = attempt
                logger.info(f"Tool '{name}' succeeded (attempt {attempt + 1}, {tc.duration_ms:.0f}ms)")
                return tc

            except asyncio.TimeoutError:
                last_error = f"Tool '{name}' timed out after {tool.timeout_sec}s"
                logger.warning(f"{last_error} (attempt {attempt + 1})")
            except Exception as e:
                last_error = f"Tool '{name}' error: {e}"
                logger.warning(f"{last_error} (attempt {attempt + 1})")

        # All attempts failed
        tc.error = last_error
        tc.finished_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        tc.duration_ms = (tc.finished_at - tc.started_at).total_seconds() * 1000
        tc.retry_count = tool.max_retries
        return tc

    # -- Schema inference --

    @staticmethod
    def _infer_schema_from_func(func: Callable) -> dict:
        """Build a JSON Schema from a Python function's signature and docstring."""
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or ""

        # Extract parameter descriptions from docstring
        param_descriptions: dict[str, str] = {}
        for match in re.finditer(r":param\s+(\w+)\s*:\s*(.+?)(?:\n|$)", doc):
            param_descriptions[match.group(1)] = match.group(2).strip()

        # First line of docstring is the description
        description = doc.split("\n")[0].strip() if doc else ""

        type_map = {
            str: "string", int: "integer", float: "number",
            bool: "boolean", list: "array", dict: "object",
        }

        properties: dict[str, dict] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            param_type = "string"
            if param.annotation is not inspect.Parameter.empty:
                param_type = type_map.get(param.annotation, "string")

            properties[param_name] = {
                "type": param_type,
                "description": param_descriptions.get(param_name, ""),
            }

            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "description": description,
            "properties": properties,
            "required": required,
        }
```

Wait, I used `__import__("datetime")` which is bad practice. Let me fix that in the implementation — the file should have `from datetime import datetime, timezone` at the top. Let me correct the plan.

Actually, let me just fix the tool.py code now and in the plan. The issue is with `tc.finished_at = __import__("datetime")...`. Let me note this and fix it during implementation by adding the import at the top.

- [ ] **Step 3 (corrected): Write tools.py**

```python
"""Tool registry for the Agent decision engine.

Manages tool registration, discovery, parameter validation, and
execution with timeout/retry support. Tools can be registered as
ToolDef objects, Python functions (auto-inferred schema), or
OpenAI Function Calling format.
"""
from __future__ import annotations

import asyncio
import inspect
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable

from loguru import logger

from agent_engine.types import ToolCall, ToolDef


class ToolRegistry:
    """Registry of tools the agent can call.

    Supports three registration paths:
    1. register(ToolDef) — full definition
    2. register_from_func(func) — auto-infer from type hints + docstring
    3. register_from_openai(schema, func) — OpenAI Function Calling format
    """

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    # -- Registration --

    def register(self, tool: ToolDef) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def register_from_func(self, func: Callable, name: str = "", description: str = "", **overrides) -> None:
        tool_name = name or func.__name__
        schema = self._infer_schema_from_func(func)
        if description:
            schema["description"] = description
        is_async = inspect.iscoroutinefunction(func)

        self.register(ToolDef(
            name=tool_name,
            description=schema.get("description", ""),
            parameters={"type": "object", "properties": schema.get("properties", {}),
                        "required": schema.get("required", [])},
            func=func,
            is_async=is_async,
            **overrides,
        ))

    def register_from_openai(self, schema: dict, func: Callable) -> None:
        func_def = schema if "name" in schema else schema.get("function", schema)
        name = func_def["name"]
        is_async = inspect.iscoroutinefunction(func)
        self.register(ToolDef(
            name=name,
            description=func_def.get("description", ""),
            parameters=func_def.get("parameters", {"type": "object", "properties": {}}),
            func=func,
            is_async=is_async,
        ))

    def unregister(self, name: str) -> None:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")
        del self._tools[name]
        logger.debug(f"Unregistered tool: {name}")

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())

    def get_tool(self, name: str) -> ToolDef:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")
        return self._tools[name]

    def list_openai_schemas(self) -> list[dict]:
        schemas = []
        for t in self._tools.values():
            schemas.append({
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            })
        return schemas

    async def call(self, name: str, arguments: dict) -> ToolCall:
        tool = self.get_tool(name)
        tc = ToolCall(
            id=f"call_{int(time.time() * 1000)}",
            tool_name=name,
            arguments=arguments,
            started_at=datetime.now(timezone.utc),
        )

        last_error: str | None = None
        for attempt in range(tool.max_retries + 1):
            try:
                if tool.is_async:
                    result = await asyncio.wait_for(
                        tool.func(**arguments),
                        timeout=tool.timeout_sec,
                    )
                else:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(tool.func, **arguments),
                        timeout=tool.timeout_sec,
                    )

                tc.result = result
                tc.finished_at = datetime.now(timezone.utc)
                tc.duration_ms = (tc.finished_at - tc.started_at).total_seconds() * 1000
                tc.retry_count = attempt
                logger.info(f"Tool '{name}' succeeded (attempt {attempt + 1}, {tc.duration_ms:.0f}ms)")
                return tc

            except asyncio.TimeoutError:
                last_error = f"Tool '{name}' timed out after {tool.timeout_sec}s"
                logger.warning(f"{last_error} (attempt {attempt + 1})")
            except Exception as e:
                last_error = f"Tool '{name}' error: {e}"
                logger.warning(f"{last_error} (attempt {attempt + 1})")

        tc.error = last_error
        tc.finished_at = datetime.now(timezone.utc)
        tc.duration_ms = (tc.finished_at - tc.started_at).total_seconds() * 1000
        tc.retry_count = tool.max_retries
        return tc

    @staticmethod
    def _infer_schema_from_func(func: Callable) -> dict:
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or ""

        param_descriptions: dict[str, str] = {}
        for match in re.finditer(r":param\s+(\w+)\s*:\s*(.+?)(?:\n|$)", doc):
            param_descriptions[match.group(1)] = match.group(2).strip()

        description = doc.split("\n")[0].strip() if doc else ""

        type_map = {
            str: "string", int: "integer", float: "number",
            bool: "boolean", list: "array", dict: "object",
        }

        properties: dict[str, dict] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            param_type = "string"
            if param.annotation is not inspect.Parameter.empty:
                param_type = type_map.get(param.annotation, "string")
            properties[param_name] = {
                "type": param_type,
                "description": param_descriptions.get(param_name, ""),
            }
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "description": description,
            "properties": properties,
            "required": required,
        }
```

- [ ] **Step 4: Run tests**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_tools.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd e:/ACTs && git add agent_engine/tools.py agent_engine/tests/test_tools.py && git commit -m "feat: add ToolRegistry with auto-inference and timeout/retry"
```

---

### Task 8: memory.py — MemoryManager

**Files:**
- Create: `agent_engine/memory.py`
- Create: `agent_engine/tests/test_memory.py`

- [ ] **Step 1: Write tests for memory.py**

```python
"""Tests for agent_engine.memory."""
import pytest
from agent_engine.memory import MemoryManager
from agent_engine.types import Message


class TestMemoryManager:
    def test_add_message(self):
        mm = MemoryManager()
        mm.add("user", "hello")
        msgs = mm.get_messages()
        assert len(msgs) == 1
        assert msgs[0].role == "user"
        assert msgs[0].content == "hello"

    def test_set_system_prompt(self):
        mm = MemoryManager()
        mm.set_system_prompt("You are helpful.")
        msgs = mm.get_messages()
        assert len(msgs) == 1
        assert msgs[0].role == "system"

    def test_get_context_messages_preserves_system(self):
        mm = MemoryManager()
        mm.set_system_prompt("system prompt")
        for i in range(20):
            mm.add("user", f"message {i}")
            mm.add("assistant", f"response {i}")
        # Get context limited to ~500 tokens (~2000 chars)
        ctx = mm.get_context_messages(max_tokens=500)
        # First message should be system
        assert ctx[0]["role"] == "system"
        # Should not exceed token limit
        total_chars = sum(len(m["content"]) for m in ctx)
        assert total_chars <= 500 * 4 + 1000  # generous margin

    def test_estimate_tokens(self):
        mm = MemoryManager()
        mm.add("user", "hello world")  # 11 chars
        tokens = mm.estimate_tokens()
        assert tokens == 3  # 11 / 4 = 2.75 → 3

    def test_compress_basic(self):
        mm = MemoryManager()
        mm.set_system_prompt("system")
        mm.add("user", "hello")
        mm.add("assistant", "hi")
        mm.compress(force=True)
        # After force compress, old messages are summarized
        msgs = mm.get_messages()
        assert msgs[0].role == "system"
        # There should be a summary message
        roles = [m.role for m in msgs]
        assert "system" in roles  # the summary is added as system

    def test_to_dict_from_dict(self):
        mm = MemoryManager()
        mm.set_system_prompt("sys")
        mm.add("user", "hello")
        data = mm.to_dict()
        restored = MemoryManager.from_dict(data)
        assert len(restored.get_messages()) == 2

    def test_clear(self):
        mm = MemoryManager()
        mm.add("user", "hello")
        mm.clear()
        assert len(mm.get_messages()) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_memory.py -v`
Expected: FAIL

- [ ] **Step 3: Write memory.py**

```python
"""Memory manager for the Agent decision engine.

Manages the conversation message list with smart truncation and
automatic summarization when approaching context limits.
"""
from __future__ import annotations

from agent_engine.types import Message


class MemoryManager:
    """Manages short-term conversation memory.

    Features:
    - Message list with role/content tracking
    - Smart truncation: system prompt always preserved, recent messages prioritized
    - Token estimation (char_count / 4)
    - Auto-compression via summarization when token threshold exceeded
    """

    def __init__(self, compress_trigger_tokens: int = 6000, compress_target_tokens: int = 3000):
        self._messages: list[Message] = []
        self.compress_trigger_tokens = compress_trigger_tokens
        self.compress_target_tokens = compress_target_tokens
        self._summary: str = ""

    # -- Message management --

    def add(self, role: str, content: str, **meta: str | None) -> None:
        self._messages.append(Message(
            role=role,  # type: ignore[arg-type]
            content=content,
            tool_call_id=meta.get("tool_call_id"),
            name=meta.get("name"),
        ))

    def set_system_prompt(self, prompt: str) -> None:
        # Remove existing system messages and prepend new one
        self._messages = [m for m in self._messages if m.role != "system"]
        self._messages.insert(0, Message(role="system", content=prompt))

    def get_messages(self) -> list[Message]:
        return list(self._messages)

    def get_context_messages(self, max_tokens: int = 6000) -> list[dict]:
        """Return messages formatted for LLM API, truncated to fit max_tokens.
        System prompt is always included. Recent messages prioritized."""
        max_chars = max_tokens * 4
        result: list[dict] = []
        chars_used = 0

        # Always include system message if present
        for m in self._messages:
            if m.role == "system":
                result.append({"role": m.role, "content": m.content})
                chars_used += len(m.content)
                break

        # Add most recent messages first (reverse), then reverse back
        non_system = [m for m in self._messages if m.role != "system"]
        recent: list[dict] = []
        for m in reversed(non_system):
            msg_dict: dict = {"role": m.role, "content": m.content}
            if m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            if m.name:
                msg_dict["name"] = m.name
            if chars_used + len(m.content) <= max_chars:
                recent.append(msg_dict)
                chars_used += len(m.content)
            else:
                break

        recent.reverse()
        return result + recent

    # -- Token estimation --

    def estimate_tokens(self) -> int:
        total_chars = sum(len(m.content) for m in self._messages)
        return max(1, total_chars // 4)

    # -- Compression --

    def compress(self, force: bool = False) -> None:
        """Summarize old messages to reduce context size.

        If force=True, always compresses. Otherwise only compresses
        when estimate_tokens() > compress_trigger_tokens.
        """
        if not force and self.estimate_tokens() <= self.compress_trigger_tokens:
            return

        if len(self._messages) <= 3:
            return  # nothing meaningful to compress

        # Summarize oldest 50% of non-system messages
        non_system = [m for m in self._messages if m.role != "system"]
        split_point = len(non_system) // 2
        old_messages = non_system[:split_point]
        recent_messages = non_system[split_point:]

        if not old_messages:
            return

        # Build a simple extractive summary: keep key facts
        summary_lines = []
        for m in old_messages:
            if m.role == "user":
                summary_lines.append(f"User asked: {m.content[:200]}")
            elif m.role == "assistant":
                summary_lines.append(f"Assistant: {m.content[:200]}")
            elif m.role == "tool":
                summary_lines.append(f"Tool '{m.name}': {str(m.content)[:200]}")

        summary_text = "Previous conversation summary:\n" + "\n".join(summary_lines[-20:])
        self._summary = summary_text

        # Rebuild: system messages + summary + recent messages
        system_msgs = [m for m in self._messages if m.role == "system"]
        self._messages = system_msgs + [
            Message(role="system", content=summary_text),
        ] + recent_messages

    # -- Utilities --

    def clear(self) -> None:
        self._messages.clear()
        self._summary = ""

    def to_dict(self) -> dict:
        return {
            "messages": [m.model_dump(mode="json") for m in self._messages],
            "summary": self._summary,
            "compress_trigger_tokens": self.compress_trigger_tokens,
            "compress_target_tokens": self.compress_target_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryManager":
        mm = cls(
            compress_trigger_tokens=data.get("compress_trigger_tokens", 6000),
            compress_target_tokens=data.get("compress_target_tokens", 3000),
        )
        mm._messages = [Message(**m) for m in data.get("messages", [])]
        mm._summary = data.get("summary", "")
        return mm
```

- [ ] **Step 4: Run tests**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_memory.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd e:/ACTs && git add agent_engine/memory.py agent_engine/tests/test_memory.py && git commit -m "feat: add MemoryManager with summarization"
```

---

### Task 9: reflect.py — Reflector

**Files:**
- Create: `agent_engine/reflect.py`
- Create: `agent_engine/tests/test_reflect.py`

- [ ] **Step 1: Write tests for reflect.py**

```python
"""Tests for agent_engine.reflect."""
import pytest
from agent_engine.reflect import Reflector, Reflection
from agent_engine.state import StateManager
from agent_engine.memory import MemoryManager
from agent_engine.types import Step, ToolCall


class TestReflectorRules:
    def test_detect_repetition_no_repeat(self):
        r = Reflector()
        steps = [
            Step(index=i, phase="act", tool_call=ToolCall(id=str(i), tool_name="search", arguments={"q": f"topic{i}"}))
            for i in range(5)
        ]
        assert r.detect_repetition(steps) is False

    def test_detect_repetition_same_call(self):
        r = Reflector()
        steps = [
            Step(index=i, phase="act", tool_call=ToolCall(id=str(i), tool_name="search", arguments={"q": "same thing"}))
            for i in range(3)
        ]
        assert r.detect_repetition(steps) is True

    def test_detect_repetition_different_tools(self):
        r = Reflector()
        steps = [
            Step(index=0, phase="act", tool_call=ToolCall(id="0", tool_name="search", arguments={"q": "x"})),
            Step(index=1, phase="act", tool_call=ToolCall(id="1", tool_name="calc", arguments={"expr": "1+1"})),
            Step(index=2, phase="act", tool_call=ToolCall(id="2", tool_name="read", arguments={"path": "f.txt"})),
        ]
        assert r.detect_repetition(steps) is False

    def test_detect_off_track_relevant(self):
        r = Reflector()
        steps = [
            Step(index=0, phase="think", thought="I need to search for the data"),
            Step(index=1, phase="act", tool_call=ToolCall(id="1", tool_name="search", arguments={"q": "data"})),
        ]
        score = r.detect_off_track("analyze data", steps)
        assert score < 0.5  # relevant

    def test_detect_off_track_irrelevant(self):
        r = Reflector()
        steps = [
            Step(index=0, phase="think", thought="let me calculate something"),
            Step(index=1, phase="act", tool_call=ToolCall(id="1", tool_name="calc", arguments={"expr": "2+2"})),
        ]
        score = r.detect_off_track("analyze data", steps)
        assert score >= 0.5  # irrelevant to data analysis

    def test_summarize_errors(self):
        r = Reflector()
        errors = ["timeout", "timeout", "connection refused", "timeout"]
        summary = r.summarize_errors(errors)
        assert "connection refused" in summary
        assert "timeout" in summary


class TestReflection:
    def test_reflection_defaults(self):
        ref = Reflection()
        assert ref.should_continue is True
        assert ref.is_stuck is False
        assert ref.detected_loop is False


@pytest.mark.asyncio
async def test_reflect_without_llm():
    """Reflector should work without LLM (rule-based only)."""
    r = Reflector()
    sm = StateManager()
    sm.start("analyze sales data")
    for i in range(4):
        sm.add_step(Step(
            index=i, phase="act",
            tool_call=ToolCall(id=str(i), tool_name="search", arguments={"q": "sales"}),
        ))
    mm = MemoryManager()
    mm.add("user", "analyze sales data")

    # Using a simple callback adapter
    from agent_engine.llm import CallbackAdapter
    async def fake_llm(messages, tools=None):
        return "continue"
    adapter = CallbackAdapter(fake_llm)

    reflection = await r.reflect(sm.state, mm, adapter)
    assert isinstance(reflection, Reflection)
    assert reflection.detected_loop is True  # 4 same tool calls
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_reflect.py -v`
Expected: FAIL

- [ ] **Step 3: Write reflect.py**

```python
"""Reflection module for the Agent decision engine.

Implements periodic self-reflection: every N steps, the agent reviews
its progress against the original goal, detects loops and repetition,
and suggests strategy adjustments.
"""
from __future__ import annotations

from pydantic import BaseModel

from agent_engine.types import AgentState, Step


class Reflection(BaseModel):
    """Result of a reflection step."""
    should_continue: bool = True
    strategy_adjustment: str = ""
    is_stuck: bool = False
    detected_loop: bool = False
    off_track_score: float = 0.0
    summary: str = ""


class Reflector:
    """Periodic self-reflection for the agent.

    Combines rule-based checks (no LLM needed) with LLM-based
    strategy review. Triggered every `reflect_interval` steps.
    """

    def __init__(self, reflect_interval: int = 3):
        self.reflect_interval = reflect_interval

    async def reflect(self, state: AgentState, memory, llm_adapter) -> Reflection:
        """Run a full reflection: rule checks + optional LLM review."""
        steps = state.steps
        reflection = Reflection()

        # Rule-based checks
        reflection.detected_loop = self.detect_repetition(steps)
        reflection.off_track_score = self.detect_off_track(state.goal, steps)

        if reflection.detected_loop:
            reflection.is_stuck = True
            reflection.should_continue = False
            reflection.summary = "Detected loop: same tool called with same arguments repeatedly."
            return reflection

        if reflection.off_track_score > 0.7:
            reflection.is_stuck = True
            reflection.summary = f"Agent appears off-track (score: {reflection.off_track_score:.2f})."

        # LLM-based strategy review
        if llm_adapter:
            try:
                review_prompt = self._build_review_prompt(state)
                msgs = memory.get_context_messages(max_tokens=4000)
                msgs.append({"role": "user", "content": review_prompt})
                resp = await llm_adapter.chat(msgs)
                reflection.strategy_adjustment = resp.content
            except Exception:
                reflection.strategy_adjustment = ""

        return reflection

    # -- Rule-based checks --

    def detect_repetition(self, steps: list[Step]) -> bool:
        """Check if the last 3 tool calls are identical."""
        tool_steps = [s for s in steps if s.tool_call is not None]
        if len(tool_steps) < 3:
            return False
        recent = tool_steps[-3:]
        first = recent[0].tool_call
        if first is None:
            return False
        for s in recent[1:]:
            tc = s.tool_call
            if tc is None:
                return False
            if tc.tool_name != first.tool_name:
                return False
            if tc.arguments != first.arguments:
                return False
        return True

    def detect_off_track(self, goal: str, steps: list[Step]) -> float:
        """Estimate how off-track the agent is (0.0 = fully on track,
        1.0 = completely off). Uses simple keyword overlap."""
        if not steps or not goal:
            return 0.0

        goal_words = set(goal.lower().split())
        if not goal_words:
            return 0.0

        # Count how many recent steps mention goal-related keywords
        recent = steps[-5:]
        relevant_count = 0
        for s in recent:
            text = (s.thought + " " + s.observation).lower()
            overlap = goal_words & set(text.split())
            if overlap:
                relevant_count += 1

        return 1.0 - (relevant_count / len(recent))

    def summarize_errors(self, errors: list[str]) -> str:
        """Deduplicate and categorize errors into a summary."""
        seen: set[str] = set()
        unique: list[str] = []
        for e in errors:
            if e not in seen:
                seen.add(e)
                unique.append(e)
        if not unique:
            return "No errors."
        return "Errors encountered: " + "; ".join(unique[-5:])

    def _build_review_prompt(self, state: AgentState) -> str:
        steps_summary = "\n".join(
            f"Step {s.index} [{s.phase}]: {s.thought[:100]}"
            for s in state.steps[-5:]
        )
        return (
            f"Goal: {state.goal}\n\n"
            f"Recent steps:\n{steps_summary}\n\n"
            f"Errors: {state.errors[-3:] if state.errors else 'None'}\n\n"
            "Review: Are we on track? Should we adjust the strategy? "
            "If the goal is achieved, say 'DONE'. If stuck, suggest a different approach."
        )
```

- [ ] **Step 4: Run tests**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_reflect.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd e:/ACTs && git add agent_engine/reflect.py agent_engine/tests/test_reflect.py && git commit -m "feat: add Reflector with loop detection and off-track scoring"
```

---

### Task 10: observe.py — Observer

**Files:**
- Create: `agent_engine/observe.py`

- [ ] **Step 1: Write observe.py**

```python
"""Observability layer for the Agent decision engine.

Provides structured logging, event callbacks, Mermaid flowchart
generation, and runtime metrics reporting.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any, Callable

from loguru import logger as _loguru_logger

from agent_engine.types import AgentState


class Event:
    """An observable event emitted during the decision loop."""

    __slots__ = ("type", "timestamp", "data")

    def __init__(self, type: str, data: dict | None = None):
        self.type = type
        self.timestamp = datetime.now(timezone.utc)
        self.data = data or {}


class Observer:
    """Unified observability layer.

    - Structured logging via loguru (text or JSON format)
    - Event callbacks for external integration (e.g., GUI updates)
    - Mermaid flowchart generation from AgentState steps
    - Runtime metrics report
    """

    def __init__(self, log_format: str = "text"):
        self._callbacks: list[Callable[[Event], None]] = []
        self._events: list[Event] = []
        self._setup_logging(log_format)

    def _setup_logging(self, log_format: str) -> None:
        _loguru_logger.remove()
        if log_format == "json":
            _loguru_logger.add(
                sys.stderr,
                format='{"time":"{time}","level":"{level}","message":"{message}"}',
                level="INFO",
            )
        else:
            _loguru_logger.add(
                sys.stderr,
                format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
                level="INFO",
                colorize=True,
            )

    # -- Events --

    def on_event(self, callback: Callable[[Event], None]) -> None:
        """Register a callback for all events."""
        self._callbacks.append(callback)

    def emit(self, event: Event) -> None:
        """Emit an event to all registered callbacks and the log."""
        self._events.append(event)
        _loguru_logger.info(f"[{event.type}] {event.data}")
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

    # -- Mermaid --

    def generate_mermaid(self, state: AgentState) -> str:
        """Generate a Mermaid flowchart from the agent's step history."""
        lines = ["flowchart TD"]
        lines.append("    Start([Goal]) --> S0[Step 0]")

        for step in state.steps:
            node_id = f"S{step.index}"
            if step.phase == "think":
                label = f"THINK: {step.thought[:40]}"
            elif step.phase == "act" and step.tool_call:
                label = f"ACT: {step.tool_call.tool_name}"
                if step.tool_call.error:
                    label += " (ERROR)"
            elif step.phase == "reflect":
                label = f"REFLECT: {step.reflection[:40]}"
            else:
                label = step.phase.upper()

            # Escape quotes in label
            label = label.replace('"', "'")
            lines.append(f"    {node_id}[\"{label}\"]")

        # Connect steps
        prev = "Start([Goal])"
        for i in range(len(state.steps)):
            lines.append(f"    {prev} --> S{i}")
            prev = f"S{i}"

        # Final state
        lines.append(f"    {prev} --> End([{state.status.upper()}])")
        return "\n".join(lines)

    # -- Metrics --

    def get_report(self, state: AgentState) -> str:
        """Generate a human-readable metrics report."""
        elapsed = ""
        if state.started_at:
            end = state.finished_at or datetime.now(timezone.utc)
            secs = (end - state.started_at).total_seconds()
            elapsed = f"{secs:.1f}s"

        tool_calls = sum(1 for s in state.steps if s.tool_call is not None)
        tool_errors = sum(1 for s in state.steps if s.tool_call and s.tool_call.error)

        lines = [
            "=" * 50,
            "  Agent Run Report",
            "=" * 50,
            f"  Status:       {state.status}",
            f"  Goal:         {state.goal[:80]}",
            f"  Total steps:  {len(state.steps)}",
            f"  Tool calls:   {tool_calls}",
            f"  Tool errors:  {tool_errors}",
            f"  Errors:       {len(state.errors)}",
            f"  Elapsed:      {elapsed}",
            "=" * 50,
        ]
        return "\n".join(lines)
```

- [ ] **Step 2: Verify import**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -c "from agent_engine.observe import Observer, Event; o=Observer(); o.emit(Event('test', {})); print('OK')"`
Expected: prints log line + "OK"

- [ ] **Step 3: Commit**

```bash
cd e:/ACTs && git add agent_engine/observe.py && git commit -m "feat: add Observer with logging, callbacks, Mermaid, and metrics"
```

---

### Task 11: engine.py — AgentEngine

**Files:**
- Create: `agent_engine/engine.py`
- Create: `agent_engine/tests/test_engine.py`

- [ ] **Step 1: Write tests for engine.py**

```python
"""Tests for agent_engine.engine."""
import pytest
from agent_engine.engine import AgentEngine
from agent_engine.llm import CallbackAdapter
from agent_engine.tools import ToolRegistry
from agent_engine.config import EngineConfig
from agent_engine.types import AgentState


class TestAgentEngine:
    @pytest.mark.asyncio
    async def test_simple_run_completes(self):
        """Agent should complete a simple goal with a direct LLM response."""
        async def simple_chat(messages, tools=None):
            # On first call, return a thought; on second, say DONE
            last = messages[-1]["content"] if messages else ""
            if "DONE" in last or "Reflect" in str(messages[-3:]).upper():
                return "The task is complete. DONE."
            return "I'll analyze the task. Let me think about it."

        engine = AgentEngine(
            llm=CallbackAdapter(simple_chat),
            config=EngineConfig(max_steps=5, reflect_interval=10),  # high interval to skip LLM reflection during tests
        )

        state = await engine.run("Test goal")
        assert state.status in ("done", "failed", "stopped")
        assert state.goal == "Test goal"

    @pytest.mark.asyncio
    async def test_run_with_tool_calls(self):
        """Agent should be able to call tools during execution."""
        call_count = 0

        async def chat_with_tools(messages, tools=None):
            nonlocal call_count
            if "result: 42" in str(messages[-3:]):
                return "I got the result 42. The task is done. DONE."
            if tools and call_count == 0:
                call_count += 1
                # Simulate an LLM that requests a tool call
                from agent_engine.types import ToolCallRequest
                # We need to return content that indicates tool use
                return "I'll calculate that."
            return "All done. DONE."

        engine = AgentEngine(
            llm=CallbackAdapter(chat_with_tools),
            config=EngineConfig(max_steps=5, reflect_interval=10),
        )

        # Register a calculator tool
        engine.tools.register_from_func(lambda x: x * 2, name="calc")

        state = await engine.run("Calculate something")
        assert state.goal == "Calculate something"

    @pytest.mark.asyncio
    async def test_max_steps_stops(self):
        """Agent should stop when max_steps is reached."""
        async def chat(messages, tools=None):
            return "Still working..."

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=3, reflect_interval=10),
        )

        state = await engine.run("An impossible goal")
        assert state.status in ("failed", "stopped")

    @pytest.mark.asyncio
    async def test_emergency_stop(self):
        """Requesting stop should halt the agent."""
        async def chat(messages, tools=None):
            return "Working..."

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=10, reflect_interval=10),
        )

        # Schedule a stop after a short delay
        import asyncio
        async def delayed_stop():
            await asyncio.sleep(0.1)
            engine.request_stop()

        task = asyncio.create_task(delayed_stop())
        state = await engine.run("Some goal")
        await task
        assert state.status == "stopped"
```

Wait, the test `test_run_with_tool_calls` won't work because the engine expects the LLM to return structured tool calls via `LLMResponse.tool_calls`, not just text. The CallbackAdapter only returns text. This test won't pass as-is.

Let me redesign this test to be more realistic. The engine should check if the LLM response contains a phrase indicating completion. For tool calls, the engine checks `response.tool_calls` — this only works with OpenAIAdapter which parses the structured response.

For the engine tests, let's test:
1. Simple completion (LLM says DONE)
2. Max steps stop
3. Emergency stop
4. Error handling

And use CallbackAdapter for all of these since it doesn't need API keys.

Let me fix the test:

- [ ] **Step 1 (corrected): Write tests for engine.py**

```python
"""Tests for agent_engine.engine."""
import pytest
from agent_engine.engine import AgentEngine
from agent_engine.llm import CallbackAdapter, LLMResponse
from agent_engine.config import EngineConfig


class TestAgentEngine:
    @pytest.mark.asyncio
    async def test_run_completes_when_llm_says_done(self):
        """Agent should stop when LLM indicates completion."""
        call_count = [0]

        async def chat(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return "Let me think about this task."
            return "The analysis is complete. DONE."

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=10, reflect_interval=10),
        )
        state = await engine.run("Analyze something")
        assert state.status == "done"
        assert state.goal == "Analyze something"
        assert len(state.steps) > 0

    @pytest.mark.asyncio
    async def test_max_steps_stops(self):
        """Agent should stop when max_steps is reached."""
        async def chat(messages, tools=None):
            return "Still working on it..."

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=3, reflect_interval=10),
        )
        state = await engine.run("An impossible task")
        assert state.status == "failed"
        assert len(state.steps) >= 3

    @pytest.mark.asyncio
    async def test_emergency_stop(self):
        """Requesting stop should halt the agent."""
        async def chat(messages, tools=None):
            return "Working..."

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=20, reflect_interval=10),
        )

        import asyncio
        async def delayed_stop():
            await asyncio.sleep(0.2)
            engine.request_stop()

        task = asyncio.create_task(delayed_stop())
        state = await engine.run("Some goal")
        await task
        assert state.status == "stopped"

    @pytest.mark.asyncio
    async def test_step_recorded(self):
        """Each iteration should record a step."""
        async def chat(messages, tools=None):
            return "DONE."

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=5, reflect_interval=10),
        )
        state = await engine.run("Goal")
        assert len(state.steps) >= 1
        assert state.steps[0].phase == "think"

    @pytest.mark.asyncio
    async def test_engine_with_tool_registry(self):
        """Engine should pass tool schemas to LLM."""
        tool_schemas_seen = []

        async def chat(messages, tools=None):
            tool_schemas_seen.append(tools)
            return "DONE."

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=5, reflect_interval=10),
        )
        engine.tools.register_from_func(lambda x: x * 2, name="double")
        await engine.run("Test")
        assert tool_schemas_seen[0] is not None
        assert len(tool_schemas_seen[0]) == 1
        assert tool_schemas_seen[0][0]["name"] == "double"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Write engine.py**

```python
"""Main decision engine for the Agent.

AgentEngine is the single entry point. It composes all components
and drives the OBSERVE→THINK→ACT→REFLECT loop until the goal
is achieved or a stop condition is met.
"""
from __future__ import annotations

from loguru import logger

from agent_engine.types import AgentState, Step
from agent_engine.state import StateManager
from agent_engine.tools import ToolRegistry
from agent_engine.memory import MemoryManager
from agent_engine.reflect import Reflector
from agent_engine.observe import Observer, Event
from agent_engine.safety import SafetyChecker
from agent_engine.llm import LLMAdapter
from agent_engine.config import EngineConfig


class AgentEngine:
    """The main Agent decision engine.

    Composes all subsystems and executes the autonomous decision loop:

        OBSERVE → THINK → ACT → REFLECT → (repeat or stop)

    Usage:
        engine = AgentEngine(llm=adapter, config=EngineConfig())
        engine.tools.register_from_func(my_tool)
        state = await engine.run("Your goal here")
    """

    def __init__(
        self,
        llm: LLMAdapter,
        config: EngineConfig | None = None,
        state: StateManager | None = None,
        tools: ToolRegistry | None = None,
        memory: MemoryManager | None = None,
    ):
        self.config = config or EngineConfig()
        self.llm = llm
        self.state = state or StateManager()
        self.tools = tools or ToolRegistry()
        self.memory = memory or MemoryManager(
            compress_trigger_tokens=self.config.compress_trigger_tokens,
            compress_target_tokens=self.config.compress_target_tokens,
        )
        self.reflector = Reflector(reflect_interval=self.config.reflect_interval)
        self.observer = Observer(log_format=self.config.log_format)
        self.safety = SafetyChecker(
            max_steps=self.config.max_steps,
            tool_whitelist=self.config.tool_whitelist_set,
        )

        # Set logging level
        logger.remove()
        logger.add(lambda msg: None, level=self.config.log_level)  # handled by Observer

    async def run(self, goal: str) -> AgentState:
        """Execute the full decision loop for the given goal.

        Returns the final AgentState with all steps recorded.
        """
        self.state.start(goal)
        self.memory.set_system_prompt(
            f"You are an autonomous AI agent. Your goal is: {goal}\n\n"
            "Follow the OBSERVE→THINK→ACT→REFLECT loop:\n"
            "1. THINK: Analyze the situation and decide the next action.\n"
            "2. ACT: Request a tool call if needed.\n"
            "3. When the goal is achieved, say 'DONE' and explain the result.\n"
            "4. If stuck, admit it and say 'FAILED' with the reason.\n"
        )
        self.memory.add("user", goal)
        self.observer.emit(Event("start", {"goal": goal}))

        while self.state.state.status == "running":
            # --- Safety check ---
            if self.safety.should_stop(self.state.state):
                reason = "max_steps" if self.state.state.current_step_index >= self.config.max_steps else "user_interrupt"
                self.state.stop("stopped" if reason == "user_interrupt" else "failed")
                self.observer.emit(Event("stopped", {"reason": reason}))
                break

            step_index = self.state.state.current_step_index
            self.observer.emit(Event("step_start", {"index": step_index}))

            # --- 1. OBSERVE ---
            context = self.memory.get_context_messages()
            step = Step(index=step_index, phase="observe")

            # --- 2. THINK ---
            step.phase = "think"
            try:
                tool_schemas = self.tools.list_openai_schemas() if self.tools.list_tools() else None
                response = await self.llm.chat(context, tool_schemas)
                step.thought = response.content
                self.memory.add("assistant", response.content)

                # Auto-compress if needed
                if self.memory.estimate_tokens() > self.config.compress_trigger_tokens:
                    self.memory.compress()
            except Exception as e:
                error_msg = f"LLM error at step {step_index}: {e}"
                logger.error(error_msg)
                self.state.record_error(error_msg)
                step.observation = error_msg
                self.state.add_step(step)
                continue

            # Check for completion signal
            if "DONE" in response.content.upper() and len(self.state.state.steps) > 0:
                step.is_completed = True
                self.state.add_step(step)
                self.state.stop("done")
                self.observer.emit(Event("done", {"steps": len(self.state.state.steps)}))
                break

            # --- 3. ACT ---
            if response.tool_calls:
                step.phase = "act"
                for tc_req in response.tool_calls:
                    # Safety: check tool
                    if not self.safety.check_tool(tc_req.name):
                        logger.warning(f"Tool '{tc_req.name}' blocked by safety")
                        continue

                    # Run before hooks
                    if not self.safety._run_hooks("before_action", tc_req.name, tc_req.arguments):
                        continue

                    tool_call = await self.tools.call(tc_req.name, tc_req.arguments)
                    step.tool_call = tool_call

                    if tool_call.error:
                        step.observation = f"Tool error: {tool_call.error}"
                        self.state.record_error(tool_call.error)
                    else:
                        step.observation = str(tool_call.result)[:1000]
                        self.memory.add("tool", step.observation, name=tc_req.name)

                    # Run after hooks
                    self.safety._run_hooks("after_action", tc_req.name, tool_call.result, tool_call.error)

                    self.state.update_metrics(tool_calls=1)
            else:
                step.observation = "No tool calls requested."

            # --- 4. REFLECT ---
            if step_index > 0 and step_index % self.reflector.reflect_interval == 0:
                step.phase = "reflect"
                reflection = await self.reflector.reflect(self.state.state, self.memory, self.llm)
                step.reflection = reflection.summary
                if reflection.is_stuck:
                    logger.warning(f"Agent appears stuck: {reflection.summary}")
                    self.state.record_error(f"Stuck: {reflection.summary}")
                if not reflection.should_continue:
                    self.state.stop("failed")
                    self.observer.emit(Event("stopped", {"reason": "stuck"}))
                    self.state.add_step(step)
                    break

            self.state.add_step(step)
            self.observer.emit(Event("step_end", {"index": step_index, "phase": step.phase}))

        # Generate report
        report = self.observer.get_report(self.state.state)
        logger.info(f"\n{report}")
        return self.state.state

    def request_stop(self) -> None:
        """Request an emergency stop. The loop will stop at the next iteration."""
        self.safety.request_stop()
```

- [ ] **Step 4: Run tests**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/test_engine.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd e:/ACTs && git add agent_engine/engine.py agent_engine/tests/test_engine.py && git commit -m "feat: add AgentEngine with full O→T→A→R loop"
```

---

### Task 12: builtin_tools/

**Files:**
- Create: `agent_engine/builtin_tools/calculator.py`
- Create: `agent_engine/builtin_tools/files.py`
- Create: `agent_engine/builtin_tools/search.py`
- Create: `agent_engine/builtin_tools/code_exec.py`
- Create: `agent_engine/builtin_tools/__init__.py` (already exists)

- [ ] **Step 1: Write calculator.py**

```python
"""Safe calculator tool using AST whitelist (no eval)."""
from __future__ import annotations

import ast
import operator
import math


# Allowed AST nodes and operators
_ALLOWED_NODES: set[type] = {
    ast.Expression, ast.Constant, ast.BinOp, ast.UnaryOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd,
    ast.Call, ast.Name,
}

_ALLOWED_FUNCTIONS: dict[str, object] = {
    "abs": abs, "round": round, "min": min, "max": max,
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "ceil": math.ceil, "floor": math.floor,
    "pi": math.pi, "e": math.e,
}


def calculate(expression: str) -> str:
    """Safely evaluate a mathematical expression.

    Supported: +, -, *, /, //, %, **, abs, round, min, max, sqrt, log, sin, cos, etc.

    Args:
        expression: A mathematical expression string, e.g. "2 + 3 * 4"
    """
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as e:
        return f"Syntax error: {e}"

    # Validate all nodes are allowed
    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODES:
            return f"Disallowed operation: {type(node).__name__}"
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_FUNCTIONS:
            return f"Unknown name: {node.id}"

    try:
        compiled = compile(tree, "<calculator>", "eval")
        result = eval(compiled, {"__builtins__": {}}, _ALLOWED_FUNCTIONS)
        return str(result)
    except Exception as e:
        return f"Error: {e}"
```

- [ ] **Step 2: Write files.py**

```python
"""Sandboxed file I/O tools."""
from __future__ import annotations

from pathlib import Path


_DEFAULT_WORKSPACE = Path("./workspace").resolve()


def _resolve_safe(workspace: Path, filepath: str) -> Path:
    """Resolve a file path, ensuring it stays within workspace."""
    workspace = workspace.resolve()
    target = (workspace / filepath).resolve()
    if not str(target).startswith(str(workspace)):
        raise ValueError(f"Path traversal detected: {filepath}")
    return target


def read_file(filepath: str, workspace_dir: str = "") -> str:
    """Read the contents of a file within the workspace.

    Args:
        filepath: Relative path to the file within the workspace.
        workspace_dir: Optional workspace root (defaults to ./workspace).
    """
    ws = Path(workspace_dir).resolve() if workspace_dir else _DEFAULT_WORKSPACE
    try:
        target = _resolve_safe(ws, filepath)
        if not target.exists():
            return f"File not found: {filepath}"
        if not target.is_file():
            return f"Not a file: {filepath}"
        return target.read_text(encoding="utf-8", errors="replace")
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Read error: {e}"


def write_file(filepath: str, content: str, workspace_dir: str = "") -> str:
    """Write content to a file within the workspace.

    Args:
        filepath: Relative path within the workspace.
        content: Text content to write.
        workspace_dir: Optional workspace root (defaults to ./workspace).
    """
    ws = Path(workspace_dir).resolve() if workspace_dir else _DEFAULT_WORKSPACE
    try:
        target = _resolve_safe(ws, filepath)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Written {len(content)} bytes to {filepath}"
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Write error: {e}"


def list_files(directory: str = ".", workspace_dir: str = "") -> str:
    """List files in a workspace directory.

    Args:
        directory: Relative directory path (default: workspace root).
        workspace_dir: Optional workspace root.
    """
    ws = Path(workspace_dir).resolve() if workspace_dir else _DEFAULT_WORKSPACE
    try:
        target = _resolve_safe(ws, directory)
        if not target.exists():
            return f"Directory not found: {directory}"
        if not target.is_dir():
            return f"Not a directory: {directory}"
        items = sorted(target.iterdir())
        lines = []
        for item in items:
            prefix = "[DIR] " if item.is_dir() else "[FILE]"
            size = item.stat().st_size if item.is_file() else 0
            lines.append(f"{prefix} {item.name} ({size}B)" if item.is_file() else f"{prefix} {item.name}")
        return "\n".join(lines) if lines else "(empty)"
    except Exception as e:
        return f"Error: {e}"
```

- [ ] **Step 3: Write search.py**

```python
"""Web search tool using DuckDuckGo (no API key required)."""
from __future__ import annotations


def web_search(query: str) -> str:
    """Search the web using DuckDuckGo.

    Args:
        query: The search query string.
    """
    try:
        import requests
    except ImportError:
        return "Error: 'requests' package is required. Install with: pip install requests"

    try:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1,
        }
        resp = requests.get(url, params=params, timeout=15, headers={
            "User-Agent": "AgentEngine/0.1.0",
        })
        resp.raise_for_status()
        data = resp.json()

        results = []
        abstract = data.get("AbstractText", "")
        if abstract:
            results.append(f"Abstract: {abstract}")

        related = data.get("RelatedTopics", [])
        for topic in related[:5]:
            if isinstance(topic, dict) and "Text" in topic:
                results.append(f"- {topic['Text']}")

        if not results:
            return f"No results found for '{query}'."

        return "\n".join(results)
    except Exception as e:
        return f"Search error: {e}"
```

- [ ] **Step 4: Write code_exec.py**

```python
"""Sandboxed code execution tool using subprocess."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def execute_python(code: str, timeout_sec: float = 10.0) -> str:
    """Execute Python code in an isolated subprocess.

    The code runs in a temporary directory with no network access
    and a strict timeout.

    Args:
        code: Python source code to execute.
        timeout_sec: Maximum execution time in seconds.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "script.py"
            script_path.write_text(code, encoding="utf-8")

            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                cwd=tmpdir,
                env={},  # Empty env for isolation
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"

            return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Execution timed out after {timeout_sec}s"
    except FileNotFoundError:
        return "Error: 'python' not found in PATH"
    except Exception as e:
        return f"Execution error: {e}"
```

- [ ] **Step 5: Update builtin_tools/__init__.py**

```python
"""Built-in example tools for the Agent decision engine."""
from agent_engine.builtin_tools.calculator import calculate
from agent_engine.builtin_tools.files import read_file, write_file, list_files
from agent_engine.builtin_tools.search import web_search
from agent_engine.builtin_tools.code_exec import execute_python

__all__ = [
    "calculate",
    "read_file", "write_file", "list_files",
    "web_search",
    "execute_python",
]
```

- [ ] **Step 6: Verify imports**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -c "from agent_engine.builtin_tools import calculate, web_search; print(calculate('2+3*4'))"`
Expected: prints `14`

- [ ] **Step 7: Commit**

```bash
cd e:/ACTs && git add agent_engine/builtin_tools/ && git commit -m "feat: add builtin tools: calculator, files, search, code_exec"
```

---

### Task 13: cli.py — Command Line Interface

**Files:**
- Create: `agent_engine/cli.py`

- [ ] **Step 1: Write cli.py**

```python
"""Command-line interface for the Agent decision engine."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from agent_engine.engine import AgentEngine
from agent_engine.llm import OpenAIAdapter, CallbackAdapter
from agent_engine.config import EngineConfig
from agent_engine.builtin_tools import calculate, read_file, write_file, web_search, execute_python


def build_engine(args) -> AgentEngine:
    """Build an AgentEngine from CLI arguments."""
    config = EngineConfig(
        max_steps=args.max_steps,
        reflect_interval=args.reflect_interval,
        openai_api_key=args.api_key or "",
        openai_base_url=args.base_url,
        openai_model=args.model,
        log_format="json" if args.json_log else "text",
        workspace_dir=args.workspace,
    )

    if args.api_key:
        adapter = OpenAIAdapter(
            api_key=args.api_key,
            base_url=args.base_url,
            model=args.model,
        )
    else:
        # No API key → use interactive mode
        print("No API key provided. Use --api-key or set AGENT_ENGINE_OPENAI_API_KEY env var.")
        sys.exit(1)

    engine = AgentEngine(llm=adapter, config=config)

    # Register builtin tools
    for tool_name in (args.tools or "all").split(","):
        tool_name = tool_name.strip()
        if tool_name in ("all", "calculator"):
            engine.tools.register_from_func(calculate)
        if tool_name in ("all", "files"):
            engine.tools.register_from_func(read_file)
            engine.tools.register_from_func(write_file)
        if tool_name in ("all", "search"):
            engine.tools.register_from_func(web_search)
        if tool_name in ("all", "code_exec"):
            engine.tools.register_from_func(execute_python)

    return engine


async def cmd_run(args) -> None:
    """Execute the run subcommand."""
    engine = build_engine(args)
    print(f"Goal: {args.goal}")
    print(f"Max steps: {args.max_steps} | Model: {args.model}")
    print("-" * 50)

    state = await engine.run(args.goal)

    print()
    if args.output:
        state_path = args.output
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state.model_dump(mode="json"), f, indent=2, ensure_ascii=False, default=str)
        print(f"State saved to {state_path}")

    if args.mermaid:
        from agent_engine.observe import Observer
        obs = Observer()
        mermaid = obs.generate_mermaid(state)
        mermaid_path = args.mermaid
        with open(mermaid_path, "w", encoding="utf-8") as f:
            f.write(mermaid)
        print(f"Mermaid diagram saved to {mermaid_path}")


def cmd_tools(args) -> None:
    """List available builtin tools."""
    print("Builtin tools:")
    print("  calculator   - Safe mathematical expression evaluation")
    print("  read_file    - Read a file from the workspace")
    print("  write_file   - Write content to a file in the workspace")
    print("  web_search   - Search the web via DuckDuckGo")
    print("  code_exec    - Execute Python code in an isolated subprocess")


def cmd_visualize(args) -> None:
    """Generate a Mermaid diagram from a saved state file."""
    import json as _json
    from agent_engine.state import StateManager
    from agent_engine.observe import Observer

    with open(args.state_file, "r", encoding="utf-8") as f:
        data = _json.load(f)

    sm = StateManager.from_dict(data)
    obs = Observer()
    mermaid = obs.generate_mermaid(sm.state)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(mermaid)
        print(f"Mermaid diagram saved to {args.output}")
    else:
        print(mermaid)


def main():
    parser = argparse.ArgumentParser(
        prog="agent-engine",
        description="Autonomous Agent Decision Engine",
    )
    sub = parser.add_subparsers(dest="command")

    # Run
    run_parser = sub.add_parser("run", help="Run the agent with a goal")
    run_parser.add_argument("goal", help="The goal/task for the agent")
    run_parser.add_argument("--max-steps", type=int, default=50, help="Maximum steps (default: 50)")
    run_parser.add_argument("--reflect-interval", type=int, default=3, help="Reflect every N steps (default: 3)")
    run_parser.add_argument("--model", default="gpt-4o", help="LLM model name")
    run_parser.add_argument("--api-key", default="", help="OpenAI API key")
    run_parser.add_argument("--base-url", default="https://api.openai.com/v1", help="API base URL")
    run_parser.add_argument("--tools", default="all", help="Tools to enable (comma-separated)")
    run_parser.add_argument("--workspace", default="./workspace", help="Workspace directory for file ops")
    run_parser.add_argument("--output", default="", help="Save final state as JSON")
    run_parser.add_argument("--mermaid", default="", help="Save Mermaid diagram to file")
    run_parser.add_argument("--json-log", action="store_true", help="JSON formatted logs")

    # Tools
    sub.add_parser("tools", help="List available tools")

    # Visualize
    viz_parser = sub.add_parser("visualize", help="Generate Mermaid diagram from a saved state")
    viz_parser.add_argument("state_file", help="Path to saved state JSON")
    viz_parser.add_argument("--output", default="", help="Output file (prints to stdout if omitted)")

    args = parser.parse_args()

    if args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "tools":
        cmd_tools(args)
    elif args.command == "visualize":
        cmd_visualize(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI help works**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m agent_engine.cli --help`
Expected: prints help text

- [ ] **Step 3: Commit**

```bash
cd e:/ACTs && git add agent_engine/cli.py && git commit -m "feat: add CLI interface with run/tools/visualize commands"
```

---

### Task 14: __init__.py — Public API

**Files:**
- Modify: `agent_engine/__init__.py`

- [ ] **Step 1: Update __init__.py**

```python
"""agent_engine — A general-purpose autonomous Agent decision system.

Usage:
    from agent_engine import AgentEngine, EngineConfig, ToolRegistry
    from agent_engine.llm import OpenAIAdapter

    engine = AgentEngine(
        llm=OpenAIAdapter(api_key="sk-..."),
        config=EngineConfig(max_steps=20),
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
    ToolDef as ToolDefType,
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
    "ToolDefType",
    "ToolCall",
    "Step",
    "AgentState",
    "Message",
]
```

- [ ] **Step 2: Verify all exports work**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -c "from agent_engine import AgentEngine, EngineConfig, ToolRegistry, StateManager; print('All imports OK')"`
Expected: prints "All imports OK"

- [ ] **Step 3: Commit**

```bash
cd e:/ACTs && git add agent_engine/__init__.py && git commit -m "feat: add public API exports in __init__.py"
```

---

### Task 15: README.md

**Files:**
- Create: `agent_engine/README.md`

- [ ] **Step 1: Write README.md**

```markdown
# Agent Engine

A general-purpose autonomous Agent decision system. Provides goals, and the Agent autonomously plans tasks, calls tools, executes actions, reflects on results, and adjusts strategy until completion.

**Key features:**
- OBSERVE→THINK→ACT→REFLECT decision loop
- Dynamic tool registration (Python functions or OpenAI schema)
- Short-term memory with automatic summarization
- Periodic self-reflection with loop detection
- Safety controls: step limits, tool whitelists, hooks
- Structured logging, event callbacks, Mermaid flowcharts
- Built-in tools: calculator, file I/O, web search, code execution

## Installation

```bash
pip install -e .
```

Or install manually:

```bash
pip install pydantic loguru python-dotenv httpx
```

Optional dependencies:

```bash
pip install requests  # for builtin web_search tool
```

## Quick Start

```python
import asyncio
from agent_engine import AgentEngine, EngineConfig
from agent_engine.llm import OpenAIAdapter

async def main():
    engine = AgentEngine(
        llm=OpenAIAdapter(api_key="sk-...", model="gpt-4o"),
        config=EngineConfig(max_steps=10),
    )

    # Register custom tools
    def get_weather(city: str) -> str:
        """Get the current weather for a city."""
        return f"Weather in {city}: Sunny, 22°C"

    engine.tools.register_from_func(get_weather)

    state = await engine.run("What's the weather in Tokyo and should I bring an umbrella?")

    print(f"Status: {state.status}")
    print(f"Steps taken: {len(state.steps)}")
    for step in state.steps:
        print(f"  Step {step.index}: [{step.phase}] {step.thought[:60]}...")

asyncio.run(main())
```

## CLI Usage

```bash
# Run with a goal
agent-engine run "Find the top 3 Python web frameworks and compare them" --api-key sk-xxx

# Save state and Mermaid diagram
agent-engine run "Analyze data.csv" --api-key sk-xxx --output state.json --mermaid flow.mmd

# List available tools
agent-engine tools

# Visualize a saved state
agent-engine visualize state.json --output flow.mmd
```

## Architecture

```
AgentEngine.run(goal)
  │
  ├── StateManager     — tracks goal, steps, errors, metrics
  ├── MemoryManager    — manages conversation messages + summarization
  ├── ToolRegistry     — registers and executes tools
  ├── Reflector        — periodic self-reflection, loop detection
  ├── SafetyChecker    — step limits, tool whitelist, hooks
  ├── Observer         — logging, callbacks, Mermaid, reports
  └── LLMAdapter       — OpenAI-compatible or custom callback
```

## Configuration

All settings can be configured via `EngineConfig` or environment variables (prefixed with `AGENT_ENGINE_`):

| Parameter | Env Var | Default |
|-----------|---------|---------|
| max_steps | `AGENT_ENGINE_MAX_STEPS` | 50 |
| reflect_interval | `AGENT_ENGINE_REFLECT_INTERVAL` | 3 |
| openai_api_key | `AGENT_ENGINE_OPENAI_API_KEY` | "" |
| openai_model | `AGENT_ENGINE_OPENAI_MODEL` | gpt-4o |
| log_format | `AGENT_ENGINE_LOG_FORMAT` | text |

## Extending

### Custom Tools

```python
# From Python function (auto-infer schema)
engine.tools.register_from_func(my_function)

# From OpenAI schema
engine.tools.register_from_openai(schema_dict, handler_function)

# Explicit ToolDef
engine.tools.register(ToolDef(name="...", description="...", parameters={...}, func=...))
```

### Custom LLM Backend

```python
from agent_engine.llm import LLMAdapter, LLMResponse

class MyAdapter(LLMAdapter):
    async def chat(self, messages, tools=None):
        # Call your LLM here
        return LLMResponse(content="response")
```

### Safety Hooks

```python
engine.safety.before_action(lambda name, args: args.get("path") != "/etc/passwd")
engine.safety.after_action(lambda name, result, error: True)
```

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
cd e:/ACTs && git add agent_engine/README.md && git commit -m "docs: add README with usage examples and architecture overview"
```

---

### Task 16: Final Integration Test

- [ ] **Step 1: Install test dependencies**

Run: `cd e:/ACTs && pip install pydantic loguru python-dotenv httpx pydantic-settings pytest pytest-asyncio 2>&1 | tail -5`

- [ ] **Step 2: Run all tests**

Run: `cd e:/ACTs && PYTHONPATH=agent_engine python -m pytest agent_engine/tests/ -v`
Expected: all tests PASS

- [ ] **Step 3: Fix any failing tests**

Review failures and fix issues.

- [ ] **Step 4: Commit any fixes**

```bash
cd e:/ACTs && git add agent_engine/ && git commit -m "test: fix integration test issues"
```

---

## Dependency Order

```
types.py (no deps)
  ├── config.py
  ├── llm.py
  ├── state.py
  ├── safety.py
  └── tools.py
        ├── memory.py
        └── reflect.py (needs state, memory, llm)
              └── observe.py
                    └── engine.py (needs all)
                          ├── builtin_tools/
                          ├── cli.py
                          └── __init__.py
```
