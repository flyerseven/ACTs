from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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


class SessionCreateWidget(QWidget):
    create_requested = pyqtSignal(object)
    cancel_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        header = QLabel("Create New Session")
        header.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Session name")

        self.agent_combo = QComboBox()

        self.context_window_input = QSpinBox()
        self.context_window_input.setRange(1, 500)
        self.context_window_input.setValue(100)

        self.compress_every_input = QSpinBox()
        self.compress_every_input.setRange(0, 50)
        self.compress_every_input.setValue(10)

        form.addRow("Session Name", self.name_input)
        form.addRow("Agent", self.agent_combo)
        form.addRow("Context Window (messages)", self.context_window_input)
        form.addRow("Compress Every N Turns (0=off)", self.compress_every_input)

        layout.addLayout(form)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.create_button = QPushButton("Create")
        action_row.addWidget(self.cancel_button)
        action_row.addWidget(self.create_button)
        layout.addLayout(action_row)

        self.create_button.clicked.connect(self._on_create)
        self.cancel_button.clicked.connect(self.cancel_requested.emit)

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

    def _on_create(self) -> None:
        name = self.name_input.text().strip() or "New Session"
        target_id = self.agent_combo.currentData() or ""
        data = SessionCreateData(
            name=name,
            target_id=target_id,
            context_window=int(self.context_window_input.value()),
            compress_every=int(self.compress_every_input.value()),
        )
        self.create_requested.emit(data)
