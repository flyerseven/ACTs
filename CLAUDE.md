# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

ACTs (Agent Creat Tools) is a desktop app for building, debugging, and orchestrating multi-Agent teams. Users bring their own LLM API keys, configure Agents locally, and chat with individual Agents or Agent teams through a PyQt6 GUI. Phase 1 MVP is complete; Phase 2 (Team orchestration) is next.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python main.py

# Health check (no GUI)
python main.py --health

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_agent.py -v

# Run a single test function
pytest tests/test_agent.py::test_agent_chat -v
```

## Architecture

```
main.py  (entry point — parses args, wires Store/Vault, launches MainWindow)
└── src/
    ├── core/        Domain models + business logic
    │   ├── models.py    Dataclasses: AgentConfig, LLMConfig, SessionMeta, Message (with YAML dict converters)
    │   ├── agent.py     Agent.load() + chat/chat_stream via LLMAdapter
    │   ├── session.py   Session.create/load, message persistence, context compression
    │   ├── team.py      AgentTeam stub (Phase 2)
    │   └── skill.py     Skill stub (Phase 2)
    ├── llm/         LLM adapter abstraction
    │   ├── base.py       LLMAdapter ABC + MockAdapter (echoes last user message)
    │   ├── openai_compat.py  OpenAICompatAdapter (httpx streaming SSE → AsyncGenerator[str])
    │   └── factory.py    LLMAdapterFactory.create() — routes by provider string
    ├── storage/     File-system persistence + optional SQLite index
    │   ├── file_store.py   Path layout: Acts/{Agents,Sessions,Team}/. Creates `.vault.enc` + `index.db` paths.
    │   ├── yaml_io.py      Thin wrappers around PyYAML (safe_load/safe_dump)
    │   └── db.py           aiosqlite schema + upsert helpers (async, for future indexing)
    ├── security/    Encrypted vault for API keys
    │   └── vault.py    AES-256-GCM encryption. Master key via keyring or local `.key` file. Resolves `vault:<alias>` refs.
    ├── ui/          PyQt6 desktop GUI (dark theme)
    │   ├── main_window.py         3-tab sidebar (Agents/Teams/Sessions) + stacked content area
    │   ├── agent_panel.py         Agent CRUD + LLM config form
    │   ├── session_panel.py       Session list, routing to session create / chat views
    │   ├── session_create_panel.py  Session creation form (system prompt, context params)
    │   ├── chat_widget.py         Chat bubbles with Markdown rendering via QWebEngineView, KaTeX math, highlight.js
    │   ├── styles.py              Global dark-theme QSS
    │   └── assets/                Bundled KaTeX + highlight.js for offline rendering
    └── utils/       Logging setup + 8-char hex ID generator
```

## Key design decisions

- **YAML-first persistence**: Agents, Sessions, Teams are all YAML files on disk. SQLite is supplementary indexing (not the source of truth).
- **LLM adapter pattern**: `LLMAdapter` ABC with `chat()` and `chat_stream()` → `AsyncGenerator[str]`. Factory routes by provider string. Falls back to `MockAdapter` if no API key is set.
- **Vault key references**: API keys in YAML are stored as `vault:<alias>` strings, resolved at load time via `Vault.resolve_key_ref()`. The vault is AES-256-GCM encrypted with a master key stored in the OS keyring (fallback: local `.key` file).
- **Session persistence format**: Messages stored line-by-line as `[timestamp] [role] <json-encoded-content>` in `content.txt`. Parsed via `parse_content_lines()`.
- **Context compression**: Sessions support automatic context summarization every N assistant turns (configured per session). Uncompressed messages are summarized and appended as a system message.
- **GUI rendering**: Chat uses `QWebEngineView` for Markdown + KaTeX math rendering. The chat widget has a separate `_use_web` path (WebEngine) vs fallback `QTextBrowser` path.
