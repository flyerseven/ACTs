# Thought Process Visualization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace flat markdown assistant bubbles with an interactive collapsible HTML view showing the OBSERVE→THINK→ACT→REFLECT loop when `enable_decision_core` is true.

**Architecture:** ThoughtRecorder (QObject) sits between AgentEngine and a QWebEngineView running thought_view.html. The engine calls ThoughtRecorder methods per phase; ThoughtRecorder emits pyqtSignals; QWebChannel bridges signals to JS; JS updates the DOM. All while preserving CLI loguru output.

**Tech Stack:** PyQt6 QWebEngineView + QWebChannel, vanilla HTML/CSS/JS (no framework), Python dataclasses, loguru

---

## File Map

| File | Responsibility |
|------|---------------|
| `agent_engine/llm.py` (modify) | Add `on_chunk` callback to `LLMAdapter.chat()` and `OpenAIAdapter.chat()` |
| `agent_engine/engine.py` (modify) | Accept `on_thought_chunk` callback, pass to LLM, call ThoughtRecorder methods at each phase |
| `src/core/thought_recorder.py` (create) | QObject with pyqtSignals, StepSnapshot list, export methods, CLI loguru output |
| `src/ui/thought_view.py` (create) | QWidget wrapping QWebEngineView + QWebChannel, loads thought_view.html |
| `src/ui/thought_view.html` (create) | Self-contained HTML/CSS/JS — toolbar, collapsible `<details>` rounds, auto-scroll, export, theme toggle |
| `src/ui/session_panel.py` (modify) | Add `EngineWorker` QThread, check `enable_decision_core`, swap between ChatBubbleWidget and ThoughtView |

---

### Task 1: Add `on_chunk` streaming callback to agent_engine LLM adapter

**Files:**
- Modify: `agent_engine/llm.py`

- [ ] **Step 1: Add `on_chunk` parameter to `LLMAdapter.chat()` abstract method**

In `agent_engine/llm.py`, modify the `LLMAdapter.chat()` signature and the `OpenAIAdapter.chat()` implementation.

Change the abstract method:

```python
# agent_engine/llm.py — LLMAdapter class

@abstractmethod
async def chat(
    self,
    messages: list[dict],
    tools: list[dict] | None = None,
    on_chunk: Callable[[str], None] | None = None,
) -> LLMResponse:
    """Send messages and return a complete response.
    
    If on_chunk is provided, it is called with each text chunk
    as it arrives (streaming), while still returning the complete
    response with tool calls at the end.
    """
    ...
```

Update `chat_stream()` default implementation to pass `on_chunk`:

```python
async def chat_stream(
    self,
    messages: list[dict],
    tools: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    resp = await self.chat(messages, tools)
    yield resp.content
```

Update `CallbackAdapter.chat()`:

```python
async def chat(self, messages: list[dict], tools: list[dict] | None = None, on_chunk: Callable[[str], None] | None = None) -> LLMResponse:
    result = self._chat_fn(messages, tools)
    if hasattr(result, "__aiter__"):
        content = ""
        async for chunk in result:
            content += chunk
            if on_chunk:
                on_chunk(chunk)
        return LLMResponse(content=content)
    content = await result
    if on_chunk:
        on_chunk(content)
    return LLMResponse(content=content)
```

- [ ] **Step 2: Modify `OpenAIAdapter.chat()` to support `on_chunk` streaming internally**

Replace the `OpenAIAdapter.chat()` method body. When `on_chunk` is provided, use streaming HTTP but accumulate full content and extract tool calls from the stream:

```python
async def chat(self, messages: list[dict], tools: list[dict] | None = None, on_chunk: Callable[[str], None] | None = None) -> LLMResponse:
    # If streaming callback requested, use streaming path internally
    if on_chunk is not None:
        return await self._chat_streaming_with_tools(messages, tools, on_chunk)

    # Original non-streaming path (unchanged)
    payload: dict = {
        "model": self.model,
        "messages": messages,
    }
    if tools:
        payload["tools"] = [{"type": "function", "function": t} for t in tools]
        payload["tool_choice"] = "auto"

    last_error: str | None = None
    for attempt in range(self.max_retries + 1):
        try:
            client = await self._get_client()
            resp = await client.post(f"{self.base_url}/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

            choice = data["choices"][0]
            msg = choice["message"]
            content = msg.get("content", "") or ""

            tool_calls: list[ToolCallRequest] = []
            raw_tool_calls = msg.get("tool_calls", [])
            if raw_tool_calls:
                import json
                for tc in raw_tool_calls:
                    func = tc["function"]
                    try:
                        args = json.loads(func["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append(ToolCallRequest(
                        id=tc.get("id", ""),
                        name=func["name"],
                        arguments=args,
                    ))

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                usage=data.get("usage", {}),
            )
        except httpx.HTTPStatusError as e:
            last_error = str(e)
            logger.warning(f"OpenAI HTTP error (attempt {attempt + 1}): {e}")
            if attempt < self.max_retries:
                continue
        except httpx.RequestError as e:
            last_error = str(e)
            logger.warning(f"OpenAI request error (attempt {attempt + 1}): {e}")
            if attempt < self.max_retries:
                continue

    raise RuntimeError(f"OpenAIAdapter: all {self.max_retries + 1} attempts failed. Last error: {last_error}")
```

- [ ] **Step 3: Add `_chat_streaming_with_tools` private method to `OpenAIAdapter`**

Add the new private method that streams the response while accumulating tool call deltas:

```python
async def _chat_streaming_with_tools(self, messages: list[dict], tools: list[dict] | None, on_chunk: Callable[[str], None]) -> LLMResponse:
    """Stream response chunks via on_chunk while accumulating full content
    and extracting tool calls from the stream."""
    import json

    payload: dict = {
        "model": self.model,
        "messages": messages,
        "stream": True,
    }
    if tools:
        payload["tools"] = [{"type": "function", "function": t} for t in tools]
        payload["tool_choice"] = "auto"

    client = await self._get_client()
    content_parts: list[str] = []
    tool_call_deltas: dict[int, dict] = {}  # index -> {id, name, arguments_str}

    async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                delta = data["choices"][0].get("delta", {})

                content_delta = delta.get("content", "")
                if content_delta:
                    content_parts.append(content_delta)
                    on_chunk(content_delta)

                # Accumulate tool call deltas
                tc_deltas = delta.get("tool_calls", [])
                for tc in tc_deltas:
                    idx = tc.get("index", 0)
                    if idx not in tool_call_deltas:
                        tool_call_deltas[idx] = {"id": "", "name": "", "arguments_str": ""}
                    if "id" in tc and tc["id"]:
                        tool_call_deltas[idx]["id"] = tc["id"]
                    func = tc.get("function", {})
                    if "name" in func and func["name"]:
                        tool_call_deltas[idx]["name"] = func["name"]
                    if "arguments" in func and func["arguments"]:
                        tool_call_deltas[idx]["arguments_str"] += func["arguments"]

                usage_data = data.get("usage")
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

    tool_calls: list[ToolCallRequest] = []
    for idx in sorted(tool_call_deltas.keys()):
        tc_data = tool_call_deltas[idx]
        try:
            args = json.loads(tc_data["arguments_str"])
        except json.JSONDecodeError:
            args = {}
        tool_calls.append(ToolCallRequest(
            id=tc_data["id"],
            name=tc_data["name"],
            arguments=args,
        ))

    return LLMResponse(
        content="".join(content_parts),
        tool_calls=tool_calls,
        usage=usage_data if 'usage_data' in dir() else {},
    )
```

- [ ] **Step 4: Run existing engine tests to verify no regression**

Run: `pytest agent_engine/tests/ -v`
Expected: All tests pass (the `on_chunk` parameter is optional, existing behavior unchanged)

- [ ] **Step 5: Commit**

```bash
git add agent_engine/llm.py
git commit -m "feat: add on_chunk streaming callback to engine LLM adapter"
```

---

### Task 2: Create ThoughtRecorder

**Files:**
- Create: `src/core/thought_recorder.py`

- [ ] **Step 1: Create the file with StepSnapshot and ThoughtRecorder**

