from __future__ import annotations

import asyncio

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from typing import TYPE_CHECKING

from core.agent import Agent
from core.models import agent_config_from_dict, session_meta_from_dict
from core.session import Session
from security.vault import Vault
from storage.file_store import FileStore
from storage.yaml_io import read_yaml
from ui.chat_widget import ChatBubbleWidget, ChatViewWidget
from ui.session_create_panel import SessionCreateData, SessionCreateWidget

if TYPE_CHECKING:
    from core.token_tracker import TokenTracker


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
            messages = self.session.build_context_messages()
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


class SessionPanel(QWidget):
    sessions_changed = pyqtSignal()

    def __init__(self, store: FileStore, vault: Vault, show_session_header: bool = True, token_tracker: "TokenTracker | None" = None) -> None:
        super().__init__()
        self.store = store
        self.vault = vault
        self.token_tracker = token_tracker
        self.active_session: Session | None = None
        self._worker: ChatWorker | None = None
        self._stream_bubble: ChatBubbleWidget | None = None
        self._stream_text: str = ""
        self._suppress_reload: bool = False
        self.session_combo: QComboBox | None = None
        self.new_session_button: QPushButton | None = None
        self._session_create: SessionCreateWidget | None = None
        self._chat_page: QWidget | None = None
        self._page_stack: QVBoxLayout | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        header = QHBoxLayout()
        if show_session_header:
            header.addWidget(QLabel("Session"))
            self.session_combo = QComboBox()
            header.addWidget(self.session_combo)
            self.new_session_button = QPushButton("New Session")
            header.addWidget(self.new_session_button)
            header.addSpacing(12)
        header.addWidget(QLabel("Target Agent"))
        self.agent_combo = QComboBox()
        header.addWidget(self.agent_combo)
        header.addStretch(1)
        layout.addLayout(header)

        self._chat_page = QWidget()
        chat_layout = QVBoxLayout(self._chat_page)
        chat_layout.setContentsMargins(0, 0, 0, 0)

        self.chat_view = ChatViewWidget()
        chat_layout.addWidget(self.chat_view, stretch=1)

        input_row = QHBoxLayout()
        self.input_box = QPlainTextEdit()
        self.input_box.setFixedHeight(80)
        input_row.addWidget(self.input_box, stretch=1)
        self.send_button = QPushButton("Send")
        input_row.addWidget(self.send_button)
        chat_layout.addLayout(input_row)

        self._session_create = SessionCreateWidget()

        self._page_stack = QVBoxLayout()
        self._page_stack.addWidget(self._chat_page)
        self._page_stack.addWidget(self._session_create)
        layout.addLayout(self._page_stack, stretch=1)

        self.send_button.clicked.connect(self.send_message)
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

    def show_create_page(self) -> None:
        if self._worker and self._worker.isRunning():
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
            )
        )
        self.active_session = session
        index = self.agent_combo.findData(data.target_id)
        if index >= 0:
            self.agent_combo.setCurrentIndex(index)
        self.refresh_sessions(select_latest=True)
        self._render_session(session)
        self.sessions_changed.emit()
        self.show_chat_page()

    def send_message(self) -> None:
        content = self.input_box.toPlainText().strip()
        if not content:
            return
        if self._worker and self._worker.isRunning():
            return
        agent_id = self.agent_combo.currentData()
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
        self._stream_text = ""
        self._stream_bubble = self.chat_view.add_message("assistant", "", render_latex=False)
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

    def _on_chunk(self, chunk: str) -> None:
        self._stream_text += chunk
        if self._stream_bubble:
            self.chat_view.append_to_message(self._stream_bubble, chunk, render_latex=True)

    def _on_finished(self, reply: str) -> None:
        if self._stream_bubble:
            self.chat_view.flush_stream_to_message(self._stream_bubble)
        self.send_button.setEnabled(True)
        self.input_box.setEnabled(True)
        if self.session_combo:
            self.session_combo.setEnabled(True)
        if self.new_session_button:
            self.new_session_button.setEnabled(True)
        self._suppress_reload = True
        self.refresh_sessions()
        self._suppress_reload = False
        self.sessions_changed.emit()

    def _on_failed(self, message: str) -> None:
        if self._stream_bubble:
            self.chat_view.update_message(self._stream_bubble, f"[Error] {message}", render_latex=False)
        self.send_button.setEnabled(True)
        self.input_box.setEnabled(True)
        if self.session_combo:
            self.session_combo.setEnabled(True)
        if self.new_session_button:
            self.new_session_button.setEnabled(True)
        self._suppress_reload = True
        self.refresh_sessions()
        self._suppress_reload = False
        self.sessions_changed.emit()

    def load_selected_session(self) -> None:
        if self._suppress_reload:
            return
        if self._worker and self._worker.isRunning():
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
        if self.active_session and self.active_session.meta.id == session_id:
            return
        session = asyncio.run(Session.load(session_id, self.store))
        self.active_session = session
        self._render_session(session)
        if session.meta.target_id:
            index = self.agent_combo.findData(session.meta.target_id)
            if index >= 0:
                self.agent_combo.setCurrentIndex(index)

    def _render_session(self, session: Session) -> None:
        self.chat_view.clear()
        for msg in session.messages:
            self.chat_view.add_message(msg.role, msg.content, render_latex=True)
        self.chat_view.scroll_to_bottom()
        QTimer.singleShot(500, self.chat_view._scroll_to_bottom)
        QTimer.singleShot(1000, self.chat_view._scroll_to_bottom)
