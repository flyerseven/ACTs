from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.agent_panel import AgentPanel
from ui.session_panel import SessionPanel
from core.models import agent_config_from_dict, session_meta_from_dict
from storage.file_store import FileStore
from security.vault import Vault
from storage.yaml_io import read_yaml, write_yaml

if TYPE_CHECKING:
    from core.token_tracker import TokenTracker


class MainWindow(QMainWindow):
    def __init__(self, store: FileStore, vault: Vault, version: str, token_tracker: "TokenTracker | None" = None) -> None:
        super().__init__()
        self.store = store
        self.vault = vault
        self.token_tracker = token_tracker
        self.setWindowTitle(f"ACTs {version}")
        self.resize(1160, 760)
        self.setMinimumSize(800, 500)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)

        wrapper_layout.addWidget(self._build_title_bar(version))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)

        splitter.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.agent_panel = AgentPanel(store=store, vault=vault, show_list=False)
        self.team_panel = self._build_placeholder("Teams will arrive in Phase 2.")
        self.session_panel = SessionPanel(store=store, vault=vault, show_session_header=False, token_tracker=token_tracker)
        self.stack.addWidget(self.agent_panel)
        self.stack.addWidget(self.team_panel)
        self.stack.addWidget(self.session_panel)
        splitter.addWidget(self.stack)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 920])

        wrapper_layout.addWidget(splitter)
        self.setCentralWidget(wrapper)

        self.agent_panel.agents_changed.connect(self._on_agents_changed)
        self.session_panel.sessions_changed.connect(self._on_sessions_changed)

        self._set_active_tab(0)
        self.refresh_agent_list()
        self.refresh_session_list()

    # ── Title bar ───────────────────────────────────────────────────────

    def _build_title_bar(self, version: str) -> QWidget:
        bar = QFrame()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(44)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        # Logo mark — a small colored square
        logo = QLabel()
        logo.setFixedSize(18, 18)
        logo.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3b82f6, stop:1 #8b5cf6);"
            "border-radius: 4px;"
        )
        layout.addWidget(logo)

        title = QLabel("ACTs")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        version_label = QLabel(f"v{version}")
        version_label.setObjectName("subtitleLabel")
        layout.addWidget(version_label)

        layout.addStretch(1)

        return bar

    # ── Sidebar ─────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setMinimumWidth(220)
        sidebar.setMaximumWidth(280)
        sidebar.setStyleSheet("QWidget { background-color: #0b1120; }")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Tab toggle row — pill-style segmented control look
        tab_container = QWidget()
        tab_container.setFixedHeight(36)
        tab_container.setStyleSheet(
            "QWidget { background-color: #0f172a; border-radius: 10px; }"
        )
        tab_row = QHBoxLayout(tab_container)
        tab_row.setContentsMargins(3, 3, 3, 3)
        tab_row.setSpacing(2)

        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)

        self.tab_agents = QPushButton("Agents")
        self.tab_teams = QPushButton("Teams")
        self.tab_sessions = QPushButton("Sessions")

        for index, button in enumerate([self.tab_agents, self.tab_teams, self.tab_sessions]):
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setFixedHeight(30)
            self.tab_group.addButton(button, index)
            tab_row.addWidget(button)

        layout.addWidget(tab_container)

        # Stacked list panels per tab
        self.sidebar_stack = QStackedWidget()

        self.agent_list = QListWidget()
        self.agent_list.setWordWrap(True)
        self.agent_add_button = QPushButton("+ New Agent")
        self.sidebar_stack.addWidget(self._build_list_panel(self.agent_list, self.agent_add_button))

        self.team_list = QListWidget()
        self.team_list.setWordWrap(True)
        self.team_add_button = QPushButton("+ New Team")
        self.team_add_button.setEnabled(False)
        self.sidebar_stack.addWidget(self._build_list_panel(self.team_list, self.team_add_button))

        self.session_list = QListWidget()
        self.session_list.setWordWrap(True)
        self.session_add_button = QPushButton("+ New Session")
        self.sidebar_stack.addWidget(self._build_list_panel(self.session_list, self.session_add_button))

        layout.addWidget(self.sidebar_stack, stretch=1)

        self.tab_group.buttonClicked.connect(lambda btn: self._set_active_tab(self.tab_group.id(btn)))
        self.agent_list.currentItemChanged.connect(self._on_agent_selected)
        self.session_list.currentItemChanged.connect(self._on_session_selected)
        self.agent_add_button.clicked.connect(self._create_agent)
        self.session_add_button.clicked.connect(self._create_session)

        return sidebar

    def _build_list_panel(self, list_widget: QListWidget, add_button: QPushButton) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(list_widget, stretch=1)
        layout.addWidget(add_button)
        return panel

    # ── Tab navigation ──────────────────────────────────────────────────

    def _set_active_tab(self, index: int) -> None:
        self.sidebar_stack.setCurrentIndex(index)
        self.stack.setCurrentIndex(index)
        if index == 0:
            self.tab_agents.setChecked(True)
        elif index == 1:
            self.tab_teams.setChecked(True)
        else:
            self.tab_sessions.setChecked(True)

    # ── List refresh ────────────────────────────────────────────────────

    def refresh_agent_list(self, select_id: str | None = None) -> None:
        current_id = select_id
        if current_id is None:
            current_item = self.agent_list.currentItem()
            if current_item:
                current_id = current_item.data(Qt.ItemDataRole.UserRole)

        self.agent_list.clear()
        agent_ids = sorted(self.store.list_agents())
        if not agent_ids:
            created_id = self.agent_panel.create_agent(emit_signal=False)
            agent_ids = [created_id]
            current_id = created_id

        for agent_id in agent_ids:
            config = agent_config_from_dict(read_yaml(self.store.agent_yaml_path(agent_id)))
            item = QListWidgetItem()
            item.setText(f"{config.name}\n  {config.model.name}")
            item.setData(Qt.ItemDataRole.UserRole, agent_id)
            font = item.font()
            font.setPointSizeF(font.pointSizeF() - 1)
            item.setFont(font)
            self.agent_list.addItem(item)

        if current_id:
            index = next((i for i in range(self.agent_list.count())
                          if self.agent_list.item(i).data(Qt.ItemDataRole.UserRole) == current_id), -1)
            if index >= 0:
                self.agent_list.setCurrentRow(index)
        elif self.agent_list.count() > 0:
            self.agent_list.setCurrentRow(0)

    def refresh_session_list(self, select_id: str | None = None) -> None:
        current_id = select_id
        if current_id is None:
            current_item = self.session_list.currentItem()
            if current_item:
                current_id = current_item.data(Qt.ItemDataRole.UserRole)

        self.session_list.clear()
        sessions = []
        for session_id in self.store.list_sessions():
            meta = session_meta_from_dict(read_yaml(self.store.session_yaml_path(session_id)))
            sessions.append((meta.updated_at, session_id, meta.name))
        sessions.sort(reverse=True)

        for _, session_id, name in sessions:
            meta = session_meta_from_dict(read_yaml(self.store.session_yaml_path(session_id)))
            display_time = meta.updated_at[:16].replace("T", " ") if meta.updated_at else ""
            item = QListWidgetItem()
            item.setText(f"{name}\n  {display_time}")
            item.setData(Qt.ItemDataRole.UserRole, session_id)
            font = item.font()
            font.setPointSizeF(font.pointSizeF() - 1)
            item.setFont(font)
            self.session_list.addItem(item)

        if current_id:
            index = next((i for i in range(self.session_list.count())
                          if self.session_list.item(i).data(Qt.ItemDataRole.UserRole) == current_id), -1)
            if index >= 0:
                self.session_list.setCurrentRow(index)

    # ── Event handlers ──────────────────────────────────────────────────

    def _on_agent_selected(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        agent_id = current.data(Qt.ItemDataRole.UserRole)
        if agent_id:
            self._set_active_tab(0)
            self.agent_panel.load_agent_by_id(agent_id)

    def _on_session_selected(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        session_id = current.data(Qt.ItemDataRole.UserRole)
        if session_id:
            self._set_active_tab(2)
            self.session_panel.load_session_by_id(session_id)

    def _create_agent(self) -> None:
        new_id = self.agent_panel.create_agent()
        self.refresh_agent_list(select_id=new_id)
        self._set_active_tab(0)

    def _create_session(self) -> None:
        self._set_active_tab(2)
        self.session_panel.show_create_page()

    def _on_agents_changed(self) -> None:
        self.refresh_agent_list(select_id=self.agent_panel.current_agent_id)
        self.session_panel.refresh_agents()

    def _on_sessions_changed(self) -> None:
        session_id = None
        if self.session_panel.active_session:
            session_id = self.session_panel.active_session.meta.id
        self.refresh_session_list(select_id=session_id)

    # ── Placeholder page ────────────────────────────────────────────────

    def _build_placeholder(self, text: str) -> QWidget:
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel()
        icon.setFixedSize(48, 48)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3b82f6, stop:1 #8b5cf6);"
            "border-radius: 12px;"
            "color: #f8fafc;"
            "font-size: 20px;"
            "font-weight: bold;"
        )
        icon.setText("T")
        layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        label = QLabel(text)
        label.setStyleSheet("color: #64748b; font-size: 13px; margin-top: 12px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        return frame