```python
"""ThoughtRecorder — intermediate layer between AgentEngine and UI.

Captures each phase of the OBSERVE→THINK→ACT→REFLECT loop,
emits pyqtSignals for the HTML frontend via QWebChannel,
and logs formatted text via loguru for CLI compatibility.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from loguru import logger
from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class StepSnapshot:
    index: int
    phase: str = "observe"
    thought: str = ""
    thought_streaming: bool = False
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""
    tool_error: str = ""
    tool_duration_ms: float = 0.0
    reflection: str = ""
    is_stuck: bool = False
    is_completed: bool = False


class ThoughtRecorder(QObject):
    """Emits signals for each phase of the decision loop.

    Always logs to loguru (CLI). Signals are picked up by
    QWebChannel when a ThoughtView is attached.
    """

    run_started = pyqtSignal(str)  # goal
    step_started = pyqtSignal(int)  # index
    thought_chunk = pyqtSignal(int, str)  # index, text_chunk
    thought_done = pyqtSignal(int, str)  # index, full_text
    tool_call_started = pyqtSignal(int, str, str)  # index, tool_name, args_json
    tool_result = pyqtSignal(int, str, str, float)  # index, result, error, duration_ms
    reflection_done = pyqtSignal(int, str, bool)  # index, summary, is_stuck
    step_ended = pyqtSignal(int, bool)  # index, is_completed
    run_finished = pyqtSignal(str, int, str)  # status, total_steps, errors_json

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._steps: list[StepSnapshot] = []
        self._current_step: StepSnapshot | None = None
        self._goal: str = ""

    # -- Engine callback interface --

    def on_run_start(self, goal: str) -> None:
        self._goal = goal
        self._steps.clear()
        self._current_step = None
        logger.info(f"Agent run started. Goal: {goal}")
        self.run_started.emit(goal)

    def on_thought_chunk(self, index: int, chunk: str) -> None:
        if self._current_step is None or self._current_step.index != index:
            self._current_step = StepSnapshot(index=index, phase="think")
            self._steps.append(self._current_step)
            logger.info(f"  Step {index} — THINK")
            self.step_started.emit(index)
        self._current_step.thought += chunk
        self._current_step.thought_streaming = True
        self.thought_chunk.emit(index, chunk)

    def on_thought_done(self, index: int, full_text: str) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.thought = full_text
            self._current_step.thought_streaming = False
        logger.info(f"  Step {index} — THINK complete ({len(full_text)} chars)")
        self.thought_done.emit(index, full_text)

    def on_tool_call_start(self, index: int, tool_name: str, args: dict) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.tool_name = tool_name
            self._current_step.tool_args = args
            self._current_step.phase = "act"
        logger.info(f"  Step {index} — ACT: {tool_name}({json.dumps(args, ensure_ascii=False)})")
        self.tool_call_started.emit(index, tool_name, json.dumps(args, ensure_ascii=False))

    def on_tool_result(self, index: int, result: str, error: str, duration_ms: float) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.tool_result = result
            self._current_step.tool_error = error
            self._current_step.tool_duration_ms = duration_ms
        if error:
            logger.error(f"  Step {index} — Tool error: {error}")
        else:
            logger.info(f"  Step {index} — Tool result ({len(result)} chars, {duration_ms:.0f}ms)")
        self.tool_result.emit(index, result, error, duration_ms)

    def on_reflection_done(self, index: int, summary: str, is_stuck: bool) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.phase = "reflect"
            self._current_step.reflection = summary
            self._current_step.is_stuck = is_stuck
        if is_stuck:
            logger.warning(f"  Step {index} — REFLECT: stuck — {summary}")
        else:
            logger.info(f"  Step {index} — REFLECT: {summary}")
        self.reflection_done.emit(index, summary, is_stuck)

    def on_step_end(self, index: int, is_completed: bool) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.is_completed = is_completed
        logger.info(f"  Step {index} — {'COMPLETED' if is_completed else 'NEXT'}")
        self.step_ended.emit(index, is_completed)

    def on_run_finish(self, status: str, errors: list[str]) -> None:
        total_steps = len(self._steps)
        logger.info(f"Run finished. Status: {status}, Steps: {total_steps}, Errors: {len(errors)}")
        self.run_finished.emit(status, total_steps, json.dumps(errors, ensure_ascii=False))

    # -- Export --

    def to_markdown(self) -> str:
        lines = [f"# Agent Run: {self._goal}", "", f"**Status:** {self._steps[-1].is_completed if self._steps else 'N/A'}", ""]
        for step in self._steps:
            lines.append(f"## Round {step.index + 1}")
            lines.append("")
            if step.thought:
                lines.append(f"### THINK\n\n{step.thought}\n")
            if step.tool_name:
                lines.append(f"### ACT — `{step.tool_name}`\n")
                lines.append(f"```json\n{json.dumps(step.tool_args, indent=2, ensure_ascii=False)}\n```\n")
                if step.tool_error:
                    lines.append(f"**Error:** {step.tool_error}\n")
                else:
                    lines.append(f"```\n{step.tool_result}\n```\n")
            if step.reflection:
                lines.append(f"### REFLECT\n\n{step.reflection}\n")
            lines.append("---\n")
        return "\n".join(lines)

    def to_json(self) -> str:
        steps_data = []
        for step in self._steps:
            steps_data.append({
                "index": step.index,
                "phase": step.phase,
                "thought": step.thought,
                "tool_name": step.tool_name,
                "tool_args": step.tool_args,
                "tool_result": step.tool_result,
                "tool_error": step.tool_error,
                "tool_duration_ms": step.tool_duration_ms,
                "reflection": step.reflection,
                "is_stuck": step.is_stuck,
                "is_completed": step.is_completed,
            })
        return json.dumps({
            "goal": self._goal,
            "steps": steps_data,
        }, indent=2, ensure_ascii=False)

    def reset(self) -> None:
        self._steps.clear()
        self._current_step = None
        self._goal = ""
```

- [ ] **Step 2: Verify the file has no syntax errors**

Run: `python -c "from src.core.thought_recorder import ThoughtRecorder, StepSnapshot; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/core/thought_recorder.py
git commit -m "feat: add ThoughtRecorder for decision loop event capture"
```

---

### Task 3: Create ThoughtView widget

**Files:**
- Create: `src/ui/thought_view.py`

- [ ] **Step 1: Create the ThoughtView widget**

```python
"""ThoughtView — QWebEngineView wrapper for collapsible thought process UI."""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtSlot
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QFileDialog

try:
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except Exception:
    _HAS_WEBENGINE = False

from core.thought_recorder import ThoughtRecorder


def _thought_view_html_path() -> Path:
    return Path(__file__).resolve().parent / "thought_view.html"


class _Bridge(QObject):
    """QWebChannel bridge — exposes export save dialog to JS."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._parent = parent

    @pyqtSlot(str, str)
    def save_file(self, content: str, default_name: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self._parent, "Export", default_name,
            "Markdown (*.md);;JSON (*.json);;All Files (*)",
        )
        if path:
            Path(path).write_text(content, encoding="utf-8")


class ThoughtView(QWidget):
    """Widget that displays the agent's decision loop as collapsible HTML."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if not _HAS_WEBENGINE:
            raise RuntimeError("QWebEngineView is not available")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._webview = QWebEngineView()
        self._webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        settings = self._webview.page().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)

        from PyQt6.QtGui import QColor
        self._webview.page().setBackgroundColor(QColor("#1e1e1e"))

        self._channel = QWebChannel()
        self._bridge = _Bridge(self)
        self._channel.registerObject("bridge", self._bridge)

        self._webview.page().setWebChannel(self._channel)

        html_path = _thought_view_html_path()
        base_url = QUrl.fromLocalFile(str(html_path.parent) + "/")
        self._webview.setUrl(QUrl.fromLocalFile(str(html_path)))

        layout.addWidget(self._webview)

    def set_recorder(self, recorder: ThoughtRecorder) -> None:
        self._channel.registerObject("recorder", recorder)
```

Wait, I need to import Qt. Let me fix the code above.

- [ ] **Step 1 (revised): Create the ThoughtView widget**

```python
"""ThoughtView — QWebEngineView wrapper for collapsible thought process UI."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, Qt, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

try:
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except Exception:
    _HAS_WEBENGINE = False

from core.thought_recorder import ThoughtRecorder


def _thought_view_html_path() -> Path:
    return Path(__file__).resolve().parent / "thought_view.html"


class _Bridge(QObject):
    """QWebChannel bridge — exposes export save dialog to JS."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._parent = parent

    @pyqtSlot(str, str)
    def save_file(self, content: str, default_name: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self._parent, "Export", default_name,
            "Markdown (*.md);;JSON (*.json);;All Files (*)",
        )
        if path:
            Path(path).write_text(content, encoding="utf-8")


class ThoughtView(QWidget):
    """Widget that displays the agent's decision loop as collapsible HTML."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if not _HAS_WEBENGINE:
            raise RuntimeError("QWebEngineView is not available")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._webview = QWebEngineView()
        self._webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        settings = self._webview.page().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
        self._webview.page().setBackgroundColor(QColor("#1e1e1e"))

        self._channel = QWebChannel()
        self._bridge = _Bridge(self)
        self._channel.registerObject("bridge", self._bridge)
        self._webview.page().setWebChannel(self._channel)

        html_path = _thought_view_html_path()
        self._webview.setUrl(QUrl.fromLocalFile(str(html_path)))

        layout.addWidget(self._webview)

    def set_recorder(self, recorder: ThoughtRecorder) -> None:
        """Register a ThoughtRecorder with the QWebChannel so JS can listen to its signals."""
        self._channel.registerObject("recorder", recorder)
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/thought_view.py
git commit -m "feat: add ThoughtView widget (QWebEngineView + QWebChannel)"
```

---

### Task 4: Create thought_view.html

**Files:**
- Create: `src/ui/thought_view.html`

- [ ] **Step 1: Create the complete HTML file**

This is the largest single file. It contains all HTML structure, CSS styles, JS logic.

