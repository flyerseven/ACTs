from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QScrollArea,
    QFrame,
)

from core.models import AgentConfig, LLMConfig, agent_config_from_dict, agent_config_to_dict, utc_now_iso
from storage.file_store import FileStore
from storage.yaml_io import read_yaml, write_yaml
from security.vault import Vault


class AgentPanel(QWidget):
    agents_changed = pyqtSignal()
    agent_loaded = pyqtSignal(str)

    def __init__(self, store: FileStore, vault: Vault, show_list: bool = True) -> None:
        super().__init__()
        self.store = store
        self.vault = vault
        self.current_agent_id: str | None = None
        self.list_widget: QListWidget | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        detail_widget = QWidget()
        detail_widget.setStyleSheet("background: transparent;")
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(24, 20, 24, 20)
        detail_layout.setSpacing(0)

        # ── Page header ──
        self.page_title = QLabel("Agent Configuration")
        self.page_title.setStyleSheet("font-size: 17px; font-weight: 700; color: #f8fafc;")
        detail_layout.addWidget(self.page_title)

        self.page_subtitle = QLabel("Configure an AI agent with its model, provider, and behavior.")
        self.page_subtitle.setStyleSheet("color: #64748b; font-size: 11.5px; margin-top: 2px; margin-bottom: 20px;")
        detail_layout.addWidget(self.page_subtitle)

        # ── Identity section ──
        detail_layout.addWidget(self._section_label("Identity"))
        detail_layout.addLayout(self._section_divider())

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Code Reviewer")
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Reviews pull requests and suggests improvements")
        self.system_prompt_input = QPlainTextEdit()
        self.system_prompt_input.setPlaceholderText("You are a helpful assistant...")
        self.system_prompt_input.setFixedHeight(90)

        identity_form = QFormLayout()
        identity_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        identity_form.setVerticalSpacing(10)
        identity_form.addRow(self._form_label("Name"), self.name_input)
        identity_form.addRow(self._form_label("Description"), self.desc_input)
        identity_form.addRow(self._form_label("System Prompt"), self.system_prompt_input)
        detail_layout.addLayout(identity_form)

        # ── Model section ──
        detail_layout.addSpacing(18)
        detail_layout.addWidget(self._section_label("Model"))
        detail_layout.addLayout(self._section_divider())

        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Mock", "mock")
        self.provider_combo.addItem("OpenAI", "openai")
        self.provider_combo.addItem("OpenAI Compatible", "openai_compat")
        self.provider_combo.addItem("Custom", "custom")
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo", "mock"])
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("vault:openai or a raw key")
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.openai.com/v1")

        model_form = QFormLayout()
        model_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        model_form.setVerticalSpacing(10)
        model_form.addRow(self._form_label("Provider"), self.provider_combo)
        model_form.addRow(self._form_label("Model"), self.model_combo)
        model_form.addRow(self._form_label("API Key"), self.api_key_input)
        model_form.addRow(self._form_label("Base URL"), self.base_url_input)
        detail_layout.addLayout(model_form)

        # ── Parameters section ──
        detail_layout.addSpacing(18)
        detail_layout.addWidget(self._section_label("Parameters"))
        detail_layout.addLayout(self._section_divider())

        self.temperature_input = QDoubleSpinBox()
        self.temperature_input.setRange(0.0, 2.0)
        self.temperature_input.setSingleStep(0.1)
        self.temperature_input.setValue(0.7)
        self.max_tokens_input = QSpinBox()
        self.max_tokens_input.setRange(1, 32000)
        self.max_tokens_input.setValue(4096)
        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(1, 600)
        self.timeout_input.setValue(30)
        self.skills_input = QLineEdit()
        self.skills_input.setPlaceholderText("coding, review, summarization")

        params_form = QFormLayout()
        params_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        params_form.setVerticalSpacing(10)
        params_form.addRow(self._form_label("Temperature"), self.temperature_input)
        params_form.addRow(self._form_label("Max Tokens"), self.max_tokens_input)
        params_form.addRow(self._form_label("Timeout (s)"), self.timeout_input)
        params_form.addRow(self._form_label("Skills"), self.skills_input)
        detail_layout.addLayout(params_form)

        # ── Actions ──
        detail_layout.addSpacing(20)
        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self.new_button = QPushButton("New Agent")
        self.new_button.setProperty("cssClass", "ghost")

        self.save_button = QPushButton("Save Agent")
        self.save_button.setProperty("cssClass", "primary")

        self.delete_button = QPushButton("Delete Agent")
        self.delete_button.setProperty("cssClass", "danger")

        button_row.addWidget(self.new_button)
        button_row.addStretch(1)
        button_row.addWidget(self.delete_button)
        button_row.addWidget(self.save_button)
        detail_layout.addLayout(button_row)

        detail_layout.addStretch(1)

        scroll.setWidget(detail_widget)

        if show_list:
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.setChildrenCollapsible(False)

            self.list_widget = QListWidget()
            self.list_widget.setMinimumWidth(200)
            self.list_widget.setMaximumWidth(260)
            splitter.addWidget(self.list_widget)
            splitter.addWidget(scroll)
            splitter.setStretchFactor(1, 1)
            layout.addWidget(splitter)

            self.list_widget.currentItemChanged.connect(self.on_select_agent)
        else:
            layout.addWidget(scroll)

        self.new_button.clicked.connect(self.create_agent)
        self.save_button.clicked.connect(self.save_agent)
        self.delete_button.clicked.connect(self.delete_agent)

        self.refresh_agents()
        if self.list_widget and self.list_widget.count() == 0:
            self.create_agent()

    # ── Section helpers ─────────────────────────────────────────────────

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("sectionLabel")
        return label

    @staticmethod
    def _section_divider() -> QHBoxLayout:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #1e293b; max-height: 1px; border: none; margin: 4px 0 8px 0;")
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line)
        return layout

    @staticmethod
    def _form_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("color: #94a3b8; font-size: 11.5px; min-width: 100px;")
        return label

    # ── Agent CRUD ──────────────────────────────────────────────────────

    def refresh_agents(self, select_id: str | None = None) -> None:
        if not self.list_widget:
            return
        self.list_widget.clear()
        agent_ids = sorted(self.store.list_agents())
        for agent_id in agent_ids:
            config = agent_config_from_dict(read_yaml(self.store.agent_yaml_path(agent_id)))
            item = QListWidgetItem()
            item.setText(f"{config.name}\n  {config.model.name}")
            item.setData(Qt.ItemDataRole.UserRole, agent_id)
            self.list_widget.addItem(item)
        if not agent_ids:
            return
        if select_id in agent_ids:
            self.list_widget.setCurrentRow(agent_ids.index(select_id))
        else:
            self.list_widget.setCurrentRow(0)

    def on_select_agent(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        agent_id = current.data(Qt.ItemDataRole.UserRole) or current.text()
        self.load_agent_by_id(agent_id)

    def load_agent_by_id(self, agent_id: str) -> None:
        config_path = self.store.agent_yaml_path(agent_id)
        data = read_yaml(config_path)
        config = agent_config_from_dict(data)
        self.current_agent_id = agent_id
        self.load_form(config)
        self.page_title.setText(config.name or "Agent Configuration")
        self.agent_loaded.emit(agent_id)

    def load_form(self, config: AgentConfig) -> None:
        self.name_input.setText(config.name)
        self.desc_input.setText(config.description)
        self.system_prompt_input.setPlainText(config.system_prompt)
        index = self.provider_combo.findData(config.model.provider)
        self.provider_combo.setCurrentIndex(index if index >= 0 else 0)
        self.model_combo.setCurrentText(config.model.name)
        self.api_key_input.setText(config.model.api_key_ref)
        self.base_url_input.setText(config.model.base_url)
        self.temperature_input.setValue(config.model.temperature)
        self.max_tokens_input.setValue(config.model.max_tokens)
        self.timeout_input.setValue(config.model.timeout_seconds)
        self.skills_input.setText(", ".join(config.skills))

    def read_form(self) -> AgentConfig:
        agent_id = self.current_agent_id or self.store.new_agent_id()
        model = LLMConfig(
            provider=self.provider_combo.currentData() or "mock",
            name=self.model_combo.currentText().strip() or "mock",
            temperature=float(self.temperature_input.value()),
            max_tokens=int(self.max_tokens_input.value()),
            base_url=self.base_url_input.text().strip() or "https://api.openai.com/v1",
            api_key_ref=self.api_key_input.text().strip(),
            timeout_seconds=int(self.timeout_input.value()),
        )
        skills = [s.strip() for s in self.skills_input.text().split(",") if s.strip()]
        return AgentConfig(
            id=agent_id,
            name=self.name_input.text().strip() or f"Agent {agent_id}",
            description=self.desc_input.text().strip(),
            system_prompt=self.system_prompt_input.toPlainText().strip(),
            model=model,
            skills=skills,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )

    def save_agent(self) -> None:
        config = self.read_form()
        self.current_agent_id = config.id
        write_yaml(self.store.agent_yaml_path(config.id), agent_config_to_dict(config))
        self.page_title.setText(config.name)
        self.refresh_agents(select_id=config.id)
        self.agents_changed.emit()

    def create_agent(self, emit_signal: bool = True) -> str:
        self.current_agent_id = self.store.new_agent_id()
        config = AgentConfig(id=self.current_agent_id, name=f"Agent {self.current_agent_id}")
        self.load_form(config)
        self.page_title.setText(config.name)
        write_yaml(self.store.agent_yaml_path(config.id), agent_config_to_dict(config))
        self.refresh_agents(select_id=config.id)
        if emit_signal:
            self.agents_changed.emit()
        return config.id

    def delete_agent(self) -> None:
        if not self.current_agent_id:
            return
        agent_dir = self.store.agent_dir(self.current_agent_id)
        if agent_dir.exists():
            for path in agent_dir.rglob("*"):
                if path.is_file():
                    path.unlink()
            for path in sorted(agent_dir.rglob("*"), reverse=True):
                if path.is_dir():
                    path.rmdir()
            agent_dir.rmdir()
        self.current_agent_id = None
        self.page_title.setText("Agent Configuration")
        self.refresh_agents()
        self.agents_changed.emit()
