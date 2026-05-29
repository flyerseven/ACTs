from __future__ import annotations

import asyncio
import json

from PyQt6.QtCore import Qt, QPropertyAnimation, QThread, QTimer, pyqtSignal

from PyQt6.QtGui import QPainter, QColor, QBrush
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from typing import TYPE_CHECKING

import sys

from core.agent import Agent
from core.models import agent_config_from_dict, session_meta_from_dict, session_meta_to_dict, utc_now_iso
from core.session import Session
from security.vault import Vault
from storage.file_store import FileStore
from storage.yaml_io import read_yaml, write_yaml
from ui.chat_widget import ChatBubbleWidget, ChatViewWidget
from ui.session_create_panel import SessionCreateData, SessionCreateWidget

if TYPE_CHECKING:
    from core.token_tracker import TokenTracker


class LoadingDots(QWidget):
    """Three pulsing dots in a wave, similar to GPT's loading indicator."""

    DOT_COUNT = 3
    DOT_SIZE = 8
    DOT_GAP = 8
    CYCLE_MS = 1200  # one full wave cycle

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        w = self.DOT_COUNT * self.DOT_SIZE + (self.DOT_COUNT - 1) * self.DOT_GAP
        self.setFixedSize(w, self.DOT_SIZE + 4)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(50)

    def _step(self) -> None:
        self._phase += 0.15
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = self.height() // 2
        for i in range(self.DOT_COUNT):
            offset = i * (2 * 3.14159 / self.DOT_COUNT)
            v = (1.0 + __import__('math').sin(self._phase + offset)) / 2.0
            alpha = int(60 + v * 180)  # 60-240 range for visible contrast
            x = i * (self.DOT_SIZE + self.DOT_GAP) + self.DOT_SIZE // 2
            p.setBrush(QBrush(QColor(148, 163, 184, alpha)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(x - self.DOT_SIZE // 2, y - self.DOT_SIZE // 2,
                          self.DOT_SIZE, self.DOT_SIZE)
        p.end()


class ChatWorker(QThread):
    chunk_received = pyqtSignal(str)
    finished_reply = pyqtSignal(str)
    failed = pyqtSignal(str)

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
            reply = asyncio.run(self._task())
            self.finished_reply.emit(reply)
        except Exception as exc:
            self.failed.emit(str(exc))

    async def _task(self) -> str:
        agent = await Agent.load(self.agent_id, self.store, self.vault, token_tracker=self.token_tracker)
        reply_parts: list[str] = []
        try:
            messages = self.session.build_context_messages(agent.config.system_prompt)
            async for chunk in agent.chat_stream(messages, session_id=self.session.meta.id):
                reply_parts.append(chunk)
                self.chunk_received.emit(chunk)
        except Exception as exc:
            error_text = f"[Error] {exc}"
            await self.session.add_message("assistant", error_text)
            await self.session.save()
            raise
        reply = "".join(reply_parts)
        await self.session.add_message("assistant", reply)
        self.session.maybe_compress_context()
        await self.session.save()
        return reply


class EngineWorker(QThread):
    """Runs AgentEngine for decision-core agents."""

    thought_chunk = pyqtSignal(int, str)
    thought_done = pyqtSignal(int, str)
    tool_call_signal = pyqtSignal(int, str, str)
    tool_result_signal = pyqtSignal(int, str, str, float)
    reflection_signal = pyqtSignal(int, str, bool)
    step_end_signal = pyqtSignal(int, bool)
    engine_started = pyqtSignal(str)
    engine_finished = pyqtSignal(str, int, str)
    engine_failed_signal = pyqtSignal(str)
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
            self.engine_failed_signal.emit(str(exc))

    async def _task(self) -> None:
        from core.agent import Agent
        from core.skill import discover_skills
        from pathlib import Path

        agent = await Agent.load(self.agent_id, self.store, self.vault, token_tracker=self.token_tracker)
        api_key = self.vault.resolve_key_ref(agent.config.model.api_key_ref)
        engine = agent.create_engine(api_key)
        engine.config.debug = True  # enable stderr debug output for console visibility

        self.engine_started.emit(self.content)

        # ── Build enhanced system prompt with skill extensions ──
        enabled = agent.config.skills or []
        system_prompt = agent.config.system_prompt
        if enabled:
            skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
            discovered = list(discover_skills(skills_dir))
            all_skills = {s.name: s for _, s in discovered}
            extensions: list[str] = []
            for skill_name in enabled:
                skill = all_skills.get(skill_name)
                if skill and skill.prompt_extension:
                    extensions.append(skill.prompt_extension)
                elif not skill:
                    print(f"  [!] Skill '{skill_name}' not found in {skills_dir} (available: {list(all_skills.keys())})",
                          flush=True, file=sys.stderr)
            if extensions:
                skill_blocks = "\n\n---\n\n".join(extensions)
                if system_prompt.strip():
                    system_prompt = f"{system_prompt.strip()}\n\n---\n\n{skill_blocks}"
                else:
                    system_prompt = skill_blocks

        print(f"\n  SKILLS enabled: {enabled if enabled else '(none)'}", flush=True, file=sys.stderr)
        print(f"  SYSTEM PROMPT ({len(system_prompt)} chars)", flush=True, file=sys.stderr)

        step_index = 0

        def on_chunk(chunk: str) -> None:
            self.thought_chunk.emit(step_index, chunk)

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
            elif event.type == "stopped":
                self.step_end_signal.emit(step_index, False)
            elif event.type == "tool_call":
                self.tool_call_signal.emit(
                    event.data["index"],
                    event.data["name"],
                    json.dumps(event.data["arguments"], ensure_ascii=False))
            elif event.type == "tool_result":
                self.tool_result_signal.emit(
                    event.data["index"],
                    event.data["result"],
                    event.data.get("error", ""),
                    event.data.get("duration_ms", 0.0))
            elif event.type == "reflection":
                self.reflection_signal.emit(
                    event.data["index"],
                    event.data["summary"],
                    event.data.get("is_stuck", False))

        engine.observer.emit = patched_emit

        state = await engine.run(self.content, on_thought_chunk=on_chunk,
                                  system_prompt=system_prompt,
                                  enabled_skills=agent.config.skills)

        for step in state.steps:
            if step.thought:
                self.thought_done.emit(step.index, step.thought)

        # Extract the final answer from the last step's thought,
        # stripping the DONE/FAILED sentinel that the engine uses internally.
        last_thought = ""
        for step in reversed(state.steps):
            if step.thought:
                last_thought = step.thought
                break

        import re
        reply = re.sub(r'\b(DONE|FAILED)\b[:\s]*', '', last_thought, flags=re.IGNORECASE).strip()
        if not reply:
            reply = "Task completed."

        await self.session.add_message("assistant", reply)
        self.session.maybe_compress_context()
        await self.session.save()

        self.engine_finished.emit(
            state.status, len(state.steps),
            json.dumps(state.errors, ensure_ascii=False))
        self.finished_reply.emit(reply)


class LoadSessionWorker(QThread):
    loaded = pyqtSignal(object)  # Session
    failed = pyqtSignal(str)

    def __init__(self, session_id: str, store: FileStore) -> None:
        super().__init__()
        self.session_id = session_id
        self.store = store

    def run(self) -> None:
        try:
            session = asyncio.run(Session.load(self.session_id, self.store))
            self.loaded.emit(session)
        except Exception as exc:
            self.failed.emit(str(exc))


class SessionPanel(QWidget):
    PAGE_SIZE = 20

    sessions_changed = pyqtSignal()
    session_edited = pyqtSignal(str)  # session_id

    def __init__(self, store: FileStore, vault: Vault, show_session_header: bool = True, token_tracker: "TokenTracker | None" = None) -> None:
        super().__init__()
        self.store = store
        self.vault = vault
        self.token_tracker = token_tracker
        self.active_session: Session | None = None
        self._worker: ChatWorker | EngineWorker | None = None
        self._stream_bubble: ChatBubbleWidget | None = None
        self._stream_text: str = ""
        self._suppress_reload: bool = False
        self.session_combo: QComboBox | None = None
        self.new_session_button: QPushButton | None = None
        self._session_create: SessionCreateWidget | None = None
        self._chat_page: QWidget | None = None
        self._page_stack: QVBoxLayout | None = None
        self._display_offset: int = 0
        self._all_messages: list = []
        self._suppress_scroll_load: bool = False
        self._load_worker: LoadSessionWorker | None = None
        self._load_spinner: QWidget | None = None
        self._spinner_dots: LoadingDots | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Toolbar ──
        toolbar = QFrame()
        toolbar.setFixedHeight(48)
        toolbar.setStyleSheet(
            "QFrame { background-color: #252526; border-bottom: 1px solid #3c3c3c; }"
        )
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 0, 16, 0)
        toolbar_layout.setSpacing(10)

        if show_session_header:
            session_label = QLabel("Session")
            session_label.setStyleSheet("color: #6a6a6a; font-size: 11px; font-weight: 600;")
            toolbar_layout.addWidget(session_label)

            self.session_combo = QComboBox()
            self.session_combo.setMinimumWidth(180)
            self.session_combo.setFixedHeight(32)
            toolbar_layout.addWidget(self.session_combo)

            self.new_session_button = QPushButton("+ New")
            self.new_session_button.setProperty("cssClass", "small")
            self.new_session_button.setFixedHeight(32)
            toolbar_layout.addWidget(self.new_session_button)

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setStyleSheet("background-color: #3c3c3c; max-width: 1px; border: none;")
            sep.setFixedHeight(20)
            toolbar_layout.addWidget(sep)

        agent_label = QLabel("Agent")
        agent_label.setStyleSheet("color: #6a6a6a; font-size: 11px; font-weight: 600;")
        toolbar_layout.addWidget(agent_label)

        self.agent_combo = QComboBox()
        self.agent_combo.setMinimumWidth(180)
        self.agent_combo.setFixedHeight(32)
        toolbar_layout.addWidget(self.agent_combo)

        self.agent_label = QLabel()
        self.agent_label.setMinimumWidth(180)
        self.agent_label.setFixedHeight(32)
        self.agent_label.setStyleSheet(
            "color: #e0e0e0; font-size: 12px; font-weight: 600;"
            "background-color: #2d2d2d; border: 1px solid #3c3c3c;"
            "border-radius: 6px; padding: 4px 10px;"
        )
        self.agent_label.setVisible(False)
        toolbar_layout.addWidget(self.agent_label)

        toolbar_layout.addStretch(1)

        layout.addWidget(toolbar)

        # ── Chat page ──
        self._chat_page = QWidget()
        chat_layout = QVBoxLayout(self._chat_page)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        self.chat_view = ChatViewWidget()
        chat_layout.addWidget(self.chat_view, stretch=1)

        # Input bar
        input_bar = QFrame()
        input_bar.setStyleSheet(
            "QFrame { background-color: #252526; border-top: 1px solid #3c3c3c; }"
        )
        input_layout = QHBoxLayout(input_bar)
        input_layout.setContentsMargins(16, 10, 16, 10)
        input_layout.setSpacing(10)

        self.input_box = QPlainTextEdit()
        self.input_box.setPlaceholderText("Type a message... (Enter to send, Shift+Enter for new line)")
        self.input_box.setFixedHeight(60)
        self.input_box.setStyleSheet(
            "QPlainTextEdit {"
            "background-color: #3c3c3c;"
            "border: 1px solid #3c3c3c;"
            "border-radius: 10px;"
            "padding: 10px 14px;"
            "color: #cccccc;"
            "font-size: 12.5px;"
            "}"
            "QPlainTextEdit:focus {"
            "border-color: #007acc;"
            "}"
        )
        input_layout.addWidget(self.input_box, stretch=1)

        self.send_button = QPushButton("Send")
        self.send_button.setProperty("cssClass", "primary")
        self.send_button.setFixedHeight(40)
        self.send_button.setFixedWidth(64)
        input_layout.addWidget(self.send_button)

        chat_layout.addWidget(input_bar)

        # ── Create page ──
        self._session_create = SessionCreateWidget()

        # ── Page stack ──
        self._page_stack = QVBoxLayout()
        self._page_stack.setContentsMargins(0, 0, 0, 0)
        self._page_stack.addWidget(self._chat_page)
        self._page_stack.addWidget(self._session_create)
        layout.addLayout(self._page_stack, stretch=1)

        # ── Pagination ──
        self.chat_view.scrolled_to_top.connect(self._load_more_messages)

        # ── Connections ──
        self.send_button.clicked.connect(self.send_message)
        self.input_box.installEventFilter(self)
        if self.new_session_button:
            self.new_session_button.clicked.connect(self.show_create_page)
        if self.session_combo:
            self.session_combo.currentIndexChanged.connect(self.load_selected_session)
        if self._session_create:
            self._session_create.create_requested.connect(self._handle_create_requested)
            self._session_create.cancel_requested.connect(self.show_chat_page)

        self.refresh_agents()
        self.refresh_sessions(select_latest=True)
        self._sync_create_agents()
        self.show_chat_page()

    # ── Enter-to-send ───────────────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        from PyQt6.QtCore import QEvent
        if obj is self.input_box and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self.send_message()
                return True
        return super().eventFilter(obj, event)

    # ── Agent / Session list ────────────────────────────────────────────

    def refresh_agents(self) -> None:
        self.agent_combo.clear()
        for agent_id in sorted(self.store.list_agents()):
            try:
                config = agent_config_from_dict(read_yaml(self.store.agent_yaml_path(agent_id)))
                label = f"{config.name} ({config.model.name})"
            except Exception:
                label = agent_id
            self.agent_combo.addItem(label, agent_id)
        self._sync_create_agents()

    def _sync_create_agents(self) -> None:
        if not self._session_create:
            return
        agents: list[tuple[str, str]] = []
        for agent_id in sorted(self.store.list_agents()):
            config = agent_config_from_dict(read_yaml(self.store.agent_yaml_path(agent_id)))
            label = f"{config.name} ({config.model.name})"
            agents.append((agent_id, label))
        self._session_create.set_agents(agents)

    def refresh_sessions(self, select_latest: bool = False) -> None:
        if not self.session_combo:
            return
        current_id = self.session_combo.currentData()
        self.session_combo.clear()

        sessions = []
        for session_id in self.store.list_sessions():
            meta = session_meta_from_dict(read_yaml(self.store.session_yaml_path(session_id)))
            sessions.append((meta.updated_at, session_id, meta.name))
        sessions.sort(reverse=True)

        for _, session_id, name in sessions:
            label = f"{name} ({session_id})"
            self.session_combo.addItem(label, session_id)

        if select_latest and sessions:
            self.session_combo.setCurrentIndex(0)
            self.load_selected_session()
        elif current_id:
            index = self.session_combo.findData(current_id)
            if index >= 0:
                self.session_combo.setCurrentIndex(index)

    # ── Page switching ──────────────────────────────────────────────────

    def show_create_page(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        if self._load_worker and self._load_worker.isRunning():
            return
        if self._session_create:
            self._session_create.reset()
        if self._chat_page and self._session_create and self._page_stack:
            self._chat_page.setVisible(False)
            self._session_create.setVisible(True)

    def show_chat_page(self) -> None:
        if self._chat_page and self._session_create and self._page_stack:
            self._session_create.setVisible(False)
            self._chat_page.setVisible(True)

    def _handle_create_requested(self, data: SessionCreateData) -> None:
        if not data.target_id:
            self.chat_view.add_message("system", "No agent available. Create one first.")
            self.show_chat_page()
            return
        session = asyncio.run(
            Session.create(
                name=data.name,
                target_type="agent",
                target_id=data.target_id,
                store=self.store,
                context_keep_last=data.context_window,
                compression_interval=data.compress_every,
                system_prompt=data.system_prompt,
                allow_agent_switch=data.allow_agent_switch,
            )
        )
        self.active_session = session
        index = self.agent_combo.findData(data.target_id)
        if index >= 0:
            self.agent_combo.setCurrentIndex(index)
        self._apply_agent_switch_mode(session)
        self.refresh_sessions(select_latest=True)
        self._render_session(session)
        self.sessions_changed.emit()
        self.show_chat_page()

    # ── Agent switch mode ──────────────────────────────────────────────

    def _apply_agent_switch_mode(self, session: Session) -> None:
        if session.meta.allow_agent_switch:
            self.agent_combo.setVisible(True)
            self.agent_label.setVisible(False)
        else:
            self.agent_combo.setVisible(False)
            self.agent_label.setVisible(True)
            name = self._agent_name_for_id(session.meta.target_id)
            self.agent_label.setText(name)

    def _agent_name_for_id(self, agent_id: str) -> str:
        try:
            config = agent_config_from_dict(read_yaml(self.store.agent_yaml_path(agent_id)))
            return f"{config.name} ({config.model.name})"
        except Exception:
            return agent_id

    def _current_agent_id(self) -> str:
        if self.active_session and not self.active_session.meta.allow_agent_switch:
            return self.active_session.meta.target_id
        return self.agent_combo.currentData() or ""

    # ── Messaging ───────────────────────────────────────────────────────

    def send_message(self) -> None:
        content = self.input_box.toPlainText().strip()
        if not content:
            return
        if self._worker and self._worker.isRunning():
            return
        if self._load_worker and self._load_worker.isRunning():
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

        self.chat_view.add_message("user", content, render_latex=True)
        self.input_box.clear()

        agent_config = agent_config_from_dict(
            read_yaml(self.store.agent_yaml_path(agent_id)))
        if agent_config.enable_decision_core:
            self._start_engine(agent_id, content)
        else:
            self._stream_text = ""
            self._stream_bubble = self.chat_view.add_message(
                "assistant", "", render_latex=False)
            self._start_stream(agent_id, content)

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
        self._worker.finished_reply.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    # ── Engine (decision-core) streaming ──────────────────────────────────

    def _start_engine(self, agent_id: str, content: str) -> None:
        if not self.active_session:
            return
        self.send_button.setEnabled(False)
        self.input_box.setEnabled(False)
        if self.session_combo:
            self.session_combo.setEnabled(False)
        if self.new_session_button:
            self.new_session_button.setEnabled(False)

        self._stream_text = ""
        self._stream_bubble = self.chat_view.add_message(
            "assistant", "", render_latex=False)

        print("\n" + "=" * 50, flush=True)
        print("  Decision Engine Started", flush=True)
        print(f"  Goal: {content[:200]}", flush=True)
        print("=" * 50, flush=True)

        self._worker = EngineWorker(
            agent_id, content, self.active_session,
            self.store, self.vault, token_tracker=self.token_tracker)
        self._worker.engine_started.connect(self._on_engine_started)
        self._worker.thought_chunk.connect(self._on_engine_thought_chunk)
        self._worker.thought_done.connect(self._on_engine_thought_done)
        self._worker.tool_call_signal.connect(self._on_engine_tool_call)
        self._worker.tool_result_signal.connect(self._on_engine_tool_result)
        self._worker.reflection_signal.connect(self._on_engine_reflection)
        self._worker.step_end_signal.connect(self._on_engine_step_end)
        self._worker.engine_finished.connect(self._on_engine_finished)
        self._worker.finished_reply.connect(self._on_engine_reply)
        self._worker.engine_failed_signal.connect(self._on_engine_failed)
        self._worker.start()

    def _on_engine_started(self, _content: str) -> None:
        pass  # startup banner already printed in _start_engine

    def _on_engine_thought_chunk(self, step_index: int, _chunk: str) -> None:
        pass  # too noisy; full thought logged in thought_done

    def _on_engine_thought_done(self, step_index: int, full_text: str) -> None:
        preview = full_text[:300].replace("\n", " ")
        if len(full_text) > 300:
            preview += "..."
        print(f"  [Step {step_index}] THINK: {preview}", flush=True)

    def _on_engine_tool_call(self, step_index: int, tool_name: str, args_json: str) -> None:
        print(f"  [Step {step_index}] ACT → {tool_name}({args_json[:200]})", flush=True)

    def _on_engine_tool_result(self, step_index: int, result: str, error: str, duration_ms: float) -> None:
        if error:
            print(f"  [Step {step_index}] TOOL ERROR ({duration_ms:.0f}ms): {error[:200]}", flush=True, file=sys.stderr)
        else:
            preview = result[:200].replace("\n", " ")
            if len(result) > 200:
                preview += "..."
            print(f"  [Step {step_index}] RESULT ({duration_ms:.0f}ms): {preview}", flush=True)

    def _on_engine_reflection(self, step_index: int, summary: str, is_stuck: bool) -> None:
        tag = "STUCK" if is_stuck else "OK"
        out = sys.stderr if is_stuck else sys.stdout
        print(f"  [Step {step_index}] REFLECT [{tag}]: {summary[:200]}", flush=True, file=out)

    def _on_engine_step_end(self, step_index: int, _is_completed: bool) -> None:
        print(f"  [Step {step_index}] ── step complete", flush=True)

    def _on_engine_finished(self, status: str, total_steps: int, errors_json: str) -> None:
        import json
        errors = json.loads(errors_json)
        print(f"  Engine finished: status={status}, steps={total_steps}, errors={len(errors)}", flush=True)
        print("=" * 50 + "\n", flush=True)

    def _on_engine_reply(self, reply: str) -> None:
        if self._stream_bubble:
            self.chat_view.update_message(self._stream_bubble, reply, render_latex=True)
        self._enable_input()
        self._suppress_reload = True
        self.refresh_sessions()
        self._suppress_reload = False
        self.sessions_changed.emit()

    def _on_engine_failed(self, message: str) -> None:
        print(f"  Engine FAILED: {message}", flush=True, file=sys.stderr)
        if self._stream_bubble:
            self.chat_view.update_message(self._stream_bubble, f"[Engine Error] {message}", render_latex=False)
        self._enable_input()
        self._suppress_reload = True
        self.refresh_sessions()
        self._suppress_reload = False
        self.sessions_changed.emit()

    # ── Simple chat streaming ─────────────────────────────────────────────

    def _on_chunk(self, chunk: str) -> None:
        self._stream_text += chunk
        if self._stream_bubble:
            self.chat_view.append_to_message(self._stream_bubble, chunk, render_latex=True)

    def _on_finished(self, reply: str) -> None:
        if self._stream_bubble:
            self.chat_view.flush_stream_to_message(self._stream_bubble)
        self._enable_input()
        self._suppress_reload = True
        self.refresh_sessions()
        self._suppress_reload = False
        self.sessions_changed.emit()

    def _on_failed(self, message: str) -> None:
        if self._stream_bubble:
            self.chat_view.update_message(self._stream_bubble, f"[Error] {message}", render_latex=False)
        self._enable_input()
        self._suppress_reload = True
        self.refresh_sessions()
        self._suppress_reload = False
        self.sessions_changed.emit()

    def _enable_input(self) -> None:
        self.send_button.setEnabled(True)
        self.input_box.setEnabled(True)
        if self.session_combo:
            self.session_combo.setEnabled(True)
        if self.new_session_button:
            self.new_session_button.setEnabled(True)

    # ── Session loading ─────────────────────────────────────────────────

    def load_selected_session(self) -> None:
        if self._suppress_reload:
            return
        if self._worker and self._worker.isRunning():
            return
        if self._load_worker and self._load_worker.isRunning():
            return
        if not self.session_combo:
            return
        session_id = self.session_combo.currentData()
        if not session_id:
            self.active_session = None
            self.chat_view.clear()
            return
        self.load_session_by_id(session_id)

    def load_session_by_id(self, session_id: str) -> None:
        if self._suppress_reload:
            return
        if self._worker and self._worker.isRunning():
            return
        if self._load_worker and self._load_worker.isRunning():
            return
        if self.active_session and self.active_session.meta.id == session_id:
            return

        self._show_load_spinner()

        self._load_worker = LoadSessionWorker(session_id, self.store)
        self._load_worker.loaded.connect(self._on_session_loaded)
        self._load_worker.failed.connect(self._on_session_load_failed)
        self._load_worker.start()

    def _show_load_spinner(self) -> None:
        self._hide_load_spinner()

        spinner = QFrame(self._chat_page)
        spinner.setStyleSheet("background-color: #1e1e1e; border: none;")
        spinner.setGeometry(self._chat_page.rect())
        spinner.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        layout = QVBoxLayout(spinner)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        self._spinner_dots = LoadingDots()
        layout.addWidget(self._spinner_dots, alignment=Qt.AlignmentFlag.AlignCenter)

        label = QLabel("Loading")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "color: #858585; font-size: 13px; background: transparent; border: none;"
        )
        layout.addWidget(label)

        spinner.show()
        spinner.raise_()
        self._load_spinner = spinner

    def _hide_load_spinner(self) -> None:
        self._spinner_dots = None
        if self._load_spinner:
            self._load_spinner.deleteLater()
            self._load_spinner = None

    def _on_session_loaded(self, session: Session) -> None:
        self.active_session = session
        self._apply_agent_switch_mode(session)
        self._render_session(session)
        if session.meta.target_id:
            index = self.agent_combo.findData(session.meta.target_id)
            if index >= 0:
                self.agent_combo.setCurrentIndex(index)

    def _on_session_load_failed(self, error: str) -> None:
        self._hide_load_spinner()
        self.chat_view.clear()
        self.chat_view.add_message("system", f"Failed to load session: {error}")

    def _render_session(self, session: Session) -> None:
        # If spinner is already visible, repurpose it as the render mask so there's
        # no visual gap or double-loading appearance. Keep the "Loading..." text
        # animating until messages are fully rendered.
        if self._load_spinner is not None and self._load_spinner.isVisible():
            mask = self._load_spinner
        else:
            mask = QFrame(self._chat_page)
            mask.setStyleSheet("background-color: #1e1e1e; border: none;")
            mask.setGeometry(self.chat_view.geometry())
            mask.show()
            mask.raise_()
        self._render_mask = mask

        self._suppress_scroll_load = True
        self.chat_view.setUpdatesEnabled(False)
        self.chat_view.clear()
        self._all_messages = list(session.messages)
        total = len(self._all_messages)
        self._display_offset = max(0, total - self.PAGE_SIZE)
        for msg in self._all_messages[self._display_offset:]:
            self.chat_view.add_message(msg.role, msg.content, render_latex=True)
        self.chat_view.setUpdatesEnabled(True)
        # Keep scrolling to bottom at increasing delays — WebEngine renders
        # KaTeX asynchronously so the content height grows over time.
        self.chat_view.scroll_to_bottom()
        QTimer.singleShot(300, self.chat_view._scroll_to_bottom)
        QTimer.singleShot(800, self.chat_view._scroll_to_bottom)
        QTimer.singleShot(1500, self._finish_render_session)

    def _finish_render_session(self) -> None:
        self._suppress_scroll_load = False
        self.chat_view._scroll_to_bottom()

        mask = getattr(self, '_render_mask', None)
        if mask is None:
            return
        self._render_mask = None

        # Make the mask click-through during fade-out
        mask.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        effect = QGraphicsOpacityEffect(mask)
        effect.setOpacity(1.0)
        mask.setGraphicsEffect(effect)

        self._render_anim = QPropertyAnimation(effect, b"opacity")
        self._render_anim.setDuration(150)
        self._render_anim.setStartValue(1.0)
        self._render_anim.setEndValue(0.0)

        def _on_finished() -> None:
            mask.deleteLater()
            self._render_anim = None
            self._hide_load_spinner()

        self._render_anim.finished.connect(_on_finished)
        self._render_anim.start()

    def _load_more_messages(self) -> None:
        if self._suppress_scroll_load:
            return
        if not self.active_session:
            return
        current = list(self.active_session.messages)
        if len(current) > len(self._all_messages):
            self._display_offset += len(current) - len(self._all_messages)
            self._all_messages = current
        else:
            self._all_messages = current
        if self._display_offset <= 0:
            return
        start = max(0, self._display_offset - self.PAGE_SIZE)
        batch = self._all_messages[start:self._display_offset]
        for msg in reversed(batch):
            self.chat_view.prepend_message(msg.role, msg.content, render_latex=True)
        self._display_offset = start

    def edit_session_meta(self, session_id: str, **kwargs: object) -> None:
        meta_path = self.store.session_yaml_path(session_id)
        data = read_yaml(meta_path)
        meta = session_meta_from_dict(data)
        for key, value in kwargs.items():
            if hasattr(meta, key):
                setattr(meta, key, value)
        meta.updated_at = utc_now_iso()
        write_yaml(meta_path, session_meta_to_dict(meta))
        if self.active_session and self.active_session.meta.id == session_id:
            for key, value in kwargs.items():
                if hasattr(self.active_session.meta, key):
                    setattr(self.active_session.meta, key, value)
        self.session_edited.emit(session_id)

    def delete_session(self, session_id: str) -> None:
        if self.active_session and self.active_session.meta.id == session_id:
            self.active_session = None
            self.chat_view.clear()
        Session.delete(session_id, self.store)
        self.sessions_changed.emit()