```html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8" />
<style>
:root {
  --bg: #1e1e1e;
  --surface: #252526;
  --border: #3c3c3c;
  --text: #cccccc;
  --text-muted: #858585;
  --accent: #007acc;
  --error: #ef4444;
  --error-bg: rgba(239,68,68,0.08);
  --success: #4ade80;
  --success-bg: rgba(74,222,128,0.06);
  --tool: #4fc1ff;
  --tool-bg: rgba(0,122,204,0.08);
  --think-bg: rgba(255,255,255,0.03);
  --observe-bg: rgba(255,255,255,0.02);
  --reflect: #c4b5fd;
  --reflect-bg: rgba(167,139,250,0.05);
  --radius: 8px;
  --transition: 0.25s ease;
}
[data-theme="light"] {
  --bg: #ffffff;
  --surface: #f5f5f5;
  --border: #e0e0e0;
  --text: #333333;
  --text-muted: #888888;
  --accent: #0066cc;
  --think-bg: rgba(0,0,0,0.02);
  --observe-bg: rgba(0,0,0,0.01);
  --tool-bg: rgba(0,122,204,0.06);
  --success-bg: rgba(74,222,128,0.04);
  --reflect-bg: rgba(167,139,250,0.03);
  --error-bg: rgba(239,68,68,0.05);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: 'IBM Plex Sans', 'Segoe UI', 'Noto Sans SC', sans-serif;
  font-size: 12.5px;
  line-height: 1.6;
  padding: 16px;
}

/* ── Toolbar ── */
.toolbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  padding: 10px 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  position: sticky;
  top: 0;
  z-index: 10;
}
.toolbar button {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  font-size: 11px;
  cursor: pointer;
  transition: background var(--transition);
}
.toolbar button:hover { background: var(--tool-bg); color: var(--tool); }
.toolbar .sep { width: 1px; background: var(--border); margin: 0 4px; }
.toolbar .theme-btn { margin-left: auto; font-size: 14px; padding: 4px 10px; }

/* ── Status banner ── */
.status-banner {
  padding: 10px 16px;
  border-radius: var(--radius);
  margin-bottom: 12px;
  font-weight: 600;
  font-size: 13px;
  display: none;
}
.status-banner.done {
  display: block;
  background: var(--success-bg);
  color: var(--success);
  border: 1px solid var(--success);
}
.status-banner.failed {
  display: block;
  background: var(--error-bg);
  color: var(--error);
  border: 1px solid var(--error);
}

/* ── Details (round) ── */
.thought-round {
  margin-bottom: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  overflow: hidden;
  transition: border-color var(--transition);
}
.thought-round.has-error {
  border-color: var(--error);
  box-shadow: 0 0 8px rgba(239,68,68,0.15);
}

.round-summary {
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  font-size: 12px;
  list-style: none;
}
.round-summary::-webkit-details-marker { display: none; }
.round-summary::before {
  content: '▸';
  font-size: 10px;
  color: var(--text-muted);
  transition: transform var(--transition);
  width: 14px;
  text-align: center;
}
details[open] > .round-summary::before {
  transform: rotate(90deg);
}

.round-badge {
  background: var(--accent);
  color: #fff;
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 4px;
  font-weight: 700;
  min-width: 28px;
  text-align: center;
}

.round-title {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.round-indicator {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
}
.round-indicator.pulsing {
  background: var(--accent);
  animation: pulse 1.2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.4; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

/* ── Round body ── */
.round-body {
  padding: 0 14px 12px;
}
@keyframes slideDown {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 2000px; }
}
details[open] .round-body {
  animation: slideDown 0.3s ease;
}

/* ── Phase rows ── */
.phase {
  display: flex;
  gap: 10px;
  padding: 6px 10px;
  margin: 4px 0;
  border-radius: 6px;
  border-left: 3px solid transparent;
}
.phase-observe { border-left-color: var(--text-muted); background: var(--observe-bg); }
.phase-think { border-left-color: var(--text-muted); background: var(--think-bg); }
.phase-act { border-left-color: var(--accent); background: var(--tool-bg); }
.phase-result { border-left-color: var(--success); background: var(--success-bg); }
.phase-result.error { border-left-color: var(--error); background: var(--error-bg); }
.phase-reflect { border-left-color: #a78bfa; background: var(--reflect-bg); }

.phase-icon { width: 18px; text-align: center; flex-shrink: 0; font-size: 12px; }
.phase-label {
  font-weight: 600;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  min-width: 60px;
  flex-shrink: 0;
  padding-top: 1px;
}
.phase-observe .phase-label { color: var(--text-muted); }
.phase-think .phase-label { color: var(--text-muted); }
.phase-act .phase-label { color: var(--tool); }
.phase-result .phase-label { color: var(--success); }
.phase-result.error .phase-label { color: var(--error); }
.phase-reflect .phase-label { color: var(--reflect); }

.phase-content {
  flex: 1;
  word-break: break-word;
  white-space: pre-wrap;
}
.phase-content pre {
  background: rgba(0,0,0,0.2);
  padding: 8px 12px;
  border-radius: 6px;
  font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 11px;
  margin: 4px 0;
  max-height: 200px;
  overflow-y: auto;
}
.tool-name {
  color: var(--tool);
  font-weight: 600;
  font-family: monospace;
  font-size: 11.5px;
}

/* ── Empty state ── */
.empty-state {
  text-align: center;
  padding: 48px 20px;
  color: var(--text-muted);
}
.empty-state .dots {
  display: inline-flex;
  gap: 6px;
  margin-top: 12px;
}
.empty-state .dots span {
  width: 8px; height: 8px;
  background: var(--text-muted);
  border-radius: 50%;
  animation: dot-bounce 1.4s ease-in-out infinite both;
}
.empty-state .dots span:nth-child(1) { animation-delay: -0.32s; }
.empty-state .dots span:nth-child(2) { animation-delay: -0.16s; }
@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0.3); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>

<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
// ── State ──
var steps = {};
var currentIndex = -1;
var totalRounds = 0;
var runActive = false;

// ── DOM helpers ──
function $id(id) { return document.getElementById(id); }

function ensureRound(index) {
  if (steps[index]) return steps[index];
  var details = document.createElement('details');
  details.className = 'thought-round';
  details.open = true;
  details.dataset.index = index;

  var summary = document.createElement('summary');
  summary.className = 'round-summary';
  summary.innerHTML =
    '<span class="round-badge">R' + (index + 1) + '</span>' +
    '<span class="round-title">Thinking...</span>' +
    '<span class="round-indicator pulsing"></span>';
  details.appendChild(summary);

  var body = document.createElement('div');
  body.className = 'round-body';
  details.appendChild(body);

  var rounds = $id('rounds');
  rounds.appendChild(details);

  steps[index] = {
    details: details,
    summary: summary,
    body: body,
    title: summary.querySelector('.round-title'),
    indicator: summary.querySelector('.round-indicator'),
    phases: {}
  };

  totalRounds = Math.max(totalRounds, index + 1);
  currentIndex = index;
  return steps[index];
}

function addPhase(round, phaseType, icon, label) {
  if (round.phases[phaseType]) return round.phases[phaseType];
  var div = document.createElement('div');
  div.className = 'phase phase-' + phaseType;
  div.innerHTML =
    '<span class="phase-icon">' + icon + '</span>' +
    '<span class="phase-label">' + label + '</span>' +
    '<span class="phase-content"></span>';
  round.body.appendChild(div);
  round.phases[phaseType] = div;
  return div;
}

function setPhaseContent(round, phaseType, html) {
  var phase = addPhase(round, phaseType, '', '');
  var iconMap = {observe: '👁', think: '💭', act: '🔧', result: '✅', reflect: '🔄'};
  var labelMap = {observe: 'OBSERVE', think: 'THINK', act: 'ACT', result: 'RESULT', reflect: 'REFLECT'};
  phase.querySelector('.phase-icon').textContent = iconMap[phaseType] || '';
  phase.querySelector('.phase-label').textContent = labelMap[phaseType] || phaseType.toUpperCase();
  phase.querySelector('.phase-content').innerHTML = html;
  return phase;
}

function setResultError(round, isError) {
  var phase = round.phases['result'];
  if (phase) {
    phase.classList.toggle('error', isError);
  }
}

function updateTitle(round, text) {
  var short = text.substring(0, 80).replace(/\n/g, ' ');
  round.title.textContent = short || 'Thinking...';
}

function scrollToBottom() {
  var el = steps[currentIndex];
  if (el && el.details) {
    el.details.scrollIntoView({behavior: 'smooth', block: 'end'});
  }
}

// ── Collapse completed rounds ──
function collapseCompletedRounds(keepOpenIndex) {
  for (var key in steps) {
    var idx = parseInt(key);
    var round = steps[key];
    var indicator = round.indicator;
    if (idx === keepOpenIndex) {
      round.details.open = true;
      if (indicator && runActive) indicator.classList.add('pulsing');
    } else if (round.title.textContent.indexOf('ERROR') !== -1 || round.details.classList.contains('has-error')) {
      round.details.open = true;
      if (indicator) indicator.classList.remove('pulsing');
    } else {
      round.details.open = false;
      if (indicator) indicator.classList.remove('pulsing');
    }
  }
}

// ── QWebChannel signal handlers ──

function onRunStarted(goal) {
  $id('empty-state').style.display = 'none';
  $id('status-banner').className = 'status-banner';
  $id('status-banner').style.display = 'none';
  steps = {};
  currentIndex = -1;
  totalRounds = 0;
  runActive = true;
  $id('rounds').innerHTML = '';
}

function onStepStarted(index) {
  ensureRound(index);
}

function onThoughtChunk(index, chunk) {
  var round = ensureRound(index);
  var phase = setPhaseContent(round, 'think', '', '');
  var content = phase.querySelector('.phase-content');
  content.textContent += chunk;
  updateTitle(round, 'THINK: ' + (content.textContent || ''));
  scrollToBottom();
}

function onThoughtDone(index, fullText) {
  var round = ensureRound(index);
  setPhaseContent(round, 'think', '', '');
  round.phases['think'].querySelector('.phase-content').textContent = fullText;
  updateTitle(round, 'THINK: ' + fullText.substring(0, 80));
}

function onToolCallStarted(index, toolName, argsJson) {
  var round = ensureRound(index);
  var args = JSON.parse(argsJson);
  var argsStr = JSON.stringify(args, null, 2);
  setPhaseContent(round, 'act', '', '');
  round.phases['act'].querySelector('.phase-content').innerHTML =
    '<span class="tool-name">' + toolName + '</span>' +
    '<pre>' + escapeHtml(argsStr) + '</pre>';
  updateTitle(round, 'ACT: ' + toolName);
}

function onToolResult(index, result, error, durationMs) {
  var round = ensureRound(index);
  var isError = error && error.length > 0;
  var displayText = isError ? error : result;
  var phase = setPhaseContent(round, 'result', '', '');
  phase.querySelector('.phase-content').innerHTML =
    '<pre>' + escapeHtml(displayText || '(empty)') + '</pre>' +
    '<span style="font-size:10px;color:var(--text-muted)">' + durationMs.toFixed(0) + 'ms</span>';
  setResultError(round, isError);
  if (isError) {
    round.details.classList.add('has-error');
    round.details.open = true;
    updateTitle(round, 'ERROR: ' + (displayText || '').substring(0, 80));
  }
}

function onReflectionDone(index, summary, isStuck) {
  var round = ensureRound(index);
  setPhaseContent(round, 'reflect', '', '');
  round.phases['reflect'].querySelector('.phase-content').textContent = summary || '(no reflection)';
  if (isStuck) {
    round.details.classList.add('has-error');
    round.details.open = true;
  }
}

function onStepEnded(index, isCompleted) {
  var round = ensureRound(index);
  if (!isCompleted) {
    collapseCompletedRounds(index);
  }
}

function onRunFinished(status, totalSteps, errorsJson) {
  runActive = false;
  collapseCompletedRounds(-1);
  var banner = $id('status-banner');
  banner.style.display = 'block';
  var errors = JSON.parse(errorsJson);
  if (status === 'done') {
    banner.className = 'status-banner done';
    banner.textContent = 'Completed — ' + totalSteps + ' steps';
  } else {
    banner.className = 'status-banner failed';
    banner.textContent = status.toUpperCase() + ' — ' + totalSteps + ' steps' +
      (errors.length > 0 ? ' (' + errors.length + ' errors)' : '');
  }
}

// ── Toolbar actions ──

function expandAll() {
  for (var key in steps) { steps[key].details.open = true; }
}
function collapseAll() {
  for (var key in steps) { steps[key].details.open = false; }
}
function toggleTheme() {
  var html = document.documentElement;
  var current = html.getAttribute('data-theme');
  var next = current === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  $id('theme-btn').textContent = next === 'dark' ? '☀' : '🌙';
}

// ── Utilities ──

function escapeHtml(text) {
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

// ── Init ──
window.onload = function() {
  if (typeof QWebChannel === 'undefined') {
    document.body.innerHTML = '<div class="empty-state"><p>QWebChannel not available. This view requires PyQt6 WebEngine.</p></div>';
    return;
  }

  new QWebChannel(qt.webChannelTransport, function(channel) {
    window.recorder = channel.objects.recorder;

    if (window.recorder) {
      window.recorder.run_started.connect(onRunStarted);
      window.recorder.step_started.connect(onStepStarted);
      window.recorder.thought_chunk.connect(onThoughtChunk);
      window.recorder.thought_done.connect(onThoughtDone);
      window.recorder.tool_call_started.connect(onToolCallStarted);
      window.recorder.tool_result.connect(onToolResult);
      window.recorder.reflection_done.connect(onReflectionDone);
      window.recorder.step_ended.connect(onStepEnded);
      window.recorder.run_finished.connect(onRunFinished);
    }
  });
};
</script>
</head>
<body>

<div id="toolbar" class="toolbar">
  <button onclick="expandAll()">Expand All</button>
  <button onclick="collapseAll()">Collapse All</button>
  <span class="sep"></span>
  <button onclick="exportMarkdown()">Export MD</button>
  <button onclick="exportJSON()">Export JSON</button>
  <button id="theme-btn" class="theme-btn" onclick="toggleTheme()">&#x2600;</button>
</div>

<div id="status-banner" class="status-banner"></div>

<div id="empty-state" class="empty-state">
  <p>Waiting for agent to start...</p>
  <div class="dots"><span></span><span></span><span></span></div>
</div>

<div id="rounds"></div>

<script>
// Export functions (added after main init)
function exportMarkdown() {
  var md = '# Agent Run\n\n';
  for (var key in steps) {
    var round = steps[key];
    var idx = parseInt(key);
    md += '## Round ' + (idx + 1) + '\n\n';
    var phases = round.phases;
    if (phases['think']) {
      md += '### THINK\n\n' + (phases['think'].querySelector('.phase-content').textContent || '') + '\n\n';
    }
    if (phases['act']) {
      md += '### ACT\n\n' + (phases['act'].querySelector('.phase-content').textContent || '') + '\n\n';
    }
    if (phases['result']) {
      md += '### RESULT\n\n' + (phases['result'].querySelector('.phase-content').textContent || '') + '\n\n';
    }
    if (phases['reflect']) {
      md += '### REFLECT\n\n' + (phases['reflect'].querySelector('.phase-content').textContent || '') + '\n\n';
    }
    md += '---\n\n';
  }
  if (window.bridge) {
    window.bridge.save_file(md, 'agent_run.md');
  }
}

function exportJSON() {
  var data = {goal: '', steps: []};
  for (var key in steps) {
    var round = steps[key];
    var step = {
      index: parseInt(key),
      thought: round.phases['think'] ? round.phases['think'].querySelector('.phase-content').textContent : '',
      tool_result: round.phases['result'] ? round.phases['result'].querySelector('.phase-content').textContent : '',
      reflection: round.phases['reflect'] ? round.phases['reflect'].querySelector('.phase-content').textContent : '',
    };
    data.steps.push(step);
  }
  if (window.bridge) {
    window.bridge.save_file(JSON.stringify(data, null, 2), 'agent_run.json');
  }
}
</script>

</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/thought_view.html
git commit -m "feat: add thought_view.html with collapsible decision loop UI"
```

