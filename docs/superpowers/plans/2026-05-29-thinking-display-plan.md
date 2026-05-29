# Thinking Display in Chat UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display the LLM's reasoning/thinking process above chat bubbles with semi-transparent collapsible UI during streaming.

**Architecture:** Add an optional `on_thought` callback to `LLMAdapter.chat_stream()` (following the existing `on_chunk` pattern in `chat()`). DeepSeekAdapter captures `reasoning_content` from SSE deltas. A new `ThinkingWidget` component renders the thinking text at 65% opacity inside `ChatBubbleWidget`, auto-collapsed when main content arrives, with user-fold override.

**Tech Stack:** PyQt6, httpx (SSE streaming), Python `AsyncGenerator`, JSON persistence

---

### Task 1: LLM Adapter — update `chat_stream()` signature

**Files:**
- Modify: `src/llm/base.py:49-58`
- Modify: `src/llm/mock.py:32-41`
- Modify: `src/llm/callback.py:51-67`

- [ ] **Step 1: Add `on_thought` parameter to `LLMAdapter.chat_stream()` ABC**

In `src/llm/base.py`, update the `chat_stream` method signature:

```python
# src/llm/base.py:49-58 — replace the existing chat_stream abstract method
    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        on_thought: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens one at a time.

        If *on_thought* is provided, it is called with reasoning/thinking
        text as it arrives (supported by providers like DeepSeek that
        return ``reasoning_content`` in SSE deltas).
        """
        ...
```

- [ ] **Step 2: Update `MockAdapter.chat_stream()` to accept the new parameter**

In `src/llm/mock.py`, update lines 32-41:

```python
# src/llm/mock.py:32-41 — replace the existing method
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        on_thought: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        response = await self.chat(messages, model, temperature, max_tokens)
        for chunk in response.content.split():
            yield chunk + " "
```

- [ ] **Step 3: Update `CallbackAdapter.chat_stream()` to accept the new parameter**

In `src/llm/callback.py`, update lines 51-57:

```python
# src/llm/callback.py:51-67 — replace the existing method
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        on_thought: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        result = self._chat_fn(messages, None)
        if hasattr(result, "__aiter__"):
            async for chunk in result:
                yield chunk
        else:
            content = await result
            if isinstance(content, LLMResponse):
                yield content.content
            else:
                yield content
```

- [ ] **Step 4: Run existing tests to verify no regressions**

```bash
pytest tests/ -v
```
Expected: all existing tests pass (new parameter has default value, old callers unaffected).

- [ ] **Step 5: Commit**

```bash
git add src/llm/base.py src/llm/mock.py src/llm/callback.py
git commit -m "feat(llm): add on_thought callback parameter to chat_stream()"
```

---

### Task 2: DeepSeekAdapter — capture `reasoning_content` from SSE

**Files:**
- Modify: `src/llm/deepseek.py:116-152` (chat_stream)
- Modify: `src/llm/deepseek.py:235-348` (_chat_streaming_with_tools)

- [ ] **Step 1: Update `chat_stream()` to yield `reasoning_content` via `on_thought`**

In `src/llm/deepseek.py`, update the `chat_stream` method (lines 116-152):

```python
# src/llm/deepseek.py — replace chat_stream method
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        thinking: bool = True,
        reasoning_effort: str = "medium",
        on_thought: Callable[[str], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        messages = self._sanitize_messages(messages)
        payload = self._build_payload(
            messages, model, temperature, max_tokens,
            stream=True, thinking=thinking, reasoning_effort=reasoning_effort,
        )

        client = await self._get_client()
        async with client.stream(
            "POST", f"{self.base_url}/chat/completions", json=payload,
        ) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise RuntimeError(
                    f"DeepSeek request failed ({resp.status_code}): "
                    f"{body.decode('utf-8', errors='ignore')}"
                )

            async for data in self._iter_sse_deltas(resp):
                try:
                    delta = data["choices"][0].get("delta", {})
                    usage = data.get("usage")
                    if usage:
                        self.last_usage = usage
                    # Capture reasoning/thinking content
                    reasoning = delta.get("reasoning_content", "")
                    if reasoning and on_thought:
                        on_thought(reasoning)
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (KeyError, IndexError):
                    continue
```

