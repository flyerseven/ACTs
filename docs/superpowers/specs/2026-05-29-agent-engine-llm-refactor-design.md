# Agent Engine LLM Adapter Refactor Design

**Date:** 2026-05-29
**Status:** approved

## Goal

Unify LLM adapters for agent_engine into `src/llm/`, using a per-provider adapter pattern with factory routing. First provider: DeepSeek.

## Motivation

- `agent_engine/llm.py` has ~450 lines mixing ABC, DeepSeekAdapter, CallbackAdapter, and LLMResponse in one file
- `src/llm/` already has a clean per-provider structure (base.py, deepseek.py, factory.py)
- Two separate adapter hierarchies with similar but incompatible interfaces
- Adding a new provider requires touching both locations

## Architecture

```
src/llm/                          # Single source of truth for ALL LLM adapters
├── base.py                       # LLMResponse dataclass + LLMAdapter ABC
├── deepseek.py                   # DeepSeekAdapter(LLMAdapter)
├── mock.py                       # MockAdapter(LLMAdapter) — split from base.py
├── callback.py                   # CallbackAdapter(LLMAdapter) — wraps async fn for testing
├── factory.py                    # LLMAdapterFactory.create(LLMConfig, api_key)
└── __init__.py                   # Public re-exports

agent_engine/                     # Consumes src/llm, no own adapters
├── engine.py                     # Imports from src.llm.base
├── cli.py                        # Uses LLMAdapterFactory
├── config.py                     # Renamed config fields
└── (llm.py DELETED)              # Removed entirely
```

## LLMAdapter Interface (src/llm/base.py)

```python
@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict]     # [{"id":..., "name":..., "arguments":{...}}]
    usage: dict | None = None
    raw: dict = field(default_factory=dict)

class LLMAdapter(ABC):
    @abstractmethod
    async def chat(
        self, messages: list[dict], model: str,
        temperature: float = 0.7, max_tokens: int = 4096,
        tools: list[dict] | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
    async def chat_stream(
        self, messages: list[dict], model: str,
        temperature: float = 0.7, max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]: ...
```

Key change: `on_chunk` callback added so agent_engine can stream thought chunks to UI while still receiving full tool_calls at the end.

## DeepSeekAdapter (src/llm/deepseek.py)

Merge the richer agent_engine implementation into the existing file:

- **Constructor:** `__init__(api_key, base_url, timeout, max_retries)` — model is passed per-call
- **chat() with on_chunk:** SSE streaming path, accumulates content + tool_call deltas, calls `on_chunk` per text chunk
- **4xx fallback:** If streaming gets 4xx, automatically retry non-streaming
- **_sanitize_messages():** Remove `content: null` from tool_call messages
- **Thinking mode:** `thinking: bool = True`, `reasoning_effort: str = "medium"` — kept as optional keyword args
- **Retry:** Exponential backoff for connection errors (not for 4xx)
- **chat_stream():** Simple streaming, unchanged interface

## Factory (src/llm/factory.py)

```python
class LLMAdapterFactory:
    @staticmethod
    def create(config: LLMConfig, api_key: str) -> LLMAdapter:
        provider = (config.provider or "").lower()
        # if provider == "deepseek": ...
        # if provider == "openai": ...  (future)
        # if provider == "mock": ...
        raise ValueError(f"Unsupported provider: {config.provider}")
```

No structural change needed — already follows the right pattern.

## CallbackAdapter (src/llm/callback.py)

Move from `agent_engine/llm.py` to `src/llm/callback.py`. Wraps a user-provided async function for testing without real API keys. Handles coroutines returning `str`, `LLMResponse`, or async generators yielding chunks.

Used by: `test_engine.py`, `test_llm.py`, `test_reflect.py`.

## agent_engine Changes

### Delete
- `agent_engine/llm.py` — entire file (~450 lines)

### Modify

**agent_engine/engine.py:**
- `from src.llm.base import LLMAdapter, LLMResponse`
- `AgentEngine.__init__` accepts `src.llm.base.LLMAdapter`
- `self.llm.chat()` calls pass `model`, `temperature`, `max_tokens` from config

**agent_engine/config.py:**
- Rename: `openai_api_key` → `llm_api_key`
- Rename: `openai_base_url` → `llm_base_url`
- Rename: `openai_model` → `llm_model`
- Add: `llm_provider: str = "deepseek"`
- Add: `llm_temperature: float = 0.7`
- Add: `llm_max_tokens: int = 4096`
- Env prefix stays `AGENT_ENGINE_`

**agent_engine/__init__.py:**
- Remove `from agent_engine.llm import ...` exports

**agent_engine/cli.py:**
- Import `LLMAdapterFactory` from `src.llm.factory`
- Import `LLMConfig` from `src.core.models`
- Build adapter via factory instead of direct `DeepSeekAdapter(...)`

### Tests

Update `agent_engine/tests/test_llm.py` to test through `src.llm` adapters instead of deleted `agent_engine/llm.py`.

## Error Handling

- 4xx errors: non-streaming fallback, then raise RuntimeError
- Connection errors: exponential backoff up to max_retries
- API key missing: factory returns MockAdapter (matches existing src/llm behavior)
- Consecutive LLM errors: agent_engine stops after 3 (unchanged)

## Future: Pluggable Decision Systems

A future feature will allow an Agent to select different decision engines (e.g., ReAct, Tree-of-Thought, custom loops), not just the current OBSERVE→THINK→ACT→REFLECT loop.

Current design is compatible: `AgentEngine` accepts an `LLMAdapter` (now via `src.llm`), so different decision engines can share the same adapter layer. When that feature lands, the decision-loop logic in `engine.py` would be extracted behind an ABC (e.g., `DecisionStrategy`), and the LLM adapter layer stays unchanged.

## Non-Goals

- Adding OpenAI/Anthropic adapters (out of scope, factory is ready for them)
- Changing agent_engine's decision loop logic
- Changing GUI chat flow (continues using src/llm adapters as before)
- Moving tools/memory/state out of agent_engine
- Implementing pluggable decision systems (noted for future)