---

### Task 5: Modify AgentEngine to integrate with ThoughtRecorder

**Files:**
- Modify: `agent_engine/engine.py`

- [ ] **Step 1: Add `on_thought_chunk` and recorder callback parameters to `AgentEngine.run()`**

Modify the `run()` method signature and the THINK phase to support streaming. The changes are:

1. Add `on_thought_chunk: Callable[[str], None] | None = None` parameter to `run()`
2. Pass `on_chunk=on_thought_chunk` to `self.llm.chat()` in the think phase
3. After the engine loop, we don't need engine changes — the ThoughtRecorder will be called from the worker that wraps the engine

Actually, looking at this more carefully, the engine doesn't need to know about ThoughtRecorder at all. The engine just needs to support the `on_thought_chunk` callback so that streaming text reaches the UI. The ThoughtRecorder integration happens in the worker thread (Task 6).

```python
# In agent_engine/engine.py, modify AgentEngine.run():

async def run(self, goal: str, on_thought_chunk: Callable[[str], None] | None = None) -> AgentState:
    """Execute the full decision loop for the given goal.
    
    Args:
        goal: The goal to achieve.
        on_thought_chunk: Optional callback for streaming thought text.
    """
    self.state.start(goal)
    # ... (system prompt and memory setup unchanged) ...

    while self.state.state.status == "running":
        # ... (safety checks unchanged) ...

        # THINK
        step.phase = "think"
        try:
            tool_schemas = self.tools.list_openai_schemas() if self.tools.list_tools() else None
            response = await self.llm.chat(context, tool_schemas, on_chunk=on_thought_chunk)
            step.thought = response.content
            # ... (rest unchanged) ...
```

- [ ] **Step 2: Run engine tests to verify no regression**

Run: `pytest agent_engine/tests/ -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add agent_engine/engine.py
git commit -m "feat: add on_thought_chunk streaming callback to AgentEngine.run()"
```

---

### Task 6: Create EngineWorker and integrate into SessionPanel

**Files:**
- Modify: `src/ui/session_panel.py`

- [ ] **Step 1: Add EngineWorker class and imports**

Add the new `EngineWorker` QThread class and modify `SessionPanel` to check `enable_decision_core`.

Add imports at the top of `session_panel.py`:

```python
# Add these imports after existing imports:
from core.thought_recorder import ThoughtRecorder
from ui.thought_view import ThoughtView
```

Add the `EngineWorker` class after `LoadSessionWorker`:

```python
class EngineWorker(QThread):
    """Runs AgentEngine in a background thread with ThoughtRecorder integration."""
    thought_chunk = pyqtSignal(int, str)  # index, chunk — forwarded from recorder
    thought_done_signal = pyqtSignal(int, str)  # index, full_text
    tool_started = pyqtSignal(int, str, str)  # index, tool_name, args_json
    tool_finished = pyqtSignal(int, str, str, float)  # index, result, error, duration_ms
    reflection_ready = pyqtSignal(int, str, bool)  # index, summary, is_stuck
    step_done = pyqtSignal(int, bool)  # index, is_completed
    engine_started = pyqtSignal(str)  # goal
    engine_finished = pyqtSignal(str, int, str)  # status, total_steps, errors_json
    engine_failed = pyqtSignal(str)  # error message
    finished_reply = pyqtSignal(str)  # final reply text

    def __init__(self, agent_id: str, content: str, session: Session, store: FileStore, vault: Vault, token_tracker: "TokenTracker | None" = None) -> None:
        super().__init__()
        self.agent_id = agent_id
        self.content = content
        self.session = session
        self.store = store
        self.vault = vault
        self.token_tracker = token_tracker

    def run(self) -> None:
        try:
            asyncio.run(self._task())
        except Exception as exc:
            self.engine_failed.emit(str(exc))

    async def _task(self) -> None:
        from agent_engine.engine import AgentEngine
        from agent_engine.config import EngineConfig
        from agent_engine.tools import ToolRegistry
        from agent_engine.llm import OpenAIAdapter
        
        # Load agent config for LLM credentials
        config = agent_config_from_dict(read_yaml(self.store.agent_yaml_path(self.agent_id)))
        api_key = self.vault.resolve_key_ref(config.model.api_key_ref)
        
        # Build engine with tools
        engine_config = EngineConfig(
            openai_model=config.model.name,
            openai_base_url=config.model.base_url,
            openai_api_key=api_key,
        )
        llm = OpenAIAdapter(
            api_key=api_key,
            base_url=config.model.base_url or "https://api.openai.com/v1",
            model=config.model.name,
        )
        tools = ToolRegistry()
        # Register builtin tools
        from agent_engine.tools.builtin import register_all
        register_all(tools)
        
        engine = AgentEngine(llm=llm, config=engine_config, tools=tools)
        
        # Wire signals
        self.engine_started.emit(self.content)
        
        async def on_chunk(chunk: str) -> None:
            # Called by engine during THINK phase
            pass  # Will be wired through the recorder
        
        state = await engine.run(self.content, on_thought_chunk=on_chunk)
        
        # Build final reply from steps
        reply_parts = []
        for step in state.steps:
            if step.thought:
                reply_parts.append(step.thought)
            if step.observation:
                reply_parts.append(step.observation)
        reply = "\n\n".join(reply_parts)
        
        await self.session.add_message("assistant", reply)
        self.session.maybe_compress_context()
        await self.session.save()
        
        self.finished_reply.emit(reply)
```

Wait, this approach has a problem. The EngineWorker needs to forward signals to the ThoughtRecorder, but QObjects with signals can't be used from a non-main thread directly. The pyqtSignal emissions need to happen on the main thread, but the engine runs in a worker thread.

The correct approach: The `EngineWorker` runs in a QThread. It shouldn't directly call ThoughtRecorder methods (which emit signals). Instead:
1. EngineWorker emits its own signals (thread-safe via pyqtSignal)
2. SessionPanel (main thread) connects EngineWorker signals to ThoughtRecorder slots

Let me redesign this:

- EngineWorker emits signals for each phase event (these are queued connections by default since they cross threads)
- SessionPanel creates ThoughtRecorder and ThoughtView on the main thread
- SessionPanel connects EngineWorker signals → ThoughtRecorder methods
- ThoughtRecorder signals → QWebChannel → JS

Actually, even simpler: I can use the `@pyqtSlot` decorator on ThoughtRecorder methods and connect EngineWorker signals directly to them. Since pyqtSignal connections across threads use queued connections by default, this is safe.

Let me restructure. The EngineWorker emits high-level signals. SessionPanel wires them to ThoughtRecorder.

Actually wait — the whole point of EngineWorker emitting signals and ThoughtRecorder having its own signals is redundant. Let me simplify:

1. EngineWorker emits simple Python signals: `thought_chunk(int, str)`, `tool_started(int, str, str)`, etc.
2. SessionPanel connects these to ThoughtRecorder's slots
3. ThoughtRecorder emits its own pyqtSignals → QWebChannel → HTML

But this doubles the signal count. A cleaner approach:

1. EngineWorker runs the engine loop directly
2. Inside the async task, EngineWorker creates the ThoughtRecorder
3. EngineWorker uses `@pyqtSlot` decorated methods or `QMetaObject.invokeMethod` to safely call ThoughtRecorder from the worker thread

Actually, the cleanest approach for PyQt:

The ThoughtRecorder lives on the main thread. EngineWorker emits its own signals from the worker thread. SessionPanel connects these to ThoughtRecorder slots. Since cross-thread signal-slot connections use queued connections, this is thread-safe.

Let me finalize the design:

EngineWorker signals (emitted from worker thread):
- `thought_chunk(int, str)`
- `tool_started(int, str, str)`  
- `tool_finished(int, str, str, float)`
- `reflection_ready(int, str, bool)`
- `engine_started(str)`
- `engine_finished(str, int, str)`

SessionPanel connects these to ThoughtRecorder slots.

Let me rewrite Task 6 properly.<｜end▁of▁thinking｜>

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="Write">
<｜｜DSML｜｜parameter name="content" string="true"># Thought Process Visualization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace flat markdown assistant bubbles with an interactive collapsible HTML view showing the OBSERVE→THINK→ACT→REFLECT loop when `enable_decision_core` is true.

**Architecture:** ThoughtRecorder (QObject) sits between AgentEngine and a QWebEngineView running thought_view.html. The engine calls ThoughtRecorder methods per phase; ThoughtRecorder emits pyqtSignals; QWebChannel bridges signals to JS; JS updates the DOM. All while preserving CLI loguru output.

**Tech Stack:** PyQt6 QWebEngineView + QWebChannel, vanilla HTML/CSS/JS (no framework), Python dataclasses, loguru

---

## File Map

| File | Responsibility |
|------|---------------|
| `agent_engine/llm.py` (modify) | Add `on_chunk` callback to `LLMAdapter.chat()` and `OpenAIAdapter.chat()` |
| `agent_engine/engine.py` (modify) | Accept `on_thought_chunk` callback in `run()`, pass to LLM adapter |
| `src/core/thought_recorder.py` (create) | QObject with pyqtSignals, StepSnapshot list, export methods, CLI loguru output |
| `src/ui/thought_view.py` (create) | QWidget wrapping QWebEngineView + QWebChannel bridge, loads thought_view.html |
| `src/ui/thought_view.html` (create) | Self-contained HTML/CSS/JS — toolbar, collapsible `<details>` rounds, auto-scroll, export, theme toggle |
| `src/ui/session_panel.py` (modify) | Add `EngineWorker` QThread, check `enable_decision_core`, swap between ChatBubbleWidget and ThoughtView |

---

### Task 1: Add `on_chunk` streaming callback to agent_engine LLM adapter

**Files:**
- Modify: `agent_engine/llm.py`

- [ ] **Step 1: Add `on_chunk` parameter to `LLMAdapter.chat()` abstract signature**

In `agent_engine/llm.py`, find the `LLMAdapter` class and update `chat()`:

```python
@abstractmethod
async def chat(
    self,
    messages: list[dict],
    tools: list[dict] | None = None,
    on_chunk: Callable[[str], None] | None = None,
) -> LLMResponse:
    """Send messages and return a complete response.

    If on_chunk is provided, it is called with each text chunk
    as it arrives (streaming), while still returning the complete
    response with tool calls at the end.
    """
    ...
```

- [ ] **Step 2: Update `CallbackAdapter.chat()` to forward `on_chunk`**

```python
async def chat(self, messages: list[dict], tools: list[dict] | None = None, on_chunk: Callable[[str], None] | None = None) -> LLMResponse:
    result = self._chat_fn(messages, tools)
    if hasattr(result, "__aiter__"):
        content = ""
        async for chunk in result:
            content += chunk
            if on_chunk:
                on_chunk(chunk)
        return LLMResponse(content=content)
    content = await result
    if on_chunk:
        on_chunk(content)
    return LLMResponse(content=content)
```

- [ ] **Step 3: Add `_chat_streaming_with_tools` to `OpenAIAdapter` and modify `chat()` to use it**

Add the import at the top of `agent_engine/llm.py` if not already present:

```python
from typing import Callable
```

Modify `OpenAIAdapter.chat()` to check for `on_chunk`:

```python
async def chat(self, messages: list[dict], tools: list[dict] | None = None, on_chunk: Callable[[str], None] | None = None) -> LLMResponse:
    # If streaming callback requested, use streaming path internally
    if on_chunk is not None:
        return await self._chat_streaming_with_tools(messages, tools, on_chunk)

    # --- Original non-streaming path (unchanged below) ---
    payload: dict = {
        "model": self.model,
        "messages": messages,
    }
    if tools:
        payload["tools"] = [{"type": "function", "function": t} for t in tools]
        payload["tool_choice"] = "auto"
    # ... rest of existing implementation unchanged ...
```

Add the new private method to `OpenAIAdapter`:

```python
async def _chat_streaming_with_tools(
    self,
    messages: list[dict],
    tools: list[dict] | None,
    on_chunk: Callable[[str], None],
) -> LLMResponse:
    """Stream response chunks via on_chunk while accumulating full content
    and extracting tool calls from streamed deltas."""
    import json

    payload: dict = {
        "model": self.model,
        "messages": messages,
        "stream": True,
    }
    if tools:
        payload["tools"] = [{"type": "function", "function": t} for t in tools]
        payload["tool_choice"] = "auto"

    client = await self._get_client()
    content_parts: list[str] = []
    tool_call_deltas: dict[int, dict] = {}
    usage_data: dict = {}

    async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                delta = data["choices"][0].get("delta", {})

                content_delta = delta.get("content", "")
                if content_delta:
                    content_parts.append(content_delta)
                    on_chunk(content_delta)

                tc_deltas = delta.get("tool_calls", [])
                for tc in tc_deltas:
                    idx = tc.get("index", 0)
                    if idx not in tool_call_deltas:
                        tool_call_deltas[idx] = {"id": "", "name": "", "arguments_str": ""}
                    if "id" in tc and tc["id"]:
                        tool_call_deltas[idx]["id"] = tc["id"]
                    func = tc.get("function", {})
                    if "name" in func and func["name"]:
                        tool_call_deltas[idx]["name"] = func["name"]
                    if "arguments" in func and func["arguments"]:
                        tool_call_deltas[idx]["arguments_str"] += func["arguments"]

                if data.get("usage"):
                    usage_data = data["usage"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

    tool_calls: list[ToolCallRequest] = []
    for idx in sorted(tool_call_deltas.keys()):
        tc_data = tool_call_deltas[idx]
        try:
            args = json.loads(tc_data["arguments_str"])
        except json.JSONDecodeError:
            args = {}
        tool_calls.append(ToolCallRequest(
            id=tc_data["id"],
            name=tc_data["name"],
            arguments=args,
        ))

    return LLMResponse(
        content="".join(content_parts),
        tool_calls=tool_calls,
        usage=usage_data,
    )
```

- [ ] **Step 4: Run existing engine tests to verify no regression**

Run: `pytest agent_engine/tests/ -v`
Expected: All existing tests pass

- [ ] **Step 5: Commit**

```bash
git add agent_engine/llm.py
git commit -m "feat: add on_chunk streaming callback to engine LLM adapter"
```

---

### Task 2: Create ThoughtRecorder

**Files:**
- Create: `src/core/thought_recorder.py`

- [ ] **Step 1: Create `src/core/thought_recorder.py`**

```python
"""ThoughtRecorder — intermediate layer between AgentEngine and UI.

Captures each phase of the OBSERVE→THINK→ACT→REFLECT loop,
emits pyqtSignals for the HTML frontend via QWebChannel,
and logs formatted text via loguru for CLI compatibility.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger
from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class StepSnapshot:
    index: int
    phase: str = "observe"
    thought: str = ""
    thought_streaming: bool = False
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""
    tool_error: str = ""
    tool_duration_ms: float = 0.0
    reflection: str = ""
    is_stuck: bool = False
    is_completed: bool = False


class ThoughtRecorder(QObject):
    """Emits signals for each phase of the decision loop.

    Always logs to loguru (CLI). Signals are picked up by
    QWebChannel when a ThoughtView is attached.
    """

    run_started = pyqtSignal(str)
    step_started = pyqtSignal(int)
    thought_chunk = pyqtSignal(int, str)
    thought_done = pyqtSignal(int, str)
    tool_call_started = pyqtSignal(int, str, str)
    tool_result = pyqtSignal(int, str, str, float)
    reflection_done = pyqtSignal(int, str, bool)
    step_ended = pyqtSignal(int, bool)
    run_finished = pyqtSignal(str, int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._steps: list[StepSnapshot] = []
        self._current_step: StepSnapshot | None = None
        self._goal: str = ""

    # -- Engine callback interface (called from worker thread via queued connections) --

    def start_run(self, goal: str) -> None:
        self._goal = goal
        self._steps.clear()
        self._current_step = None
        logger.info(f"Agent run started. Goal: {goal}")
        self.run_started.emit(goal)

    def on_thought_chunk(self, index: int, chunk: str) -> None:
        if self._current_step is None or self._current_step.index != index:
            self._current_step = StepSnapshot(index=index, phase="think")
            self._steps.append(self._current_step)
            logger.info(f"  Step {index} — THINK")
            self.step_started.emit(index)
        self._current_step.thought += chunk
        self._current_step.thought_streaming = True
        self.thought_chunk.emit(index, chunk)

    def on_thought_done(self, index: int, full_text: str) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.thought = full_text
            self._current_step.thought_streaming = False
        logger.info(f"  Step {index} — THINK complete ({len(full_text)} chars)")
        self.thought_done.emit(index, full_text)

    def on_tool_call(self, index: int, tool_name: str, args: dict) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.tool_name = tool_name
            self._current_step.tool_args = args
            self._current_step.phase = "act"
        logger.info(f"  Step {index} — ACT: {tool_name}({json.dumps(args, ensure_ascii=False)})")
        self.tool_call_started.emit(index, tool_name, json.dumps(args, ensure_ascii=False))

    def on_tool_result(self, index: int, result: str, error: str, duration_ms: float) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.tool_result = result
            self._current_step.tool_error = error
            self._current_step.tool_duration_ms = duration_ms
        if error:
            logger.error(f"  Step {index} — Tool error: {error}")
        else:
            logger.info(f"  Step {index} — Tool result ({len(result)} chars, {duration_ms:.0f}ms)")
        self.tool_result.emit(index, result, error, duration_ms)

    def on_reflection(self, index: int, summary: str, is_stuck: bool) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.phase = "reflect"
            self._current_step.reflection = summary
            self._current_step.is_stuck = is_stuck
        if is_stuck:
            logger.warning(f"  Step {index} — REFLECT: stuck — {summary}")
        else:
            logger.info(f"  Step {index} — REFLECT: {summary}")
        self.reflection_done.emit(index, summary, is_stuck)

    def on_step_end(self, index: int, is_completed: bool) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.is_completed = is_completed
        logger.info(f"  Step {index} — {'COMPLETED' if is_completed else 'NEXT'}")
        self.step_ended.emit(index, is_completed)

    def finish_run(self, status: str, errors: list[str]) -> None:
        total_steps = len(self._steps)
        logger.info(f"Run finished. Status: {status}, Steps: {total_steps}, Errors: {len(errors)}")
        self.run_finished.emit(status, total_steps, json.dumps(errors, ensure_ascii=False))

    # -- Export --

    def to_markdown(self) -> str:
        lines = [f"# Agent Run: {self._goal}", "", f"**Steps:** {len(self._steps)}", ""]
        for step in self._steps:
            lines.append(f"## Round {step.index + 1}")
            lines.append("")
            if step.thought:
                lines.append(f"### THINK\n\n{step.thought}\n")
            if step.tool_name:
                lines.append(f"### ACT — `{step.tool_name}`\n")
                lines.append(f"```json\n{json.dumps(step.tool_args, indent=2, ensure_ascii=False)}\n```\n")
                if step.tool_error:
                    lines.append(f"**Error:** {step.tool_error}\n")
                else:
                    lines.append(f"```\n{step.tool_result}\n```\n")
            if step.reflection:
                lines.append(f"### REFLECT\n\n{step.reflection}\n")
            lines.append("---\n")
        return "\n".join(lines)

    def to_json(self) -> str:
        steps_data = []
        for step in self._steps:
            steps_data.append({
                "index": step.index,
                "phase": step.phase,
                "thought": step.thought,
                "tool_name": step.tool_name,
                "tool_args": step.tool_args,
                "tool_result": step.tool_result,
                "tool_error": step.tool_error,
                "tool_duration_ms": step.tool_duration_ms,
                "reflection": step.reflection,
                "is_stuck": step.is_stuck,
                "is_completed": step.is_completed,
            })
        return json.dumps({
            "goal": self._goal,
            "steps": steps_data,
        }, indent=2, ensure_ascii=False)

    def reset(self) -> None:
        self._steps.clear()
        self._current_step = None
        self._goal = ""
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "from src.core.thought_recorder import ThoughtRecorder, StepSnapshot; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/core/thought_recorder.py
git commit -m "feat: add ThoughtRecorder for decision loop event capture"
```