- [ ] **Step 2: Update `_chat_streaming_with_tools()` to also forward `reasoning_content`**

In `src/llm/deepseek.py`, update the inner loop of `_chat_streaming_with_tools()` (around lines 267-294). The method signature already has `on_chunk` for content; we need to also handle `reasoning_content`. Since the method currently doesn't accept `on_thought`, add it as a parameter and forward:

In `_chat_streaming_with_tools` signature (around line 235):

```python
# src/llm/deepseek.py — update _chat_streaming_with_tools signature
    async def _chat_streaming_with_tools(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]] | None,
        on_chunk: Callable[[str], None],
        thinking: bool = True,
        reasoning_effort: str = "medium",
        on_thought: Callable[[str], None] | None = None,
    ) -> LLMResponse:
```

In the SSE delta parsing loop (around lines 269-294 in the method body), add reasoning_content handling:

```python
# src/llm/deepseek.py — inside _chat_streaming_with_tools SSE loop,
# after the existing "delta = data['choices'][0].get('delta', {})" line:
                            # Capture reasoning/thinking content
                            reasoning = delta.get("reasoning_content", "")
                            if reasoning and on_thought:
                                on_thought(reasoning)

                            content_delta = delta.get("content", "")
                            if content_delta:
                                content_parts.append(content_delta)
                                on_chunk(content_delta)
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/ -v
```
Expected: all existing tests pass.

- [ ] **Step 4: Write a unit test for reasoning_content SSE parsing**

In `tests/test_llm.py`, add a new test method to `TestToolCallDeltaAccumulation`:

```python
    @pytest.mark.asyncio
    async def test_reasoning_content_forwarded_to_on_thought(self):
        """When SSE delta contains reasoning_content, on_thought is called."""
        from unittest.mock import AsyncMock

        sse_lines = [
            self._make_sse_line({"choices": [{"delta": {"reasoning_content": "Let me think"}}]}),
            self._make_sse_line({"choices": [{"delta": {"reasoning_content": " about this."}}]}),
            self._make_sse_line({"choices": [{"delta": {"content": "Here is the answer."}}]}),
            "data: [DONE]",
        ]

        mock_client = self._make_mock_stream(sse_lines)

        adapter = DeepSeekAdapter(api_key="test-key")
        adapter._get_client = AsyncMock(return_value=mock_client)

        thoughts: list[str] = []
        received: list[str] = []
        async for chunk in adapter.chat_stream(
            [{"role": "user", "content": "test"}],
            model="deepseek-chat",
            on_thought=lambda t: thoughts.append(t),
        ):
            received.append(chunk)

        assert "".join(thoughts) == "Let me think about this."
        assert "".join(received) == "Here is the answer."
```

- [ ] **Step 5: Run the new test**

```bash
pytest tests/test_llm.py::TestToolCallDeltaAccumulation::test_reasoning_content_forwarded_to_on_thought -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/llm/deepseek.py tests/test_llm.py
git commit -m "feat(llm): capture reasoning_content from DeepSeek SSE, forward via on_thought"
```

---

### Task 3: Agent.chat_stream — forward `on_thought`

**Files:**
- Modify: `src/core/agent.py:66-76`

- [ ] **Step 1: Forward `on_thought` in `Agent.chat_stream()`**

In `src/core/agent.py`, update lines 66-76:

```python
# src/core/agent.py:66-76 — replace method
    async def chat_stream(self, messages: list[dict[str, Any]], session_id: str = "",
                          on_thought: Callable[[str], None] | None = None):
        try:
            async for chunk in self.llm.chat_stream(
                messages=messages,
                model=self.config.model.name,
                temperature=self.config.model.temperature,
                max_tokens=self.config.model.max_tokens,
                on_thought=on_thought,
            ):
                yield chunk
        finally:
            self._record_usage(self.llm.last_usage, session_id=session_id)
```

Need to add `Callable` import at the top of the file:

