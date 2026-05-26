# 005: Session Message Persistence Format

**Date:** 2025 (Phase 1 MVP)

**Status:** Accepted

## Context

Chat messages need to be persisted to disk so sessions survive app restarts. The format must support:
- Append-only writes during streaming (without rewriting the entire file)
- Text-based for human inspection
- Parseable for reload
- Preservation of special characters and Unicode

## Decision

Store messages as **line-delimited text** in `content.txt`:

```
[2025-06-01T12:00:00Z] [user] "hello"
[2025-06-01T12:00:05Z] [assistant] "Hi there!"
```

Each line: `[timestamp] [role] <json-encoded-content>`

JSON encoding (`json.dumps`) ensures newlines, quotes, and Unicode within message content don't break the line-based format.

## Format Details

**Write** (`render_content_lines`):
```python
for msg in messages:
    encoded = json.dumps(msg.content, ensure_ascii=True)
    lines.append(f"[{msg.timestamp}] [{msg.role}] {encoded}")
```

**Read** (`parse_content_lines`):
```python
prefix, content = line.split("] ", 1)
timestamp = prefix[1:]
role, body = content.split("] ", 1)
role = role.lstrip("[")
decoded = json.loads(body) if valid JSON else body
```

## Rationale

- **Append-friendly**: New messages add new lines; no file rewrite needed
- **Streaming-safe**: Each complete message is one line; partial writes don't corrupt existing data
- **Human-readable**: Timestamps and roles are visible at a glance
- **JSON-in-line**: Content can contain any character without breaking the format

## Legacy Support

Two content paths are supported:
- `content/content.txt` (current format)
- `content.txt` (legacy, at session root)

`Session.load()` checks the new path first, then the legacy path.

## Consequences

- Not suitable for binary content or attachments (not currently needed)
- Line-based parsing is O(n) but acceptable for typical session sizes
- `[` characters at the start of a message would break parsing — but roles are controlled (user/assistant/system)