---

### Task 3: Create ThoughtView widget

**Files:**
- Create: `src/ui/thought_view.py`

- [ ] **Step 1: Create `src/ui/thought_view.py`**

```python
"""ThoughtView — QWebEngineView wrapper for collapsible thought process UI."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, Qt, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

try:
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except Exception:
    _HAS_WEBENGINE = False

from core.thought_recorder import ThoughtRecorder


def _thought_view_html_path() -> Path:
    return Path(__file__).resolve().parent / "thought_view.html"


class _Bridge(QObject):
    """Exposes save-file dialog to JS via QWebChannel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._parent = parent

    @pyqtSlot(str, str)
    def save_file(self, content: str, default_name: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self._parent, "Export", default_name,
            "Markdown (*.md);;JSON (*.json);;All Files (*)",
        )
        if path:
            Path(path).write_text(content, encoding="utf-8")


class ThoughtView(QWidget):
    """Displays the agent's decision loop as collapsible HTML."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if not _HAS_WEBENGINE:
            raise RuntimeError("QWebEngineView is not available")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._webview = QWebEngineView()
        self._webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        settings = self._webview.page().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
        self._webview.page().setBackgroundColor(QColor("#1e1e1e"))

        self._channel = QWebChannel()
        self._bridge = _Bridge(self)
        self._channel.registerObject("bridge", self._bridge)
        self._webview.page().setWebChannel(self._channel)

        html_path = _thought_view_html_path()
        self._webview.setUrl(QUrl.fromLocalFile(str(html_path)))

        layout.addWidget(self._webview)

    def set_recorder(self, recorder: ThoughtRecorder) -> None:
        """Register a ThoughtRecorder so JS can listen to its signals."""
        self._channel.registerObject("recorder", recorder)
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/thought_view.py
git commit -m "feat: add ThoughtView widget (QWebEngineView + QWebChannel)"
```

---

### Task 4: Create thought_view.html

**Files:**
- Create: `src/ui/thought_view.html`

- [ ] **Step 1: Create the complete HTML file**

