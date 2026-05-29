# Agent Decision Engine — Design Spec

**Date**: 2026-05-28
**Status**: Approved
**Scope**: Standalone Python library (`agent_engine/`)

## Overview

A general-purpose autonomous Agent decision system. Users provide a goal; the Agent autonomously plans tasks, calls tools, executes actions, reflects on results, and adjusts strategy until the goal is achieved or determined impossible.

**Key constraint**: No heavy frameworks (LangChain, LlamaIndex, AutoGPT). Core logic must be fully transparent — no black boxes.

## Architecture

**Pattern**: Modular components with direct method calls (no event bus).

```
agent_engine/
├── __init__.py          # Exports AgentEngine, all core classes
├── pyproject.toml       # pydantic, loguru, python-dotenv, httpx
├── README.md
│
├── engine.py            # AgentEngine.run() — main O→T→A→R loop
├── state.py             # StateManager — state machine + tracking
├── tools.py             # ToolRegistry — register/call/validate tools
├── memory.py            # MemoryManager — messages + auto-summarization
├── reflect.py           # Reflector — every-N-step self-reflection
├── observe.py           # Observer — logs/callbacks/Mermaid/metrics
├── safety.py            # SafetyChecker — step limits/whitelist/hooks
├── llm.py               # LLMAdapter + OpenAIAdapter + CallbackAdapter
├── types.py             # All Pydantic data models
├── config.py            # pydantic-settings global configuration
├── cli.py               # Command-line interface
│
├── builtin_tools/
│   ├── search.py        # Web search (DuckDuckGo)
│   ├── calculator.py    # Safe calculator (ast.parse whitelist)
│   ├── files.py         # File I/O (path sandbox)
│   └── code_exec.py     # Code execution (subprocess isolation)
│
└── tests/
    ├── test_engine.py
    ├── test_tools.py
    ├── test_memory.py
    ├── test_reflect.py
    └── test_safety.py
```

## Decision Loop

```
OBSERVE → THINK → ACT → REFLECT → (repeat or stop)
```

1. **Observe**: Gather context from MemoryManager (system prompt + recent messages)
2. **Think**: LLM reasons about next action, optionally requests tool calls
3. **Act**: Execute tool calls via ToolRegistry (with validation, timeout, retry)
4. **Reflect**: Every N steps (default 3), LLM reviews progress; rule-based checks detect loops/repetition

**Stop conditions**: goal achieved (LLM signals done), max_steps exhausted, emergency stop, or loop detected.

## Component Details

### 1. types.py — Pydantic Models

| Model | Purpose |
|-------|---------|
| `ToolDef` | Tool definition — name, description, JSON Schema params, func ref, timeout, retries |
| `ToolCall` | Tool invocation record — name, args, result, error, timing |
| `Step` | One loop iteration — phase, thought, tool_call, observation, reflection |
| `AgentState` | Full agent state — goal, sub_goals, steps, status, errors, metrics |
| `Message` | Chat message — role, content, tool_call_id, name |

### 2. state.py — StateManager

- State machine: `idle → running ⇄ paused → done/failed/stopped`
- Tracks: current step index, sub-goals, error history (deduplicated), runtime metrics
- Serialization: `to_dict()` / `from_dict()` for optional persistence

### 3. tools.py — ToolRegistry

**Three registration paths**:
1. `register(ToolDef)` — explicit definition
2. `register_from_func(func)` — auto-infer schema from type hints + docstring
3. `register_from_openai(schema, func)` — OpenAI Function Calling format

**Call pipeline**: whitelist check → parameter validation → timeout wrapping → execution → retry (if configured) → record result

Supports both sync and async tool functions.

### 4. memory.py — MemoryManager

- Message list storage with role/content/metadata
- `get_context_messages(max_tokens)` — smart truncation (system prompt always preserved, recent messages prioritized)
- Auto-compression: when estimated tokens > threshold (default 6000), summarize oldest 50% of messages
- Token estimation: `char_count / 4`
- Manual `compress()` with optional `force=True`

### 5. reflect.py — Reflector

- `reflect_interval`: every N steps (default 3)
- LLM-based reflection: reviews progress against goal, suggests strategy adjustments
- Rule-based checks (no LLM needed):
  - `detect_repetition()`: same tool + same args 3 consecutive times
  - `detect_off_track()`: keyword-based deviation score 0~1
  - `summarize_errors()`: deduplicate + categorize errors

### 6. observe.py — Observer

- Event callbacks: `on_event(callback)` for external integration
- Structured logging via loguru (JSON format optional)
- Mermaid flowchart generation from AgentState steps
- Metrics report: elapsed time, total steps, tool call count, success rate, token usage

### 7. engine.py — AgentEngine

The single entry point. Composes all components. `run(goal)` executes the full decision loop.

```python
engine = AgentEngine(llm=adapter, tools=registry)
state = await engine.run("Analyze data.csv and generate a report")
```

### 8. safety.py — SafetyChecker

- `max_steps`: hard limit (default 50)
- `tool_whitelist`: optional allowlist
- `confirm_sensitive`: tools requiring external confirmation (exec, shell, file_delete)
- `stop_requested`: emergency stop flag
- Hook system: `before_action(callback)`, `after_action(callback)` — return False to block

### 9. llm.py — LLM Adapter

- `LLMAdapter` (ABC): `chat(messages, tools) → LLMResponse`, `chat_stream(...) → AsyncGenerator`
- `OpenAIAdapter`: built-in httpx-based OpenAI-compatible client with retry
- `CallbackAdapter`: user-provided `async def chat_fn(messages, tools) → str`

### 10. config.py — Configuration

pydantic-settings with `.env` support. Configurable: max_steps, reflect_interval, compress_trigger_tokens, log_level, log_format (text/json).

## Built-in Tools

| Tool | Implementation | Safety |
|------|---------------|--------|
| `web_search` | DuckDuckGo via `requests` | Rate-limited, user-agent required |
| `calculator` | `ast.parse` whitelist (no eval) | Only safe operators/nodes allowed |
| `file_read/write` | Path sandboxed to workspace dir | Cannot escape `workspace/` |
| `code_exec` | `subprocess.run` with timeout | Isolated, no network by default |

## Key Design Decisions

- **Component communication**: Direct method calls, no event bus — traceable, transparent
- **State persistence**: Optional via `to_dict()`/`from_dict()` — library doesn't dictate storage
- **LLM calls**: async primary, sync as thin wrapper — supports concurrent tool calls
- **Tool execution**: async primary path, sync functions auto-wrapped — compatible with both
- **Config**: pydantic-settings + `.env` — type-safe with environment variable overrides

## Dependencies

```
pydantic>=2.0          # Data validation
loguru>=0.7            # Structured logging
python-dotenv>=1.0     # Environment variables
httpx>=0.25            # HTTP client for OpenAI adapter

# Optional
chromadb>=0.4          # Vector memory (future)
requests>=2.28         # For builtin web_search tool
```

## Notes

- All `run()`, `chat()`, `call()`, `compress()` methods are `async` — the engine is fully async-native.
- File I/O builtin tools are sandboxed to a configurable `workspace_dir` (defaults to `./workspace` relative to CWD).
- The library does NOT create any directories on import — only when `AgentEngine.run()` is called.

## CLI Interface

```bash
# Run with a goal
agent-engine run "Find the top 5 Python web frameworks and compare them"

# Run with custom config
agent-engine run "..." --max-steps 20 --model gpt-4o --api-key sk-xxx

# List registered tools
agent-engine tools

# Generate Mermaid diagram from a saved state
agent-engine visualize state.json
```
