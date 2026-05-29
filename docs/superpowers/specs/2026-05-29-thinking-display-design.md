# Thinking Display in Chat UI — Design Spec

Date: 2026-05-29
Status: Approved

## Overview

Display the LLM's reasoning/thinking process in the chat UI. Thinking content is shown above the output bubble with semi-transparent styling and collapsible sections.

## Requirements

| # | Requirement | Detail |
|---|---|---|
| R1 | Real-time streaming | Thinking text appears incrementally as the model generates it |
| R2 | Collapsible per step | Simple chat: one collapsible block per response. Agent engine: one block per step |
| R3 | Semi-transparent | 65% opacity, distinguishing thinking from main content |
| R4 | Placement | Above the assistant reply bubble, inside ChatBubbleWidget |
| R5 | Auto-collapse | Thinking auto-collapses when main content begins streaming |
| R6 | User-fold override | Once user manually folds a thinking block, it stays folded permanently |
| R7 | Historical default | Loaded history messages default to collapsed thinking |
| R8 | Persistence | Thinking saved to `content.txt` with `[thinking]` role |
| R9 | Path 1 first | Implement simple chat (ChatWorker) first; agent engine (EngineWorker) later |

## Architecture

### Data Flow

```
DeepSeek SSE delta
  ├── delta.reasoning_content  →  on_thought() callback  →  ChatWorker.thought_chunk signal
  └── delta.content            →  yield chunk             →  ChatWorker.chunk_received signal
                                                                     │
                                              ┌──────────────────────┘
                                              ▼
                                        SessionPanel
                                     ├── _on_thought_chunk()  →  ThinkingWidget.append()
                                     └── _on_chunk()          →  ChatBubbleWidget.append_chunk()
```

### Approach: Dual-Channel Callback (Approach A)

Add an optional `on_thought` callback parameter to `chat_stream()`, following the existing `on_chunk` pattern in `chat()`.

## Implementation Plan (Path 1: Simple Chat)

### 1. LLM Adapter Layer

#### 1a. `src/llm/base.py` — LLMAdapter ABC
- Add optional `on_thought: Callable[[str], None] | None = None` parameter to `chat_stream()`

#### 1b. `src/llm/deepseek.py` — DeepSeekAdapter
- In `chat_stream()`: capture `delta.get("reasoning_content", "")` from SSE
- Call `on_thought(reasoning_text)` when reasoning_content is non-empty
- Also update `_chat_streaming_with_tools()` similarly

#### 1c. `src/llm/mock.py` — MockAdapter
- Accept `on_thought` parameter (no-op, just for interface compatibility)

#### 1d. `src/llm/callback.py` — CallbackAdapter
- Accept `on_thought` parameter (no-op, for interface compatibility)

#### 1e. `src/core/agent.py` — Agent.chat_stream()
- Forward `on_thought` callback to `self.llm.chat_stream()`

### 2. Worker Layer

#### 2a. `src/ui/session_panel.py` — ChatWorker
- New signal: `thought_chunk = pyqtSignal(str)`
- In `_task()`: pass `on_thought=lambda t: self.thought_chunk.emit(t)` to `agent.chat_stream()`

### 3. UI Layer

#### 3a. `src/ui/chat_widget.py` — New ThinkingWidget class

A collapsible QFrame that:
- **Header**: 🧠 icon + "思考过程" label + elapsed time + collapse toggle button
- **Body**: QTextBrowser or QLabel showing thinking text at 65% opacity, italic
- **States**: streaming (auto-expanded with pulsing dots), complete (auto-collapsed when content arrives), user-folded (permanently collapsed)
- **Public API**:
  - `append_chunk(text)` — append streaming text
  - `finalize()` — mark complete
  - `set_collapsed(bool)` — programmatic collapse
  - `is_user_folded()` — check if user manually intervened

CSS styling:
- Background: `rgba(255, 255, 255, 0.04)` on a 1px `rgba(255, 255, 255, 0.08)` border
- Text: `#a0a0a0` at `opacity: 0.65`, `font-style: italic`, `font-size: 11.5px`
- Collapse button: `#858585` text, subtle border

#### 3b. `src/ui/chat_widget.py` — ChatBubbleWidget changes
- Add an optional `ThinkingWidget` owned by the bubble
- When `thinking` is set, insert it between header and content label in the layout
- When main content starts (first non-empty content), auto-collapse thinking