```python
# src/core/agent.py:4 — add Callable to typing imports
from typing import Any, Callable, TYPE_CHECKING
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/ -v
```
Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/core/agent.py
git commit -m "feat(agent): forward on_thought callback in Agent.chat_stream()"
```

---

### Task 4: Message model — add `thinking` field

**Files:**
- Modify: `src/core/models.py:57-61`

- [ ] **Step 1: Add `thinking` field to `Message` dataclass**

In `src/core/models.py`, update the Message class (lines 57-61):

```python
# src/core/models.py:57-61 — replace
@dataclass
class Message:
    role: str
    content: str
    timestamp: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)
    thinking: str | None = None
```

- [ ] **Step 2: Verify tests pass**

```bash
pytest tests/test_session.py -v
```
Expected: all tests pass (new field has default value `None`).

- [ ] **Step 3: Commit**

```bash
git add src/core/models.py
git commit -m "feat(models): add optional thinking field to Message"
```

---

### Task 5: Session persistence — save/load `[thinking]` lines

**Files:**
- Modify: `src/core/session.py:68-73` (add_message)
- Modify: `src/core/session.py:125-131` (render_content_lines)
- Modify: `src/core/session.py:134-152` (parse_content_lines)

- [ ] **Step 1: Update `add_message()` to accept thinking parameter**

In `src/core/session.py`, update lines 68-73:

```python
# src/core/session.py:68-73 — replace
    async def add_message(self, role: str, content: str,
                          thinking: str | None = None) -> Message:
        if thinking:
            think_msg = Message(role="thinking", content=thinking)
            self.messages.append(think_msg)
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        self.meta.updated_at = utc_now_iso()
        return msg
```

- [ ] **Step 2: Update `render_content_lines()` to handle `[thinking]` messages**

In `src/core/session.py`, the existing `render_content_lines` already loops over messages and writes `[role] content`. Since we store thinking as a separate Message with `role="thinking"`, the existing render code handles it as-is — no change needed. Verify the output looks like:

```
[2026-05-29T20:30:02Z] [thinking] "..."
[2026-05-29T20:30:05Z] [assistant] "..."
```

No code change for `render_content_lines`.

- [ ] **Step 3: Update `parse_content_lines()` to handle `[thinking]` role**

In `src/core/session.py`, `parse_content_lines` at line 134 already handles arbitrary roles — it reads the role from the line. The `[thinking]` role will be parsed as a Message with `role="thinking"`. No code change needed for parsing either.

However, we need to ensure that when loading messages, thinking messages are associated with the following assistant message. Update the `load` method or add a post-processing step. Actually, the simplest approach: keep thinking as a separate message in the list but have the UI skip rendering it as a standalone bubble. Instead, the UI pairs thinking messages with the following assistant message.

- [ ] **Step 4: Run existing session tests**

```bash
pytest tests/test_session.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Add a test for thinking persistence**

In `tests/test_session.py`, add a test:

```python
    def test_add_message_with_thinking(self, tmp_store):
        """Thinking messages are persisted before assistant messages."""
        import asyncio
        session = asyncio.run(
            Session.create("test", "agent", "agt1", tmp_store)
        )
        asyncio.run(session.add_message("user", "Hello"))
        asyncio.run(session.add_message("assistant", "Response",
                                         thinking="Let me think..."))
        asyncio.run(session.save())

        # Reload
        loaded = asyncio.run(Session.load(session.meta.id, tmp_store))
        roles = [m.role for m in loaded.messages]
        assert roles == ["user", "thinking", "assistant"]
        assert loaded.messages[1].content == "Let me think..."
        assert loaded.messages[1].thinking is None  # thinking messages don't nest
```

- [ ] **Step 6: Run the new test**

```bash
pytest tests/test_session.py::test_add_message_with_thinking -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/core/session.py tests/test_session.py
git commit -m "feat(session): persist thinking messages with [thinking] role"
```

---

### Task 6: ThinkingWidget — new collapsible thinking display component

**Files:**
- Create: (code goes in `src/ui/chat_widget.py` after `StreamingBuffer`)

- [ ] **Step 1: Add `ThinkingWidget` class to `chat_widget.py`**

Insert after the `StreamingBuffer` class (after line 118), before the `# ── Chat bubble ──` comment:

```python
# ── Thinking process display ──────────────────────────────────────────────


class ThinkingWidget(QFrame):
    """Collapsible, semi-transparent thinking process display.

    Renders above the assistant reply bubble.  Shows a 🧠 header with
    expand/collapse toggle, and the thinking text at ~65% opacity.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._thinking_text: str = ""
        self._streaming: bool = False
        self._user_folded: bool = False
        self._collapsed: bool = False
        self._start_time: float | None = None

        self._build_ui()
        self.setVisible(False)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── Header bar ──
        header = QWidget()
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.mousePressEvent = lambda e: self._toggle()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 3, 8, 3)
        header_layout.setSpacing(6)

        self._icon_label = QLabel("🧠")
        self._icon_label.setFixedWidth(18)
        header_layout.addWidget(self._icon_label)

        self._title_label = QLabel("思考过程")
        self._title_label.setStyleSheet(
            "color: #a0a0a0; font-size: 11px; font-weight: 500; background: transparent;"
        )
        header_layout.addWidget(self._title_label)

        self._time_label = QLabel("")
        self._time_label.setStyleSheet(
            "color: #6a6a6a; font-size: 9px; background: transparent;"
        )
        header_layout.addWidget(self._time_label)

        header_layout.addStretch(1)

        self._toggle_btn = QPushButton("▲ 收起")
        self._toggle_btn.setFixedHeight(20)
        self._toggle_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #858585; border: 1px solid rgba(255,255,255,0.06);"
            "  border-radius: 4px; padding: 0 8px; font-size: 10px;"
            "}"
            "QPushButton:hover { color: #cccccc; border-color: rgba(255,255,255,0.15); }"
        )
        self._toggle_btn.clicked.connect(self._toggle)
        header_layout.addWidget(self._toggle_btn)

        layout.addWidget(header)

        # ── Content body ──
        self._body = QTextBrowser()
        self._body.setOpenExternalLinks(False)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setFrameShape(QFrame.Shape.NoFrame)
        self._body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._body.setStyleSheet(
            "QTextBrowser {"
            "  background: transparent; border: none;"
            "  color: #a0a0a0; font-size: 11.5px;"
            "  font-style: italic; line-height: 1.55;"
            "}"
        )
        self._body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._body)

        # ── Whole-widget styling ──
        self.setStyleSheet(
            "ThinkingWidget {"
            "  border: 1px solid rgba(255,255,255,0.08);"
            "  background: rgba(255,255,255,0.04);"
            "  border-radius: 10px;"
            "}"
        )

        # Opacity effect for semi-transparency
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.65)
        self.setGraphicsEffect(self._opacity)

    # ── Public API ──────────────────────────────────────────────────────

    def start_stream(self) -> None:
        """Begin streaming mode — auto-expand and show animated dots."""
        self._streaming = True
        self._start_time = __import__('time').time()
        self._thinking_text = ""
        if not self._user_folded:
            self._collapsed = False
            self._body.setVisible(True)
            self._toggle_btn.setText("▲ 收起")
        self._title_label.setText("正在思考...")
        self.setVisible(True)

    def append_chunk(self, chunk: str) -> None:
        """Append a streaming chunk of thinking text."""
        if self._streaming:
            self._thinking_text += chunk
            # Show plain text — no markdown rendering
            self._body.setPlainText(self._thinking_text)
            # Auto-scroll to bottom
            bar = self._body.verticalScrollBar()
            if bar:
                bar.setValue(bar.maximum())

    def finalize(self) -> None:
        """Mark thinking as complete. Auto-collapse if user hasn't folded."""
        self._streaming = False
        if self._start_time:
            elapsed = __import__('time').time() - self._start_time
            self._time_label.setText(f"耗时 {elapsed:.1f}s")
        self._title_label.setText("思考过程")
        if not self._user_folded:
            self._collapse()

    def set_collapsed(self, collapsed: bool) -> None:
        """Programmatic collapse/expand."""
        if collapsed:
            self._collapse()
        else:
            self._expand()

    def is_user_folded(self) -> bool:
        return self._user_folded

    # ── Internals ───────────────────────────────────────────────────────

    def _toggle(self) -> None:
        if self._collapsed:
            self._expand()
        else:
            self._user_folded = True
            self._collapse()

    def _collapse(self) -> None:
        self._collapsed = True
        self._body.setVisible(False)
        self._toggle_btn.setText("▼ 展开")

    def _expand(self) -> None:
        self._collapsed = False
        self._body.setVisible(True)
        self._toggle_btn.setText("▲ 收起")
```

