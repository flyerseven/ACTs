# ACTs Architecture

## Overview

ACTs (Agent Creat Tools) is a PyQt6 desktop application for building, debugging, and orchestrating multi-Agent LLM teams. Users bring their own API keys, configure Agents locally, and chat with individual Agents or Agent teams. Phase 1 MVP supports single-Agent chat; Phase 2 adds Team orchestration.

```
┌─────────────────────────────────────────────────────┐
│                    main.py                          │
│   Entry point: CLI args → Store/Vault → MainWindow │
└──────────────────┬──────────────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│  core/  │  │   llm/   │  │   ui/    │
│ models  │  │ adapters │  │ PyQt GUI │
│ agent   │  │ factory  │  │ windows  │
│ session │  │          │  │ panels   │
│ team*   │  │          │  │ widgets  │
│ skill*  │  │          │  │ styles   │
└───┬─────┘  └────┬─────┘  └────┬─────┘
    │             │             │
    └──────┬──────┘             │
           ▼                    │
    ┌──────────────┐            │
    │  security/   │◄───────────┘
    │  vault       │
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │  storage/    │
    │  file_store  │
    │  yaml_io     │
    │  db*         │
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │  Acts/       │  ← file-system persistence
    │  Agents/     │
    │  Sessions/   │
    │  Team/       │
    │  .vault.enc  │
    └──────────────┘

* = supplementary / Phase 2
```

## Layer Descriptions

### `main.py` — Entry Point

- Parses CLI arguments (`--health`, `--tokens`, `--tokens-session`, `--tokens-clear`)
- Initializes `FileStore`, `Vault`, `TokenTracker`
- Creates `QApplication` with global dark theme (`APP_STYLE`)
- Launches `MainWindow`

### `src/core/` — Domain Models & Business Logic

| File | Responsibility |
|------|---------------|
| `models.py` | Dataclasses: `AgentConfig`, `LLMConfig`, `SessionMeta`, `Message`; YAML dict converters |
| `agent.py` | `Agent` class — `load()` from YAML, `chat()` / `chat_stream()` via `LLMAdapter` |
| `session.py` | `Session` class — `create()`, `load()`, message persistence, context compression |
| `team.py` | `AgentTeam` stub (Phase 2) |
| `skill.py` | `Skill` stub (Phase 2) |
| `token_tracker.py` | `TokenTracker` — JSONL-based usage logging, cost estimation, per-session/per-model stats |

**Data flow during a chat message:**

```
User types message in SessionPanel
  → Session.add_message("user", content)       [persists to content.txt]
  → Session.build_context_messages()           [assembles system prompt + recent messages]
  → Agent.chat_stream(messages, session_id)    [delegates to LLMAdapter]
  → LLMAdapter.chat_stream() → AsyncGenerator[str]
  → SessionPanel._on_chunk(chunk)             [streams to ChatBubbleWidget]
  → Session.add_message("assistant", reply)    [persists full reply]
  → Session.save()
```

### `src/llm/` — LLM Adapter Abstraction

```
LLMAdapter (ABC)
├── chat() → LLMResponse
├── chat_stream() → AsyncGenerator[str]
└── last_usage: dict

MockAdapter          — echoes last user message (no API key needed)
OpenAICompatAdapter  — httpx-based SSE streaming, OpenAI-compatible API
```

`LLMAdapterFactory.create(config, api_key)` routes by provider string:
- `"openai" | "openai_compat" | "custom"` → `OpenAICompatAdapter` (with key) or `MockAdapter` (no key)
- `"mock"` → `MockAdapter`

### `src/storage/` — Persistence

**On-disk layout:**

```
Acts/
├── Agents/
│   └── {agent_id}/
│       └── AGENT.yaml
├── Sessions/
│   └── {session_id}/
│       ├── SESSION.yaml
│       └── content/
│           └── content.txt        ← [timestamp] [role] <json-encoded-content>
├── Team/
│   └── {team_id}.yaml
├── .vault.enc                     ← AES-256-GCM encrypted API keys
└── index.db                       ← SQLite supplementary index (future)
```

