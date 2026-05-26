# 001: YAML-First Persistence

**Date:** 2025 (Phase 1 MVP)

**Status:** Accepted

## Context

The application needs to persist Agent configurations, Session metadata, and chat messages. Options considered:

1. SQLite as primary store
2. YAML files as primary store with SQLite as supplementary index

## Decision

**YAML-first**: All domain objects (Agents, Sessions, Teams) are stored as YAML files on disk. SQLite is used only as a supplementary index (schema defined in `db.py` but not yet wired into the main data flow).

## Rationale

- **Human-readable**: Users can inspect and edit Agent configs directly in a text editor
- **Git-friendly**: YAML files can be version-controlled, diffed, and shared
- **Simplicity**: No migrations, no ORM, no database setup
- **Portability**: Directory of files can be copied between machines
- **Debugging**: Easy to inspect state by reading files

## Consequences

- No transactional guarantees across multiple writes
- Listing requires directory scanning (`iterdir()`)
- Large numbers of sessions may become slow (mitigated by future SQLite index)
- Session messages stored in a custom line-based format (`content.txt`) rather than YAML to support append-only writes during streaming

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| SQLite primary | ACID, queries, indexing | Requires migrations, less transparent |
| JSON files | Parseable by many tools | Less human-friendly than YAML, no comments |
| Pure SQLite | Single file, fast queries | Opaque, harder to debug |