#### 3c. `src/ui/chat_widget.py` — ChatViewWidget changes
- `add_message()` accepts optional `thinking_widget: ThinkingWidget | None`
- Or: new method `set_thinking(bubble, thinking_widget)` to attach thinking to an existing bubble

### 4. Session Panel Layer

#### 4a. `src/ui/session_panel.py` — SessionPanel
- `_start_stream()`: connect `worker.thought_chunk` to `_on_thought_chunk`
- `_on_thought_chunk(chunk)`: if no thinking widget yet, create one and associate with `_stream_bubble`; append chunk
- `_on_chunk(chunk)`: when first content chunk arrives, call `thinking_widget.finalize()` (triggers auto-collapse)
- `_on_finished(reply)`: ensure thinking is finalized
- `_on_failed(message)`: if thinking widget exists, show error state

### 5. Persistence Layer

#### 5a. `src/core/session.py` — Session
- `add_message()`: accept optional `thinking: str | None` parameter
- When `thinking` is set, write a `[thinking]` line before the `[assistant]` line
- `parse_content_lines()`: parse `[thinking]` role lines, attach to the following message

#### 5b. `src/core/models.py` — Message
- Add optional `thinking: str | None = None` field

#### 5c. `src/ui/session_panel.py` — ChatWorker._task()
- Collect thinking text during streaming
- Pass `thinking=collected_thinking` to `session.add_message("assistant", reply, thinking=...)`

#### 5d. `src/ui/session_panel.py` — _render_session()
- When rendering historical messages, create ThinkingWidget for messages that have `thinking` field
- ThinkingWidget defaults to collapsed state when loading history

## Component States

```
                    ┌──────────────┐
                    │   No thinking │
                    └──────┬───────┘
                           │ first thought chunk arrives
                           ▼
                    ┌──────────────┐
            ┌──────│  Streaming   │
            │      │ (expanded,   │
            │      │  dots动画)    │
            │      └──────┬───────┘
            │             │
            │   ┌─────────┴─────────┐
            │   │                   │
            │   ▼                   ▼
            │ ┌──────────┐   ┌──────────────┐
            │ │ 完成      │   │ 用户手动折叠  │
            │ │ (自动折叠) │   │ (永久折叠)    │
            │ └────┬─────┘   └──────┬───────┘
            │      │                │
            │      ▼                │
            │ ┌──────────┐          │
            └─│ 用户展开  │          │
              │ (手动)    │          │
              └──────────┘          │
                    │               │
                    ▼               ▼
              ┌──────────────────────────┐
              │ 可自由切换展开/折叠        │
              └──────────────────────────┘
```

## Testing Plan

| Test | File | What |
|---|---|---|
| Unit: DeepSeek reasoning_content SSE parsing | `tests/test_llm.py` | Verify `on_thought` called with reasoning_content from mock SSE |
| Unit: ThinkingWidget states | `tests/test_chat_widget.py` | Verify collapse/expand, user-fold override |
| Unit: Session persistence | `tests/test_session.py` | Verify `[thinking]` role round-trip |
| Integration: ChatWorker signal flow | `tests/test_session_panel.py` | Verify thought_chunk signal emits correctly |
| Visual: Manual testing | Run app | Verify appearance, streaming, collapse behavior |

## Files Changed

| File | Change |
|---|---|
| `src/llm/base.py` | `chat_stream()` + `on_thought` param |
| `src/llm/deepseek.py` | Capture reasoning_content, call on_thought |
| `src/llm/mock.py` | Accept on_thought (no-op) |
| `src/llm/callback.py` | Accept on_thought (no-op) |
| `src/core/agent.py` | Forward on_thought to adapter |
| `src/core/models.py` | Message + thinking field |
| `src/core/session.py` | add_message thinking param, parse [thinking] lines |
| `src/ui/chat_widget.py` | New ThinkingWidget class, ChatBubbleWidget changes |
| `src/ui/session_panel.py` | ChatWorker thought_chunk signal, SessionPanel handlers |

## Future: Path 2 (Agent Engine)

The EngineWorker already has `thought_chunk`/`thought_done`/`step_end` signals. When implementing Path 2:

- Connect engine signals to ThinkingWidget creation/update
- Each step gets its own ThinkingWidget (collapsible independently)
- Tool calls and results shown alongside step thinking
- Reflection summaries shown as additional context

## References

- DeepSeek API thinking mode: https://api.deepseek.com — `reasoning_content` in SSE delta
- Visual mockups: `.superpowers/brainstorm/1780-1780059577/content/`
