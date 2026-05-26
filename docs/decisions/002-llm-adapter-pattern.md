# 002: LLM Adapter Pattern

**Date:** 2025 (Phase 1 MVP)

**Status:** Accepted

## Context

The app needs to support multiple LLM providers (OpenAI, OpenAI-compatible APIs, Anthropic, local models, etc.) through a unified interface. Each provider has different API formats, authentication, and streaming protocols.

## Decision

Use an abstract **LLMAdapter** base class with a **Factory** pattern:

```
LLMAdapter (ABC)
├── chat() → LLMResponse           # Non-streaming request
├── chat_stream() → AsyncGenerator  # SSE streaming
└── last_usage: dict               # Token usage from last call

LLMAdapterFactory.create(config, api_key) → LLMAdapter
```

## Rationale

- **Provider agnostic**: Core business logic (`Agent`, `Session`) never depends on specific API implementations
- **Testability**: `MockAdapter` allows testing without API keys or network
- **Extensibility**: New providers require only a new adapter class (e.g., `AnthropicAdapter`)
- **Streaming-first**: Both `chat()` and `chat_stream()` are first-class

## Current Implementations

| Adapter | Provider | Auth | Streaming |
|---------|----------|------|-----------|
| `MockAdapter` | `mock` | None | Echoes last user message word-by-word |
| `OpenAICompatAdapter` | `openai`, `openai_compat`, `custom` | Bearer token | SSE via httpx `aiter_lines()` |

## Consequences

- Adding a new provider (e.g., Anthropic, local Ollama) requires implementing two async methods
- The `chat_stream()` → `AsyncGenerator[str]` contract means callers must handle chunked output
- `last_usage` is set after streaming completes; token tracking happens in `Agent._record_usage()`
- Falls back to `MockAdapter` when no API key is configured (graceful degradation)

## Future Considerations

- Anthropic adapter with Messages API support
- Ollama / local LLM adapter
- Tool-calling / function-calling support
- Streaming token usage tracking (currently usage arrives at end of SSE stream)
