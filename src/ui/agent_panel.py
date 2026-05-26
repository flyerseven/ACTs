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
        layout.setContentsMargins(12, 12, 12, 12)

        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(12, 0, 0, 0)

        self.form_layout = QFormLayout()
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.name_input = QLineEdit()
        self.desc_input = QLineEdit()
        self.system_prompt_input = QPlainTextEdit()
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Mock", "mock")
        self.provider_combo.addItem("OpenAI", "openai")
        self.provider_combo.addItem("OpenAI Compatible", "openai_compat")
        self.provider_combo.addItem("Custom", "custom")
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo", "mock"])
        self.api_key_input = QLineEdit()
        self.base_url_input = QLineEdit()
        self.temperature_input = QDoubleSpinBox()
        self.temperature_input.setRange(0.0, 2.0)
        self.temperature_input.setSingleStep(0.1)
        self.max_tokens_input = QSpinBox()
        self.max_tokens_input.setRange(1, 32000)
        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(1, 600)
        self.skills_input = QLineEdit()

        self.form_layout.addRow("Name", self.name_input)
        self.form_layout.addRow("Description", self.desc_input)
        self.form_layout.addRow("System Prompt", self.system_prompt_input)
        self.form_layout.addRow("Provider", self.provider_combo)
        self.form_layout.addRow("Model", self.model_combo)
        self.form_layout.addRow("API Key Ref", self.api_key_input)
        self.form_layout.addRow("Base URL", self.base_url_input)
        self.form_layout.addRow("Temperature", self.temperature_input)
        self.form_layout.addRow("Max Tokens", self.max_tokens_input)
        self.form_layout.addRow("Timeout (s)", self.timeout_input)
        self.form_layout.addRow("Skills (comma)", self.skills_input)

        detail_layout.addLayout(self.form_layout)

        button_row = QHBoxLayout()
        self.new_button = QPushButton("New Agent")
        self.save_button = QPushButton("Save Agent")
        self.delete_button = QPushButton("Delete Agent")
        button_row.addWidget(self.new_button)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.delete_button)
        detail_layout.addLayout(button_row)

        if show_list:
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.setChildrenCollapsible(False)

            self.list_widget = QListWidget()
            self.list_widget.setMinimumWidth(220)
            splitter.addWidget(self.list_widget)
            splitter.addWidget(detail_widget)
            splitter.setStretchFactor(1, 1)
            layout.addWidget(splitter)

            self.list_widget.currentItemChanged.connect(self.on_select_agent)
        else:
            layout.addWidget(detail_widget)
        self.new_button.clicked.connect(self.create_agent)
        self.save_button.clicked.connect(self.save_agent)
        self.delete_button.clicked.connect(self.delete_agent)

        self.refresh_agents()
        if self.list_widget and self.list_widget.count() == 0:
            self.create_agent()

    def refresh_agents(self, select_id: str | None = None) -> None:
        if not self.list_widget:
            return
        self.list_widget.clear()
        agent_ids = sorted(self.store.list_agents())
        for agent_id in agent_ids:
            item = QListWidgetItem(agent_id)
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
        agent_id = current.text()
        self.load_agent_by_id(agent_id)

    def load_agent_by_id(self, agent_id: str) -> None:
        config_path = self.store.agent_yaml_path(agent_id)
        data = read_yaml(config_path)
        config = agent_config_from_dict(data)
        self.current_agent_id = agent_id
        self.load_form(config)
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
        self.refresh_agents(select_id=config.id)
        self.agents_changed.emit()

    def create_agent(self, emit_signal: bool = True) -> str:
        self.current_agent_id = self.store.new_agent_id()
        config = AgentConfig(id=self.current_agent_id, name=f"Agent {self.current_agent_id}")
        self.load_form(config)
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
        self.refresh_agents()
        self.agents_changed.emit()
