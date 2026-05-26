# ACTs Documentation

## Getting Started

- [README](../README.md) — Quick start, health check, data directory
- [CLAUDE.md](../CLAUDE.md) — Claude Code guidance and project overview

## Architecture

- [architecture.md](architecture.md) — Full system architecture, layer descriptions, data flow

## Decision Records

Key architectural decisions with context, rationale, and consequences:

| # | Decision | Summary |
|---|----------|---------|
| 001 | [YAML-First Persistence](decisions/001-yaml-first-persistence.md) | Configs and metadata as YAML files; SQLite supplementary |
| 002 | [LLM Adapter Pattern](decisions/002-llm-adapter-pattern.md) | Abstract adapter + factory for multi-provider support |
| 003 | [Vault API Key Management](decisions/003-vault-api-key-management.md) | AES-256-GCM encrypted keys with `vault:<alias>` references |
| 004 | [WebEngine + KaTeX Rendering](decisions/004-webengine-katex-chat-rendering.md) | Python markdown → HTML, client-side KaTeX math, QTextBrowser fallback |
| 005 | [Session Message Format](decisions/005-session-message-format.md) | Line-based `[timestamp] [role] <json>` for append-only writes |
| 006 | [Context Compression](decisions/006-context-compression.md) | Configurable per-session summarization strategy |
| 007 | [Threading Model](decisions/007-threading-model.md) | QThread + asyncio hybrid for non-blocking LLM calls |

## Directory Structure

```
ACTs/
├── main.py                    # Entry point
├── requirements.txt           # Dependencies
├── CLAUDE.md                  # Claude Code guidance
├── docs/                      # Architecture documentation (this directory)
│   ├── index.md
│   ├── architecture.md
│   └── decisions/
├── src/
│   ├── core/                  # Domain models + business logic
│   ├── llm/                   # LLM adapter abstraction
│   ├── storage/               # File-system persistence
│   ├── security/              # Encrypted vault
│   ├── ui/                    # PyQt6 GUI
│   │   └── assets/            # Bundled KaTeX + highlight.js
│   └── utils/                 # ID generation, logging
├── tests/                     # pytest test suite
├── Acts/                      # Runtime data (created at first run)
│   ├── Agents/
│   ├── Sessions/
│   └── Team/
└── scripts/                   # Asset fetching utilities
```

## Key Concepts

### Agent
A configured LLM endpoint. Has a name, system prompt, model config (provider, model name, temperature, max_tokens), and API key reference. Stored as `Acts/Agents/{id}/AGENT.yaml`.

### Session
A conversation with an Agent. Has metadata (name, target agent, system prompt override), a list of Messages, and context compression settings. Stored as `Acts/Sessions/{id}/SESSION.yaml` + `content/content.txt`.

### Message
A single turn in a conversation: role (`user`, `assistant`, `system`), content (string), timestamp. Persisted as a line in `content.txt`.

### Vault
Encrypted store for API keys. Keys are referenced in configs as `vault:<alias>`. Master key stored in OS keyring.

### LLM Adapter
Abstract interface for LLM API calls. Implementations: `MockAdapter` (echo), `OpenAICompatAdapter` (OpenAI-compatible SSE streaming).

## Phase Roadmap

### Phase 1 (Complete)
- [x] Single-Agent configuration (CRUD via UI)
- [x] Single-Agent chat with streaming
- [x] Session persistence (save/load conversations)
- [x] Encrypted API key vault
- [x] Markdown + LaTeX rendering
- [x] Token usage tracking
- [x] Context compression (simple truncation)

### Phase 2 (Planned)
- [ ] Agent Team orchestration
- [ ] Multi-Agent chat routing
- [ ] LLM-based context summarization
- [ ] Tool/function calling
- [ ] Skill system
- [ ] Anthropic adapter
- [ ] Local model support (Ollama)
