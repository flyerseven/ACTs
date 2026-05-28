# Thought Process Visualization — Design Spec

**Date**: 2026-05-28
**Status**: Approved
**Scope**: Replace flat markdown assistant bubbles with an interactive collapsible HTML view when the agent's Decision Core is enabled.

## 1. Summary

When an agent is configured with `enable_decision_core: true`, the assistant response area in the chat UI is replaced by a dedicated QWebEngineView running a self-contained HTML page (`thought_view.html`). This page visualizes each iteration of the OBSERVE→THINK→ACT→REFLECT loop as a collapsible `<details>` element with color-coded phases, real-time streaming text, error highlighting, and export capabilities.

When `enable_decision_core` is false, the existing flat ChatBubbleWidget markdown rendering is used unchanged.

## 2. Architecture

```
AgentEngine.run()
  │  callback per phase
  ▼
ThoughtRecorder (QObject, Python)
  │  pyqtSignal emitted
  ▼
QWebChannel → thought_view.html (JS)
  │  DOM update
  ▼
User sees collapsible thought process
```

`ThoughtRecorder` is a new intermediate layer between the AgentEngine and the UI. It:
- Receives structured phase data from the engine
- Emits signals for the HTML frontend via QWebChannel
- Logs formatted text via loguru for CLI compatibility
- Maintains full step history for export

## 3. Data Model

### ThoughtRecorder signals (QWebChannel → JS)

| Signal | Payload | When |
|--------|---------|------|
| `run_started` | `{goal}` | New run begins |
| `step_started` | `{index}` | New step begins |
| `thought_chunk` | `{index, text_chunk}` | Streaming thought text |
| `thought_done` | `{index, full_text}` | THINK phase complete |
| `tool_call_started` | `{index, tool_name, args}` | Tool invocation begins |
| `tool_result` | `{index, result, error, duration_ms}` | Tool returns |
| `reflection_done` | `{index, summary, is_stuck}` | REFLECT phase complete |
| `step_ended` | `{index, is_completed}` | Step fully done |
| `run_finished` | `{status, total_steps, errors}` | Goal achieved or failed |

### StepSnapshot (Python internal)

```python
@dataclass
class StepSnapshot:
    index: int
    phase: str
    thought: str = ""
    thought_streaming: bool = False
    tool_name: str = ""
    tool_args: dict = {}
    tool_result: str = ""
    tool_error: str = ""
    tool_duration_ms: float = 0.0
    reflection: str = ""
    is_stuck: bool = False
    is_completed: bool = False
```

## 4. HTML Structure

Each decision round is a `<details>` element:

```html
<details class="thought-round" data-index="0" open>
  <summary class="round-summary">
    <span class="round-badge">R1</span>
    <span class="round-title">THINK: Analyzing the codebase...</span>
    <span class="round-indicator pulsing"></span>
  </summary>
  <div class="round-body">
    <div class="phase phase-observe">...</div>
    <div class="phase phase-think">...</div>
    <div class="phase phase-act">...</div>
    <div class="phase phase-reflect">...</div>
  </div>
</details>
```

Toolbar at top: Expand All / Collapse All / Export Markdown / Export JSON / Theme toggle.

## 5. CSS Color Scheme

| Phase | Border-left | Background | Text |
|-------|------------|------------|------|
| OBSERVE | `#6a6a6a` | `rgba(255,255,255,0.02)` | `#858585` |
| THINK | `#6a6a6a` | `rgba(255,255,255,0.03)` | `#cccccc` |
| ACT (tool) | `#007acc` | `rgba(0,122,204,0.08)` | `#4fc1ff` |
| ACT (result) | `#4ade80` | `rgba(74,222,128,0.06)` | `#86efac` |
| REFLECT | `#a78bfa` | `rgba(167,139,250,0.05)` | `#c4b5fd` |
| Error | `#ef4444` | `rgba(239,68,68,0.08)` | `#fca5a5` |

Dark/light themes via CSS custom properties on `:root`, toggled by JS class swap on `<html>`.

## 6. Interaction Behavior

- Active step: `<details open>`, summary shows pulsing indicator dot
- Step completes: `open` attribute removed (auto-collapse), unless it's the most recent completed step
- Error step: force `open`, add `.has-error` class with red left border glow
- Run finishes: collapse all steps, show final status banner
- Smooth open/close animation via CSS `@keyframes`
- Auto-scroll to active step via `scrollIntoView({behavior: 'smooth'})`
- Click any collapsed round to expand and inspect

## 7. Export

Two JS functions read DOM state and produce structured output:

- **Export Markdown**: Generates `## Round N` sections with phase content, tool calls as code blocks
- **Export JSON**: Serializes all step data to JSON, triggers file download via Python `QFileDialog`

## 8. File Changes

### New files

| File | Purpose |
|------|---------|
| `src/core/thought_recorder.py` | ThoughtRecorder QObject with pyqtSignals, StepSnapshot, export methods |
| `src/ui/thought_view.py` | ThoughtView QWidget wrapping QWebEngineView + QWebChannel setup |
| `src/ui/thought_view.html` | Self-contained HTML/CSS/JS for the collapsible thought UI (~300-400 lines) |

### Modified files

| File | Change |
|------|--------|
| `agent_engine/engine.py` | Accept optional ThoughtRecorder callback, call phase methods during loop |
| `src/ui/session_panel.py` | Check `enable_decision_core`, instantiate ThoughtView + ThoughtRecorder when enabled, fall back to ChatBubbleWidget otherwise |

## 9. CLI Compatibility

ThoughtRecorder always calls `logger.info()` with formatted phase text regardless of whether the HTML view is active. The existing CLI output is preserved unchanged.

## 10. Non-Goals

- Does NOT modify the AgentEngine decision loop logic
- Does NOT change how user messages are rendered
- Does NOT affect sessions without decision_core enabled
- Does NOT add new dependencies (QWebChannel and QWebEngineView are already in the PyQt6 dependency tree)