- [ ] **Step 2: Verify the file has no syntax errors**

```bash
python -c "from src.ui.chat_widget import ThinkingWidget; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/ui/chat_widget.py
git commit -m "feat(ui): add ThinkingWidget — collapsible semi-transparent thinking display"
```

---

### Task 7: ChatBubbleWidget — integrate ThinkingWidget

**Files:**
- Modify: `src/ui/chat_widget.py` — `ChatBubbleWidget.__init__` and related methods

- [ ] **Step 1: Add ThinkingWidget to ChatBubbleWidget**

In `ChatBubbleWidget.__init__()`, after the header layout and before the content area (around line 188), add the thinking widget:

In the `__init__`, after self.copy_button setup (around line 187) and before the content area comment (line 189):

```python
        # ── thinking process (shown above content) ──
        self.thinking_widget = ThinkingWidget()
        self.thinking_widget.setVisible(False)
```

Then in the layout assembly (around line 221-225), insert thinking_widget between header and content:

```python
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        layout.addLayout(header_layout)
        layout.addWidget(self.thinking_widget)
        layout.addWidget(self.label)
```

- [ ] **Step 2: Add `append_thinking`, `finalize_thinking`, `start_thinking` methods**

Add to `ChatBubbleWidget`:

```python
    def start_thinking(self) -> None:
        """Show and start the thinking widget in streaming mode."""
        self.thinking_widget.start_stream()

    def append_thinking(self, chunk: str) -> None:
        """Append a thinking text chunk during streaming."""
        self.thinking_widget.append_chunk(chunk)

    def finalize_thinking(self) -> None:
        """Complete the thinking stream — auto-collapses unless user-folded."""
        self.thinking_widget.finalize()
```

- [ ] **Step 3: Auto-collapse thinking when content arrives**

In `append_chunk()` (line 241), add auto-collapse logic: when the first content chunk arrives and thinking is streaming, finalize it:

```python
    def append_chunk(self, chunk: str, render_latex: bool = True) -> None:
        """Append a streaming chunk and re-render the full accumulated text."""
        # Auto-finalize thinking when main content starts
        if self.thinking_widget.isVisible() and self.thinking_widget._streaming:
            self.thinking_widget.finalize()
        self._raw_text += chunk
        self._render_latex = self._render_latex or render_latex
        if not self._use_web:
            if self._render_latex:
                safe_segments = self._buffer.feed(chunk)
                if safe_segments:
                    self.label.setMarkdown(self._raw_text)
            else:
                self.label.setMarkdown(self._raw_text)
        else:
            self._render()
        self._apply_width_constraints()
```

- [ ] **Step 4: Verify syntax**

```bash
python -c "from src.ui.chat_widget import ChatBubbleWidget; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/ui/chat_widget.py
git commit -m "feat(ui): integrate ThinkingWidget into ChatBubbleWidget"
```

---

### Task 8: ChatWorker — emit `thought_chunk` signal

**Files:**
- Modify: `src/ui/session_panel.py:77-115` (ChatWorker)

- [ ] **Step 1: Add `thought_chunk` signal to `ChatWorker`**

In `src/ui/session_panel.py`, update ChatWorker (lines 77-78):

```python
class ChatWorker(QThread):
    chunk_received = pyqtSignal(str)
    thought_chunk = pyqtSignal(str)
    finished_reply = pyqtSignal(str)
    failed = pyqtSignal(str)
```

- [ ] **Step 2: Pass `on_thought` callback in `_task()`**

Update the `_task` method (lines 98-115):

