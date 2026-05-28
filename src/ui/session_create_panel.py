from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


@dataclass
class SessionCreateData:
    name: str
    target_id: str
    context_window: int
    compress_every: int
    system_prompt: str
    allow_agent_switch: bool = True


class SessionCreateWidget(QWidget):
    create_requested = pyqtSignal(object)
    cancel_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(0)

        # Page header
        title = QLabel("Create New Session")
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #e0e0e0;")
        layout.addWidget(title)

        subtitle = QLabel("Start a new conversation with an AI agent.")
        subtitle.setStyleSheet("color: #6a6a6a; font-size: 11.5px; margin-top: 2px; margin-bottom: 20px;")
        layout.addWidget(subtitle)

        # Settings card
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet("QFrame#card { background-color: #252526; border: 1px solid #3c3c3c; border-radius: 12px; padding: 0; }")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(0)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setVerticalSpacing(12)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("My Session")

        self.agent_combo = QComboBox()

        self.context_window_input = QSpinBox()
        self.context_window_input.setRange(1, 500)
        self.context_window_input.setValue(100)

        self.compress_every_input = QSpinBox()
        self.compress_every_input.setRange(0, 50)
        self.compress_every_input.setValue(10)

        self.system_prompt_input = QTextEdit()
        self.system_prompt_input.setPlaceholderText("Optional system prompt override...")
        self.system_prompt_input.setFixedHeight(100)

        self.allow_switch_checkbox = QCheckBox("Allow switching Agent during session")
        self.allow_switch_checkbox.setChecked(True)
        self.allow_switch_checkbox.setStyleSheet(
            "QCheckBox { color: #c0c0c0; font-size: 11.5px; spacing: 8px; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
        )

        form.addRow(self._fl("Session Name"), self.name_input)
        form.addRow(self._fl("Agent"), self.agent_combo)
        form.addRow(self._fl(""), self.allow_switch_checkbox)
        form.addRow(self._fl("Context Window"), self.context_window_input)
        form.addRow(self._fl("Compress Every N"), self.compress_every_input)
        form.addRow(self._fl("System Prompt"), self.system_prompt_input)

        card_layout.addLayout(form)
        layout.addWidget(card)

        # Actions
        layout.addSpacing(20)
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("cssClass", "ghost")
        self.create_button = QPushButton("Create Session")
        self.create_button.setProperty("cssClass", "primary")
        action_row.addWidget(self.cancel_button)
        action_row.addStretch(1)
        action_row.addWidget(self.create_button)
        layout.addLayout(action_row)

        layout.addStretch(1)

        self.create_button.clicked.connect(self._on_create)
        self.cancel_button.clicked.connect(self.cancel_requested.emit)

    @staticmethod
    def _fl(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("color: #858585; font-size: 11.5px; min-width: 120px;")
        return label

    def set_agents(self, agents: list[tuple[str, str]]) -> None:
        self.agent_combo.clear()
        for agent_id, label in agents:
            self.agent_combo.addItem(label, agent_id)

    def reset(self) -> None:
        self.name_input.setText("New Session")
        if self.agent_combo.count() > 0:
            self.agent_combo.setCurrentIndex(0)
        self.context_window_input.setValue(100)
        self.compress_every_input.setValue(10)
        self.system_prompt_input.clear()
        self.allow_switch_checkbox.setChecked(True)

    def _on_create(self) -> None:
        name = self.name_input.text().strip() or "New Session"
        target_id = self.agent_combo.currentData() or ""
        data = SessionCreateData(
            name=name,
            target_id=target_id,
            context_window=int(self.context_window_input.value()),
            compress_every=int(self.compress_every_input.value()),
            system_prompt=self.system_prompt_input.toPlainText().strip(),
            allow_agent_switch=self.allow_switch_checkbox.isChecked(),
        )
        self.create_requested.emit(data)
