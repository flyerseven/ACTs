# 006: Context Compression Strategy

**Date:** 2025 (Phase 1 MVP)

**Status:** Accepted

## Context

LLM APIs have context window limits and per-token pricing. Long conversations accumulate messages that may exceed context limits or become expensive. The app needs a strategy to manage context length.

## Decision

Implement **configurable automatic summarization** at the Session level:

1. `compression_interval`: Summarize every N assistant turns (0 = disabled)
2. `context_keep_last`: Number of recent messages to keep uncompressed
3. Summary stored in `SessionMeta.summary`
4. `last_compressed_turn`: Tracks how many messages have been compressed

## Algorithm

```
Session.maybe_compress_context():
  if compression_interval <= 0: return
  if current_turn_count % interval != 0: return
  if len(messages) <= context_keep_last: return

  chunk = messages[last_compressed_turn : len(messages) - context_keep_last]
  new_summary = summarize_messages(existing_summary, chunk)
  last_compressed_turn = len(messages) - context_keep_last
```

## Context Assembly

```python
Session.build_context_messages():
  messages = []
  if system_prompt: messages.append(system message)
  if summary_exists: messages.append("Summary of previous context: {summary}")
  messages += recent_messages[last_compressed_turn:][-context_keep_last:]
  return messages
```

## Summarization (Current)

`summarize_messages()` concatenates message contents and truncates to 2000 characters. This is a **placeholder** — true LLM-based summarization is planned for Phase 2.

## Consequences

- Compression runs after each streaming response completes (`_on_finished`)
- The summary is sent as a system message, placing it before recent context
- Truncation-based summarization loses detail but preserves the most recent ~2000 chars of context
- Phase 2 should replace `summarize_messages` with an LLM call for intelligent summarization