```python
    async def _task(self) -> str:
        agent = await Agent.load(self.agent_id, self.store, self.vault, token_tracker=self.token_tracker)
        reply_parts: list[str] = []
        thinking_parts: list[str] = []

        def on_thought(text: str) -> None:
            thinking_parts.append(text)
            self.thought_chunk.emit(text)

        try:
            messages = self.session.build_context_messages(agent.config.system_prompt)
            async for chunk in agent.chat_stream(
                messages, session_id=self.session.meta.id,
                on_thought=on_thought,
            ):
                reply_parts.append(chunk)
                self.chunk_received.emit(chunk)
        except Exception as exc:
            error_text = f"[Error] {exc}"
            await self.session.add_message("assistant", error_text)
            await self.session.save()
            raise
        reply = "".join(reply_parts)
        thinking = "".join(thinking_parts)
        await self.session.add_message("assistant", reply, thinking=thinking if thinking else None)
        self.session.maybe_compress_context()
        await self.session.save()
        return reply
```

- [ ] **Step 3: Verify syntax**

```bash
python -c "from src.ui.session_panel import ChatWorker; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/ui/session_panel.py
git commit -m "feat(session_panel): add thought_chunk signal to ChatWorker"
```

---

### Task 9: SessionPanel — wire thinking to UI

**Files:**
- Modify: `src/ui/session_panel.py` — `_start_stream`, `_on_chunk`, `_on_finished`, `_on_failed`, `_render_session`

- [ ] **Step 1: Connect `thought_chunk` signal in `_start_stream()`**

In `src/ui/session_panel.py`, update `_start_stream` (around line 621-625):

```python
    def _start_stream(self, agent_id: str, content: str) -> None:
        if not self.active_session:
            return
        self.send_button.setEnabled(False)
        self.input_box.setEnabled(False)
        if self.session_combo:
            self.session_combo.setEnabled(False)
        if self.new_session_button:
            self.new_session_button.setEnabled(False)

        self._worker = ChatWorker(agent_id, content, self.active_session, self.store, self.vault, token_tracker=self.token_tracker)
        self._worker.chunk_received.connect(self._on_chunk)
        self._worker.thought_chunk.connect(self._on_thought_chunk)
        self._worker.finished_reply.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
```

- [ ] **Step 2: Add `_on_thought_chunk` handler**

Add a new method to `SessionPanel`:

```python
    def _on_thought_chunk(self, chunk: str) -> None:
        if not self._stream_bubble:
            return
        if not self._stream_bubble.thinking_widget.isVisible():
            self._stream_bubble.start_thinking()
        self._stream_bubble.append_thinking(chunk)
```

- [ ] **Step 3: Add thinking finalization in `_on_chunk`**

Update `_on_chunk` to finalize thinking when the first content chunk arrives:

```python
    def _on_chunk(self, chunk: str) -> None:
        self._stream_text += chunk
        if self._stream_bubble:
            # When first content chunk arrives, thinking is auto-finalized
            # inside append_chunk (ChatBubbleWidget handles the auto-collapse)
            self.chat_view.append_to_message(self._stream_bubble, chunk, render_latex=True)
```

Note: The auto-finalize logic is already in `ChatBubbleWidget.append_chunk()` from Task 7 Step 3. No additional changes needed here beyond ensuring the connection exists.

- [ ] **Step 4: Add thinking finalization in `_on_finished`**

Update `_on_finished` to ensure thinking is finalized:

```python
    def _on_finished(self, reply: str) -> None:
        if self._stream_bubble:
            # Ensure thinking is finalized even if no content chunks arrived
            if self._stream_bubble.thinking_widget.isVisible():
                self._stream_bubble.finalize_thinking()
            self.chat_view.flush_stream_to_message(self._stream_bubble)
        self._enable_input()
        self._suppress_reload = True
        self.refresh_sessions()
        self._suppress_reload = False
        self.sessions_changed.emit()
```

- [ ] **Step 5: Handle thinking in historical message rendering**

Update `_render_session` to create thinking widgets for messages that have thinking content. Replace the message rendering loop (around lines 870-871):

```python
        for msg in self._all_messages[self._display_offset:]:
            if msg.role == "thinking":
                # Skip standalone rendering — thinking is attached
                # to the next assistant bubble
                continue
            bubble = self.chat_view.add_message(msg.role, msg.content, render_latex=True)
            # Attach thinking from the previous message if it was a thinking role
            # We need to pair thinking messages with their following assistant message.
```