```html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8" />
<style>
:root {
  --bg: #1e1e1e;
  --surface: #252526;
  --border: #3c3c3c;
  --text: #cccccc;
  --text-muted: #858585;
  --accent: #007acc;
  --error: #ef4444;
  --error-bg: rgba(239,68,68,0.08);
  --success: #4ade80;
  --success-bg: rgba(74,222,128,0.06);
  --tool: #4fc1ff;
  --tool-bg: rgba(0,122,204,0.08);
  --think-bg: rgba(255,255,255,0.03);
  --observe-bg: rgba(255,255,255,0.02);
  --reflect: #c4b5fd;
  --reflect-bg: rgba(167,139,250,0.05);
  --radius: 8px;
  --transition: 0.25s ease;
}
[data-theme="light"] {
  --bg: #ffffff;
  --surface: #f5f5f5;
  --border: #e0e0e0;
  --text: #333333;
  --text-muted: #888888;
  --accent: #0066cc;
  --think-bg: rgba(0,0,0,0.02);
  --observe-bg: rgba(0,0,0,0.01);
  --tool-bg: rgba(0,122,204,0.06);
  --success-bg: rgba(74,222,128,0.04);
  --reflect-bg: rgba(167,139,250,0.03);
  --error-bg: rgba(239,68,68,0.05);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: 'IBM Plex Sans', 'Segoe UI', 'Noto Sans SC', sans-serif;
  font-size: 12.5px;
  line-height: 1.6;
  padding: 16px;
}

/* ── Toolbar ── */
.toolbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  padding: 10px 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  position: sticky;
  top: 0;
  z-index: 10;
}
.toolbar button {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  font-size: 11px;
  cursor: pointer;
  transition: background var(--transition);
}
.toolbar button:hover { background: var(--tool-bg); color: var(--tool); }
.toolbar .sep { width: 1px; background: var(--border); margin: 0 4px; }
.toolbar .theme-btn { margin-left: auto; font-size: 14px; padding: 4px 10px; }

/* ── Status banner ── */
.status-banner {
  padding: 10px 16px;
  border-radius: var(--radius);
  margin-bottom: 12px;
  font-weight: 600;
  font-size: 13px;
  display: none;
}
.status-banner.done {
  display: block;
  background: var(--success-bg);
  color: var(--success);
  border: 1px solid var(--success);
}
.status-banner.failed {
  display: block;
  background: var(--error-bg);
  color: var(--error);
  border: 1px solid var(--error);
}

/* ── Details (round) ── */
.thought-round {
  margin-bottom: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  overflow: hidden;
  transition: border-color var(--transition);
}
.thought-round.has-error {
  border-color: var(--error);
  box-shadow: 0 0 8px rgba(239,68,68,0.15);
}

.round-summary {
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  font-size: 12px;
  list-style: none;
}
.round-summary::-webkit-details-marker { display: none; }
.round-summary::before {
  content: '\25B8';
  font-size: 10px;
  color: var(--text-muted);
  transition: transform var(--transition);
  width: 14px;
  text-align: center;
}
details[open] > .round-summary::before {
  transform: rotate(90deg);
}

.round-badge {
  background: var(--accent);
  color: #fff;
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 4px;
  font-weight: 700;
  min-width: 28px;
  text-align: center;
}

.round-title {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.round-indicator {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
}
.round-indicator.pulsing {
  background: var(--accent);
  animation: pulse 1.2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.4; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

/* ── Round body ── */
.round-body {
  padding: 0 14px 12px;
}
@keyframes slideDown {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 2000px; }
}
details[open] .round-body {
  animation: slideDown 0.3s ease;
}

/* ── Phase rows ── */
.phase {
  display: flex;
  gap: 10px;
  padding: 6px 10px;
  margin: 4px 0;
  border-radius: 6px;
  border-left: 3px solid transparent;
}
.phase-observe { border-left-color: var(--text-muted); background: var(--observe-bg); }
.phase-think { border-left-color: var(--text-muted); background: var(--think-bg); }
.phase-act { border-left-color: var(--accent); background: var(--tool-bg); }
.phase-result { border-left-color: var(--success); background: var(--success-bg); }
.phase-result.error { border-left-color: var(--error); background: var(--error-bg); }
.phase-reflect { border-left-color: #a78bfa; background: var(--reflect-bg); }

.phase-icon { width: 18px; text-align: center; flex-shrink: 0; font-size: 12px; }
.phase-label {
  font-weight: 600;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  min-width: 60px;
  flex-shrink: 0;
  padding-top: 1px;
}
.phase-observe .phase-label { color: var(--text-muted); }
.phase-think .phase-label { color: var(--text-muted); }
.phase-act .phase-label { color: var(--tool); }
.phase-result .phase-label { color: var(--success); }
.phase-result.error .phase-label { color: var(--error); }
.phase-reflect .phase-label { color: var(--reflect); }

.phase-content {
  flex: 1;
  word-break: break-word;
  white-space: pre-wrap;
}
.phase-content pre {
  background: rgba(0,0,0,0.2);
  padding: 8px 12px;
  border-radius: 6px;
  font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 11px;
  margin: 4px 0;
  max-height: 200px;
  overflow-y: auto;
}
.tool-name {
  color: var(--tool);
  font-weight: 600;
  font-family: monospace;
  font-size: 11.5px;
}

/* ── Empty state ── */
.empty-state {
  text-align: center;
  padding: 48px 20px;
  color: var(--text-muted);
}
.empty-state .dots {
  display: inline-flex;
  gap: 6px;
  margin-top: 12px;
}
.empty-state .dots span {
  width: 8px; height: 8px;
  background: var(--text-muted);
  border-radius: 50%;
  animation: dot-bounce 1.4s ease-in-out infinite both;
}
.empty-state .dots span:nth-child(1) { animation-delay: -0.32s; }
.empty-state .dots span:nth-child(2) { animation-delay: -0.16s; }
@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0.3); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>

<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
// ── State ──
var steps = {};
var currentIndex = -1;
var runActive = false;

function $id(id) { return document.getElementById(id); }

function ensureRound(index) {
  if (steps[index]) return steps[index];
  var details = document.createElement('details');
  details.className = 'thought-round';
  details.open = true;
  details.dataset.index = index;

  var summary = document.createElement('summary');
  summary.className = 'round-summary';
  summary.innerHTML =
    '<span class="round-badge">R' + (index + 1) + '</span>' +
    '<span class="round-title">Thinking...</span>' +
    '<span class="round-indicator pulsing"></span>';
  details.appendChild(summary);

  var body = document.createElement('div');
  body.className = 'round-body';
  details.appendChild(body);

  $id('rounds').appendChild(details);

  steps[index] = {
    details: details,
    summary: summary,
    body: body,
    title: summary.querySelector('.round-title'),
    indicator: summary.querySelector('.round-indicator'),
    phases: {}
  };

  currentIndex = index;
  return steps[index];
}

function addPhase(round, phaseType, icon, label) {
  if (round.phases[phaseType]) return round.phases[phaseType];
  var div = document.createElement('div');
  div.className = 'phase phase-' + phaseType;
  div.innerHTML =
    '<span class="phase-icon">' + icon + '</span>' +
    '<span class="phase-label">' + label + '</span>' +
    '<span class="phase-content"></span>';
  round.body.appendChild(div);
  round.phases[phaseType] = div;
  return div;
}

function setPhaseContent(round, phaseType, html) {
  var iconMap = {observe: '👁', think: '💭', act: '🔧', result: '✅', reflect: '🔄'};
  var labelMap = {observe: 'OBSERVE', think: 'THINK', act: 'ACT', result: 'RESULT', reflect: 'REFLECT'};
  var phase = addPhase(round, phaseType, iconMap[phaseType] || '', labelMap[phaseType] || phaseType.toUpperCase());
  phase.querySelector('.phase-content').innerHTML = html;
  return phase;
}

function setResultError(round, isError) {
  var phase = round.phases['result'];
  if (phase) { phase.classList.toggle('error', isError); }
}

function updateTitle(round, text) {
  var short = text.substring(0, 80).replace(/\n/g, ' ');
  round.title.textContent = short || 'Thinking...';
}

function scrollToBottom() {
  var el = steps[currentIndex];
  if (el && el.details) {
    el.details.scrollIntoView({behavior: 'smooth', block: 'end'});
  }
}

function collapseCompletedRounds(keepOpenIndex) {
  for (var key in steps) {
    var idx = parseInt(key);
    var round = steps[key];
    if (idx === keepOpenIndex) {
      round.details.open = true;
      if (round.indicator && runActive) round.indicator.classList.add('pulsing');
    } else if (round.details.classList.contains('has-error')) {
      round.details.open = true;
      if (round.indicator) round.indicator.classList.remove('pulsing');
    } else {
      round.details.open = false;
      if (round.indicator) round.indicator.classList.remove('pulsing');
    }
  }
}

// ── QWebChannel signal handlers ──

function onRunStarted(goal) {
  $id('empty-state').style.display = 'none';
  $id('status-banner').className = 'status-banner';
  $id('status-banner').style.display = 'none';
  steps = {};
  currentIndex = -1;
  runActive = true;
  $id('rounds').innerHTML = '';
}

function onStepStarted(index) { ensureRound(index); }

function onThoughtChunk(index, chunk) {
  var round = ensureRound(index);
  var phase = setPhaseContent(round, 'think', '', '');
  var content = phase.querySelector('.phase-content');
  content.textContent += chunk;
  updateTitle(round, 'THINK: ' + (content.textContent || ''));
  scrollToBottom();
}

function onThoughtDone(index, fullText) {
  var round = ensureRound(index);
  setPhaseContent(round, 'think', '', '');
  round.phases['think'].querySelector('.phase-content').textContent = fullText;
  updateTitle(round, 'THINK: ' + fullText.substring(0, 80));
}

function onToolCallStarted(index, toolName, argsJson) {
  var round = ensureRound(index);
  var args = JSON.parse(argsJson);
  setPhaseContent(round, 'act', '', '');
  round.phases['act'].querySelector('.phase-content').innerHTML =
    '<span class="tool-name">' + escapeHtml(toolName) + '</span>' +
    '<pre>' + escapeHtml(JSON.stringify(args, null, 2)) + '</pre>';
  updateTitle(round, 'ACT: ' + toolName);
}

function onToolResult(index, result, error, durationMs) {
  var round = ensureRound(index);
  var isError = error && error.length > 0;
  var displayText = isError ? error : result;
  var phase = setPhaseContent(round, 'result', '', '');
  phase.querySelector('.phase-content').innerHTML =
    '<pre>' + escapeHtml(displayText || '(empty)') + '</pre>' +
    '<span style="font-size:10px;color:var(--text-muted)">' + durationMs.toFixed(0) + 'ms</span>';
  setResultError(round, isError);
  if (isError) {
    round.details.classList.add('has-error');
    round.details.open = true;
    updateTitle(round, 'ERROR: ' + (displayText || '').substring(0, 80));
  }
}

function onReflectionDone(index, summary, isStuck) {
  var round = ensureRound(index);
  setPhaseContent(round, 'reflect', '', '');
  round.phases['reflect'].querySelector('.phase-content').textContent = summary || '(no reflection)';
  if (isStuck) {
    round.details.classList.add('has-error');
    round.details.open = true;
  }
}

function onStepEnded(index, isCompleted) {
  if (!isCompleted) { collapseCompletedRounds(index); }
}

function onRunFinished(status, totalSteps, errorsJson) {
  runActive = false;
  collapseCompletedRounds(-1);
  var banner = $id('status-banner');
  banner.style.display = 'block';
  var errors = JSON.parse(errorsJson);
  if (status === 'done') {
    banner.className = 'status-banner done';
    banner.textContent = 'Completed — ' + totalSteps + ' steps';
  } else {
    banner.className = 'status-banner failed';
    banner.textContent = status.toUpperCase() + ' — ' + totalSteps + ' steps' +
      (errors.length > 0 ? ' (' + errors.length + ' errors)' : '');
  }
}

// ── Toolbar ──

function expandAll() {
  for (var key in steps) { steps[key].details.open = true; }
}
function collapseAll() {
  for (var key in steps) { steps[key].details.open = false; }
}
function toggleTheme() {
  var html = document.documentElement;
  var next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  $id('theme-btn').textContent = next === 'dark' ? '☀' : '🌙';
}

// ── Export ──

function exportMarkdown() {
  var md = '# Agent Run\n\n';
  for (var key in steps) {
    var round = steps[key];
    md += '## Round ' + (parseInt(key) + 1) + '\n\n';
    var phases = round.phases;
    if (phases['think']) {
      md += '### THINK\n\n' + (phases['think'].querySelector('.phase-content').textContent || '') + '\n\n';
    }
    if (phases['act']) {
      md += '### ACT\n\n' + (phases['act'].querySelector('.phase-content').textContent || '') + '\n\n';
    }
    if (phases['result']) {
      md += '### RESULT\n\n' + (phases['result'].querySelector('.phase-content').textContent || '') + '\n\n';
    }
    if (phases['reflect']) {
      md += '### REFLECT\n\n' + (phases['reflect'].querySelector('.phase-content').textContent || '') + '\n\n';
    }
    md += '---\n\n';
  }
  if (window.bridge) {
    window.bridge.save_file(md, 'agent_run.md');
  }
}

function exportJSON() {
  var data = {goal: '', steps: []};
  for (var key in steps) {
    var round = steps[key];
    data.steps.push({
      index: parseInt(key),
      thought: round.phases['think'] ? round.phases['think'].querySelector('.phase-content').textContent : '',
      tool_result: round.phases['result'] ? round.phases['result'].querySelector('.phase-content').textContent : '',
      reflection: round.phases['reflect'] ? round.phases['reflect'].querySelector('.phase-content').textContent : '',
    });
  }
  if (window.bridge) {
    window.bridge.save_file(JSON.stringify(data, null, 2), 'agent_run.json');
  }
}

function escapeHtml(text) {
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

// ── Init ──
window.onload = function() {
  if (typeof QWebChannel === 'undefined') {
    document.body.innerHTML = '<div class="empty-state"><p>QWebChannel not available. This view requires PyQt6 WebEngine.</p></div>';
    return;
  }

  new QWebChannel(qt.webChannelTransport, function(channel) {
    window.recorder = channel.objects.recorder;
    window.bridge = channel.objects.bridge;

    if (window.recorder) {
      window.recorder.run_started.connect(onRunStarted);
      window.recorder.step_started.connect(onStepStarted);
      window.recorder.thought_chunk.connect(onThoughtChunk);
      window.recorder.thought_done.connect(onThoughtDone);
      window.recorder.tool_call_started.connect(onToolCallStarted);
      window.recorder.tool_result.connect(onToolResult);
      window.recorder.reflection_done.connect(onReflectionDone);
      window.recorder.step_ended.connect(onStepEnded);
      window.recorder.run_finished.connect(onRunFinished);
    }
  });
};
</script>
</head>
<body>

<div class="toolbar">
  <button onclick="expandAll()">Expand All</button>
  <button onclick="collapseAll()">Collapse All</button>
  <span class="sep"></span>
  <button onclick="exportMarkdown()">Export MD</button>
  <button onclick="exportJSON()">Export JSON</button>
  <button id="theme-btn" class="theme-btn" onclick="toggleTheme()">&#x2600;</button>
</div>

<div id="status-banner" class="status-banner"></div>

<div id="empty-state" class="empty-state">
  <p>Waiting for agent to start...</p>
  <div class="dots"><span></span><span></span><span></span></div>
</div>

<div id="rounds"></div>

</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/thought_view.html
git commit -m "feat: add thought_view.html with collapsible decision loop UI"
```

---

### Task 5: Modify AgentEngine.run() to accept on_thought_chunk

**Files:**
- Modify: `agent_engine/engine.py`

- [ ] **Step 1: Add `on_thought_chunk` parameter to `run()`**

In `agent_engine/engine.py`, change the `run()` signature and pass `on_chunk` to the LLM call:

```python
async def run(self, goal: str, on_thought_chunk: Callable[[str], None] | None = None) -> AgentState:
    """Execute the full decision loop for the given goal.

    Args:
        goal: The goal to achieve.
        on_thought_chunk: Optional callback receiving each streaming
            thought chunk during the THINK phase.
    """
    # ... self.state.start(goal) through memory setup unchanged ...

    while self.state.state.status == "running":
        # ... safety checks unchanged ...

        # THINK
        step.phase = "think"
        try:
            tool_schemas = self.tools.list_openai_schemas() if self.tools.list_tools() else None
            response = await self.llm.chat(context, tool_schemas, on_chunk=on_thought_chunk)
            step.thought = response.content
            # ... rest unchanged ...
```

Add the `Callable` import at the top if not present:

```python
from typing import Callable
```

