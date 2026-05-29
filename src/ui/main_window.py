from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.agent_panel import AgentPanel
from ui.session_panel import SessionPanel
from ui.session_tree_widget import SessionTreeWidget
from ui.skill_manager import SkillManager
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
        wrapper_layout.addWidget(self._build_menu_bar())

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
        self.session_panel.session_edited.connect(self._on_session_edited)

        self._warmup_webengine()

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
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #007acc, stop:1 #0098ff);"
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

    # ── Menu bar ─────────────────────────────────────────────────────────

    def _build_menu_bar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            "QFrame { background-color: #1e1e1e; border-bottom: 1px solid #3c3c3c; }"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(0)

        layout.addWidget(self._menu_button("Skill", [
            ("Manage Skills", self._open_skill_manager),
        ]))

        layout.addStretch(1)
        return bar

    def _menu_button(self, title: str, items: list[tuple[str, object]]) -> QPushButton:
        btn = QPushButton(title)
        btn.setFlat(True)
        btn.setFixedHeight(26)
        btn.setStyleSheet(
            "QPushButton { color: #cccccc; font-size: 11.5px; padding: 2px 10px;"
            "  background: transparent; border: none; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3c3c3c; }"
            "QPushButton:pressed { background-color: #007acc; }"
        )

        menu = QMenu(btn)
        menu.setStyleSheet(
            "QMenu { background-color: #2d2d2d; color: #cccccc; border: 1px solid #3c3c3c; }"
            "QMenu::item { padding: 5px 24px; }"
            "QMenu::item:selected { background-color: #007acc; }"
            "QMenu::separator { height: 1px; background: #3c3c3c; margin: 4px 8px; }"
        )

        for label, handler in items:
            action = menu.addAction(label)
            if callable(handler):
                action.triggered.connect(handler)

        btn.setMenu(menu)
        return btn

    def _open_skill_manager(self) -> None:
        dlg = SkillManager(self)
        dlg.exec()

    # ── WebEngine pre-warm ──────────────────────────────────────────────

    def _warmup_webengine(self) -> None:
        """Create a hidden QWebEngineView so Chromium process + GPU process
        start before the window is shown.  Without this, the first visible
        QWebEngineView instantiation steals the rendering context from the
        window, causing a full-window white flash."""
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            self._web_warmup = QWebEngineView(self)
            self._web_warmup.setVisible(False)
            self._web_warmup.setHtml("<html><body style='background:#252526;'></body></html>")
        except Exception:
            pass

    # ── Sidebar ─────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setMinimumWidth(220)
        sidebar.setMaximumWidth(280)
        sidebar.setStyleSheet("QWidget { background-color: #252526; }")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Tab toggle row — pill-style segmented control look
        tab_container = QWidget()
        tab_container.setFixedHeight(36)
        tab_container.setStyleSheet(
            "QWidget { background-color: #2d2d2d; border-radius: 10px; }"
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

        self.session_list = SessionTreeWidget(self.store)
        self.session_add_button = QPushButton("+ New Session")

        self.group_filter_combo = QComboBox()
        self.group_filter_combo.setFixedHeight(32)

        session_panel_wrapper = QWidget()
        sp_layout = QVBoxLayout(session_panel_wrapper)
        sp_layout.setContentsMargins(0, 0, 0, 0)
        sp_layout.setSpacing(6)
        sp_layout.addWidget(self.group_filter_combo)
        sp_layout.addWidget(self.session_list, stretch=1)
        sp_layout.addWidget(self.session_add_button)
        self.sidebar_stack.addWidget(session_panel_wrapper)

        layout.addWidget(self.sidebar_stack, stretch=1)

        self.tab_group.buttonClicked.connect(lambda btn: self._set_active_tab(self.tab_group.id(btn)))
        self.agent_list.currentItemChanged.connect(self._on_agent_selected)
        self.session_list.session_selected.connect(self._on_session_selected_from_tree)
        self.session_list.session_rename_requested.connect(self._rename_session)
        self.session_list.session_edit_requested.connect(self._edit_session_params)
        self.session_list.session_delete_requested.connect(self._delete_session)
        self.session_list.group_renamed.connect(lambda old, new: self.refresh_session_list())
        self.session_list.group_deleted.connect(lambda g: self.refresh_session_list())
        self.session_list.session_moved.connect(lambda sid, g: self.refresh_session_list())
        self.group_filter_combo.currentIndexChanged.connect(self._on_group_filter_changed)
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
        if select_id is None:
            select_id = self.session_list.get_selected_session_id()

        self.session_list.load_sessions()

        if select_id:
            self.session_list.set_selected_session(select_id)

        current_filter = self.group_filter_combo.currentData()
        self.group_filter_combo.blockSignals(True)
        self.group_filter_combo.clear()
        self.group_filter_combo.addItem("全部", None)
        for group_name, count in self.session_list.get_all_groups():
            label = f"{group_name or '未分组'} ({count})"
            self.group_filter_combo.addItem(label, group_name)
        if current_filter is not None:
            idx = self.group_filter_combo.findData(current_filter)
            if idx >= 0:
                self.group_filter_combo.setCurrentIndex(idx)
        self.group_filter_combo.blockSignals(False)

        self.session_list.filter_by_group(self.group_filter_combo.currentData())

    # ── Event handlers ──────────────────────────────────────────────────

    def _on_agent_selected(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        agent_id = current.data(Qt.ItemDataRole.UserRole)
        if agent_id:
            self._set_active_tab(0)
            self.agent_panel.load_agent_by_id(agent_id)

    def _on_session_selected_from_tree(self, session_id: str) -> None:
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

    def _on_session_edited(self, session_id: str) -> None:
        self.refresh_session_list(select_id=session_id)

    # ── Group filter ───────────────────────────────────────────────────

    def _on_group_filter_changed(self, index: int) -> None:
        group_name = self.group_filter_combo.currentData()
        self.session_list.filter_by_group(group_name)

    def _rename_session(self, session_id: str) -> None:
        from storage.yaml_io import read_yaml
        meta = session_meta_from_dict(read_yaml(self.store.session_yaml_path(session_id)))
        new_name, ok = QInputDialog.getText(
            self, "Rename Session", "New name:", QLineEdit.EchoMode.Normal, meta.name,
        )
        if ok and new_name.strip():
            self.session_panel.edit_session_meta(session_id, name=new_name.strip())

    def _edit_session_params(self, session_id: str) -> None:
        from storage.yaml_io import read_yaml
        meta = session_meta_from_dict(read_yaml(self.store.session_yaml_path(session_id)))
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Session Parameters")
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet(
            "QDialog { background-color: #252526; border: 1px solid #3c3c3c; border-radius: 12px; }"
            "QLabel { color: #858585; font-size: 11.5px; }"
            "QLineEdit, QSpinBox, QTextEdit {"
            "  background-color: #3c3c3c; border: 1px solid #3c3c3c; border-radius: 6px;"
            "  padding: 6px 10px; color: #cccccc; font-size: 12px; }"
            "QTextEdit { min-height: 60px; }"
            "QPushButton {"
            "  background-color: #007acc; border: none; border-radius: 6px;"
            "  color: #e0e0e0; padding: 6px 16px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background-color: #0098ff; }"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setVerticalSpacing(10)

        name_input = QLineEdit(meta.name)
        form.addRow(QLabel("Name"), name_input)

        group_input = QLineEdit(meta.group)
        group_input.setPlaceholderText("e.g. Work, Personal, Experiment")
        form.addRow(QLabel("Group"), group_input)

        sys_prompt_input = QTextEdit()
        sys_prompt_input.setPlainText(meta.system_prompt)
        sys_prompt_input.setPlaceholderText("Optional system prompt override...")
        sys_prompt_input.setFixedHeight(80)
        form.addRow(QLabel("System Prompt"), sys_prompt_input)

        ctx_input = QSpinBox()
        ctx_input.setRange(1, 500)
        ctx_input.setValue(meta.context_keep_last)
        form.addRow(QLabel("Context Window"), ctx_input)

        compress_input = QSpinBox()
        compress_input.setRange(0, 50)
        compress_input.setValue(meta.compression_interval)
        form.addRow(QLabel("Compress Every N"), compress_input)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self.session_panel.edit_session_meta(
            session_id,
            name=name_input.text().strip() or meta.name,
            group=group_input.text().strip(),
            system_prompt=sys_prompt_input.toPlainText().strip(),
            context_keep_last=ctx_input.value(),
            compression_interval=compress_input.value(),
        )

    def _delete_session(self, session_id: str) -> None:
        from storage.yaml_io import read_yaml
        meta = session_meta_from_dict(read_yaml(self.store.session_yaml_path(session_id)))
        reply = QMessageBox.question(
            self,
            "Delete Session",
            f"Delete session \"{meta.name}\"?\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.session_panel.delete_session(session_id)

    # ── Placeholder page ────────────────────────────────────────────────

    def _build_placeholder(self, text: str) -> QWidget:
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel()
        icon.setFixedSize(48, 48)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #007acc, stop:1 #0098ff);"
            "border-radius: 12px;"
            "color: #e0e0e0;"
            "font-size: 20px;"
            "font-weight: bold;"
        )
        icon.setText("T")
        layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        label = QLabel(text)
        label.setStyleSheet("color: #6a6a6a; font-size: 13px; margin-top: 12px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        return frame