**Design decisions:**
- **YAML-first**: Agents, Sessions, Teams are YAML files. SQLite is supplementary.
- **Session messages**: Line-by-line format: `[timestamp] [role] <json>` in `content.txt`
- **Two content paths**: `content/content.txt` (new) and `content.txt` (legacy, root of session dir)

### `src/security/` — Encrypted Vault

`Vault` stores API keys encrypted with AES-256-GCM:

1. **Master key**: Retrieved from OS keyring (`keyring` library), falls back to local `.key` file
2. **Key references**: API keys in YAML stored as `vault:<alias>` strings
3. **Resolution**: `vault.resolve_key_ref("vault:openai")` → actual key

### `src/ui/` — PyQt6 Desktop GUI

```
MainWindow
├── Sidebar (QListWidget tabs)
│   ├── Agents list
│   ├── Teams list
│   └── Sessions list
└── Content (QStackedWidget)
    ├── AgentPanel       — CRUD form (name, provider, model, API key, params)
    ├── TeamPanel        — placeholder (Phase 2)
    └── SessionPanel     — chat view + session management
        ├── ChatViewWidget (scrollable message list)
        │   └── ChatRowWidget → ChatBubbleWidget
        │       ├── Header: avatar + name + copy button
        │       └── Content: QWebEngineView or QTextBrowser
        ├── Input area (QPlainTextEdit + Send button)
        └── SessionCreateWidget (name, agent, context params)
```

**Chat rendering — two paths:**

| Path | Condition | Markdown | LaTeX | Code Highlight |
|------|-----------|----------|-------|----------------|
| WebEngine | `_HAS_WEBENGINE and _katex_available()` | Python `markdown` → HTML | KaTeX (client-side) | highlight.js |
| QTextBrowser | Fallback | Qt `setMarkdown()` | Delimiters preserved (not rendered) | None |

**Rendering pipeline (WebEngine):**

```
Raw markdown text
  → _markdown_to_html()
    • Stash math blocks ($, $$, \(, \[)
    • markdown.markdown() → HTML
    • Restore math blocks
  → JS setHtml(html)
    • content.innerHTML = html
    • hljs.highlightAll()
    • renderMathInElement()
  → Rendered output
```

### `src/utils/` — Utilities

| File | Purpose |
|------|---------|
| `id_gen.py` | `new_id()` — 8-char hex from `uuid4` |
| `logger.py` | `setup_logging()` — basic config with format |

## Threading Model

```
Main Thread (Qt event loop)
├── SessionPanel UI updates
├── ChatBubbleWidget rendering
└── Signal/slot connections

ChatWorker (QThread)
└── asyncio.run(_task())
    ├── Agent.chat_stream() → AsyncGenerator
    └── Emits: chunk_received, finished_reply, failed
```

The `ChatWorker` runs `asyncio.run()` on a separate `QThread` to avoid blocking the GUI during LLM API calls. Chunks are emitted via Qt signals and processed on the main thread.

## Dependencies

```
PyQt6, PyQt6-WebEngine  — Desktop GUI + web rendering
PyYAML                   — Config/message persistence
httpx                    — Async HTTP for OpenAI-compatible APIs
aiosqlite                — Async SQLite
cryptography             — AES-256-GCM for vault encryption
keyring                  — OS-level master key storage
markdown                 — Server-side Markdown → HTML
matplotlib               — (future: token usage charts)
pytest, pytest-asyncio   — Testing
```

## Test Structure

```
tests/
├── conftest.py           — Sets up sys.path for src/ imports
├── test_agent.py         — Agent.load() + MockAdapter chat
├── test_session.py       — Session create → save → load round-trip
├── test_storage.py       — FileStore structure + YAML round-trip
├── test_db.py            — SQLite schema init
├── test_parse_state_machine.py  — LaTeX StreamingBuffer + Markdown math stashing
└── test_latex_streaming_visual.py — Visual LaTeX rendering test
```