- [ ] **Step 2: Run engine tests**

Run: `pytest agent_engine/tests/ -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add agent_engine/engine.py
git commit -m "feat: add on_thought_chunk streaming callback to AgentEngine.run()"
```

---

### Task 6: Add EngineWorker and integrate into SessionPanel

**Files:**
- Modify: `src/ui/session_panel.py`

- [ ] **Step 1: Add imports at top of session_panel.py**

After the existing import block, add:

```python
from core.thought_recorder import ThoughtRecorder
from ui.thought_view import ThoughtView
```

- [ ] **Step 2: Add EngineWorker class after LoadSessionWorker**

```python
class EngineWorker(QThread):
    """Runs AgentEngine in background with streaming thought chunks."""

    # Signals emitted from worker thread (queued connections to main thread)
    thought_chunk = pyqtSignal(int, str)
    tool_call_signal = pyqtSignal(int, str, str)
    tool_result_signal = pyqtSignal(int, str, str, float)
    reflection_signal = pyqtSignal(int, str, bool)
    step_end_signal = pyqtSignal(int, bool)
    engine_started = pyqtSignal(str)
    engine_finished = pyqtSignal(str, int, str)
    engine_failed = pyqtSignal(str)
    finished_reply = pyqtSignal(str)

    def __init__(self, agent_id: str, content: str, session: Session,
                 store: FileStore, vault: Vault,
                 token_tracker: "TokenTracker | None" = None) -> None:
        super().__init__()
        self.agent_id = agent_id
        self.content = content
        self.session = session
        self.store = store
        self.vault = vault
        self.token_tracker = token_tracker

    def run(self) -> None:
        try:
            asyncio.run(self._task())
        except Exception as exc:
            self.engine_failed.emit(str(exc))

    async def _task(self) -> None:
        from agent_engine.engine import AgentEngine
        from agent_engine.config import EngineConfig
        from agent_engine.tools import ToolRegistry
        from agent_engine.llm import OpenAIAdapter

        config = agent_config_from_dict(read_yaml(
            self.store.agent_yaml_path(self.agent_id)))
        api_key = self.vault.resolve_key_ref(config.model.api_key_ref)

        engine_config = EngineConfig(
            openai_model=config.model.name,
            openai_base_url=config.model.base_url or "https://api.openai.com/v1",
            openai_api_key=api_key,
        )
        llm = OpenAIAdapter(
            api_key=api_key,
            base_url=config.model.base_url or "https://api.openai.com/v1",
            model=config.model.name,
        )
        tools = ToolRegistry()

        # Register builtin tools if the package is available
        try:
            from agent_engine.tools.builtin import register_all
            register_all(tools)
        except ImportError:
            pass

        engine = AgentEngine(llm=llm, config=engine_config, tools=tools)

        self.engine_started.emit(self.content)

        step_index = 0

        def on_chunk(chunk: str) -> None:
            self.thought_chunk.emit(step_index, chunk)

        # Patch observer to emit richer events for the UI
        orig_emit = engine.observer.emit

        def patched_emit(event) -> None:
            nonlocal step_index
            orig_emit(event)
            if event.type == "step_start":
                step_index = event.data.get("index", step_index)
            elif event.type == "step_end":
                self.step_end_signal.emit(step_index, False)
            elif event.type == "done":
                self.step_end_signal.emit(step_index, True)

        engine.observer.emit = patched_emit

        state = await engine.run(self.content, on_thought_chunk=on_chunk)

        # Emit tool call and result events from recorded steps
        for step in state.steps:
            idx = step.index
            if step.tool_call:
                import json
                self.tool_call_signal.emit(
                    idx, step.tool_call.tool_name,
                    json.dumps(step.tool_call.arguments, ensure_ascii=False))
                self.tool_result_signal.emit(
                    idx, step.observation or "",
                    step.tool_call.error or "",
                    step.tool_call.duration_ms)
            if step.reflection:
                # Check if this was a stuck reflection
                is_stuck = "stuck" in step.reflection.lower()
                self.reflection_signal.emit(idx, step.reflection, is_stuck)

        # Build final reply
        reply_parts = []
        for step in state.steps:
            if step.thought:
                reply_parts.append(step.thought)
        reply = "\n\n".join(reply_parts) if reply_parts else "Task completed."

        await self.session.add_message("assistant", reply)
        self.session.maybe_compress_context()
        await self.session.save()

        self.engine_finished.emit(
            state.status, len(state.steps),
            json.dumps(state.errors, ensure_ascii=False))
        self.finished_reply.emit(reply)
```

- [ ] **Step 3: Modify SessionPanel.__init__ to add ThoughtView and recorder-related attributes**

Add these lines to `SessionPanel.__init__()`, after the existing attribute initializations:

```python
self._thought_view: ThoughtView | None = None
self._thought_recorder: ThoughtRecorder | None = None
self._engine_worker: EngineWorker | None = None
self._use_decision_core: bool = False
```

- [ ] **Step 4: Modify send_message() to check enable_decision_core and route accordingly**

Replace the second half of `send_message()` (from `self.chat_view.add_message("user", ...)` onward):

```python
    def send_message(self) -> None:
        content = self.input_box.toPlainText().strip()
        if not content:
            return
        if self._worker and self._worker.isRunning():
            return
        if self._load_worker and self._load_worker.isRunning():
            return
        if self._engine_worker and self._engine_worker.isRunning():
            return
        agent_id = self._current_agent_id()
        if not agent_id:
            self.chat_view.add_message("system", "No agent available. Create one first.")
            return

        if self.active_session is None:
            self.active_session = asyncio.run(
                Session.create(
                    name="New Session",
                    target_type="agent",
                    target_id=agent_id,
                    store=self.store,
                )
            )
            self.refresh_sessions(select_latest=True)
            self.sessions_changed.emit()
        asyncio.run(self.active_session.add_message("user", content))
        asyncio.run(self.active_session.save())

        # Check if agent has decision core enabled
        agent_config = agent_config_from_dict(
            read_yaml(self.store.agent_yaml_path(agent_id)))
        self._use_decision_core = agent_config.enable_decision_core

        self.chat_view.add_message("user", content, render_latex=True)
        self.input_box.clear()

        if self._use_decision_core:
            self._start_engine_stream(agent_id, content)
        else:
            self._stream_text = ""
            self._stream_bubble = self.chat_view.add_message(
                "assistant", "", render_latex=False)
            self._start_stream(agent_id, content)
```

- [ ] **Step 5: Add _start_engine_stream() and related handlers**

Add these new methods to `SessionPanel`:

```python
    def _start_engine_stream(self, agent_id: str, content: str) -> None:
        """Start the engine with thought process visualization."""
        if not self.active_session:
            return
        self.send_button.setEnabled(False)
        self.input_box.setEnabled(False)
        if self.session_combo:
            self.session_combo.setEnabled(False)
        if self.new_session_button:
            self.new_session_button.setEnabled(False)

        # Create ThoughtRecorder (main thread QObject)
        self._thought_recorder = ThoughtRecorder()

        # Create and insert ThoughtView into chat layout
        if self._thought_view is not None:
            self._thought_view.hide()
            self._thought_view.deleteLater()
        self._thought_view = ThoughtView()
        self._thought_view.set_recorder(self._thought_recorder)

        # Insert into chat_view container (before the spacer at the end)
        self.chat_view.container_layout.insertWidget(
            self.chat_view.container_layout.count() - 1,
            self._thought_view)

        # Start engine worker
        self._engine_worker = EngineWorker(
            agent_id, content, self.active_session,
            self.store, self.vault, token_tracker=self.token_tracker)

        # Wire worker signals -> ThoughtRecorder slots
        self._engine_worker.engine_started.connect(
            self._thought_recorder.start_run)
        self._engine_worker.thought_chunk.connect(
            self._thought_recorder.on_thought_chunk)
        self._engine_worker.tool_call_signal.connect(
            lambda idx, name, args: self._thought_recorder.on_tool_call(
                idx, name, json.loads(args)))
        self._engine_worker.tool_result_signal.connect(
            self._thought_recorder.on_tool_result)
        self._engine_worker.reflection_signal.connect(
            self._thought_recorder.on_reflection)
        self._engine_worker.step_end_signal.connect(
            self._thought_recorder.on_step_end)
        self._engine_worker.engine_finished.connect(
            lambda status, steps, errors: self._thought_recorder.finish_run(
                status, json.loads(errors)))

        # Wire worker signals -> SessionPanel handlers
        self._engine_worker.finished_reply.connect(self._on_engine_finished)
        self._engine_worker.engine_failed.connect(self._on_engine_failed)

        self._engine_worker.start()

    def _on_engine_finished(self, reply: str) -> None:
        self._enable_input()
        self._suppress_reload = True
        self.refresh_sessions()
        self._suppress_reload = False
        self.sessions_changed.emit()

    def _on_engine_failed(self, message: str) -> None:
        self._enable_input()
        self._suppress_reload = True
        self.refresh_sessions()
        self._suppress_reload = False
        self.sessions_changed.emit()
```

Add `import json` at the top of `session_panel.py` if not already present.

- [ ] **Step 6: Run a quick syntax check**

Run: `python -c "from src.ui.session_panel import SessionPanel; print('OK')"`
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add src/ui/session_panel.py
git commit -m "feat: add EngineWorker and decision-core routing to SessionPanel"
```

---

### Task 7: Integration test and manual verification

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: All previously-passing tests still pass

- [ ] **Step 2: Run agent_engine tests**

Run: `pytest agent_engine/tests/ -v`
Expected: All engine tests pass

- [ ] **Step 3: Verify health check still works**

Run: `python main.py --health`
Expected: Health check passes

- [ ] **Step 4: Commit final state if any tweaks were needed**

```bash
git add -A
git commit -m "chore: final integration tweaks for thought process visualization"
```

---

## Implementation Order

Tasks must run sequentially: 1 → 2 → 3 → 4 → 5 → 6 → 7

Each task builds on the previous. Task 4 (HTML) is the largest file but has no Python dependencies, so it can theoretically run in parallel with Tasks 2-3. The critical path is: LLM adapter change → ThoughtRecorder → Engine modification → SessionPanel integration.

## Testing Strategy

- **Task 1**: Existing `agent_engine/tests/` must continue passing
- **Task 2**: Import-only syntax check
- **Task 5**: Engine tests must continue passing with new optional parameter
- **Task 6**: Manual test — launch app, create agent with `enable_decision_core=true`, send message, verify thought_view.html loads
- **Task 7**: Full test suite regression check