Actually, we need a different approach for pairing. The thinking message comes right before the assistant message in the message list. Let's iterate differently:

```python
        msgs = self._all_messages[self._display_offset:]
        i = 0
        while i < len(msgs):
            msg = msgs[i]
            # Check if next message is a thinking-role msg followed by assistant
            thinking_text: str | None = None
            if msg.role == "thinking" and i + 1 < len(msgs):
                # Pair this thinking with the next message
                thinking_text = msg.content
                i += 1
                msg = msgs[i]  # Advance to the paired message
            bubble = self.chat_view.add_message(msg.role, msg.content, render_latex=True)
            if thinking_text:
                bubble.thinking_widget._thinking_text = thinking_text
                bubble.thinking_widget._body.setPlainText(thinking_text)
                bubble.thinking_widget._title_label.setText("思考过程")
                bubble.thinking_widget._collapsed = True
                bubble.thinking_widget._body.setVisible(False)
                bubble.thinking_widget._toggle_btn.setText("▼ 展开")
                bubble.thinking_widget.setVisible(True)
            i += 1
```

Wait, but `add_message` also calls `set_content` which renders. For simplicity, let's add the thinking after the bubble is created. Let me refine:

```python
        msgs = self._all_messages[self._display_offset:]
        i = 0
        while i < len(msgs):
            msg = msgs[i]
            # Handle thinking → assistant pairing
            thinking_text: str | None = None
            if msg.role == "thinking":
                thinking_text = msg.content
                i += 1
                if i >= len(msgs):
                    break
                msg = msgs[i]
            bubble = self.chat_view.add_message(msg.role, msg.content, render_latex=True)
            if thinking_text:
                bubble.thinking_widget._thinking_text = thinking_text
                bubble.thinking_widget._body.setPlainText(thinking_text)
                bubble.thinking_widget._title_label.setText("思考过程")
                bubble.thinking_widget.set_collapsed(True)
                bubble.thinking_widget.setVisible(True)
            i += 1
```

- [ ] **Step 6: Handle failed state — ensure thinking is cleaned up**

Update `_on_failed`:

```python
    def _on_failed(self, message: str) -> None:
        if self._stream_bubble:
            # Hide thinking widget on failure
            self._stream_bubble.thinking_widget.setVisible(False)
            self.chat_view.update_message(self._stream_bubble, f"[Error] {message}", render_latex=False)
        self._enable_input()
        self._suppress_reload = True
        self.refresh_sessions()
        self._suppress_reload = False
        self.sessions_changed.emit()
```

- [ ] **Step 7: Run the app health check**

```bash
python main.py --health
```
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add src/ui/session_panel.py
git commit -m "feat(session_panel): wire thinking display to UI streaming and history"
```

---

### Task 10: Visual verification — manual test

**Files:**
- None (manual testing)

- [ ] **Step 1: Launch the app**

```bash
python main.py
```

- [ ] **Step 2: Verify the following scenarios**

1. **Streaming thinking**: Send a message to a DeepSeek agent with thinking enabled. Verify:
   - 🧠 "正在思考..." appears above the assistant bubble
   - Thinking text streams in real-time at 65% opacity
   - When content starts, thinking auto-collapses
   - Can manually re-expand to read thinking

2. **User-fold override**: During streaming, manually fold thinking. Verify it stays folded even when new thinking chunks arrive.

3. **History persistence**: Send a message, close the app, reopen. Verify the thinking block is visible (collapsed) when loading the session.

4. **Multi-turn**: Send multiple messages. Verify each reply has its own thinking block.

5. **No thinking**: Use a mock adapter agent. Verify no thinking widget appears.

- [ ] **Step 3: Fix any issues found during manual testing**

- [ ] **Step 4: Commit any fixes**

---

### Task 11: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v
```
Expected: all tests pass, including the new `test_reasoning_content_forwarded_to_on_thought` and `test_add_message_with_thinking`.

- [ ] **Step 2: Fix any regressions**

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: final integration fixes for thinking display"
```
