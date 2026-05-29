"""Dialog for importing skills by pasting code snippets (OpenAI Function JSON
or LangChain BaseTool Python code)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.skill_import import (
    LangChainToolAdapter,
    OpenAIFunctionAdapter,
    YamlSkillAdapter,
    detect_format,
)


class SkillImportDialog(QDialog):
    """Modal dialog for pasting code to import as a skill."""

    FORMAT_LABELS = {
        "openai_function": "OpenAI Function / Tool (JSON)",
        "langchain_tool": "LangChain BaseTool (Python)",
        "yaml_skill": "Custom YAML Skill",
        "unknown": "Unknown — will try auto-detect",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Skill from Code")
        self.resize(700, 560)
        self.setMinimumSize(500, 400)
        self.setStyleSheet("QDialog { background-color: #252526; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ── Header ──
        header = QLabel("Paste an OpenAI Function JSON or LangChain Tool Python class.")
        header.setStyleSheet("color: #858585; font-size: 11px;")
        header.setWordWrap(True)
        layout.addWidget(header)

        # ── Format selector row ──
        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(8)

        fmt_label = QLabel("Format:")
        fmt_label.setStyleSheet("color: #cccccc; font-size: 12px;")
        fmt_row.addWidget(fmt_label)

        self.format_combo = QComboBox()
        self.format_combo.addItems([
            self.FORMAT_LABELS["unknown"],
            self.FORMAT_LABELS["openai_function"],
            self.FORMAT_LABELS["langchain_tool"],
            self.FORMAT_LABELS["yaml_skill"],
        ])
        self.format_combo.setStyleSheet(
            "QComboBox {"
            "  background-color: #3c3c3c; border: 1px solid #3c3c3c; border-radius: 6px;"
            "  padding: 4px 10px; color: #cccccc; font-size: 12px;"
            "}"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView {"
            "  background-color: #333333; color: #cccccc; selection-background-color: #094771;"
            "}"
        )
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        fmt_row.addWidget(self.format_combo, stretch=1)

        self.detect_btn = QPushButton("Auto-detect")
        self.detect_btn.setFixedHeight(28)
        self.detect_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #3c3c3c; border: 1px solid #555; border-radius: 6px;"
            "  color: #cccccc; padding: 2px 12px; font-size: 11px;"
            "}"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        self.detect_btn.clicked.connect(self._auto_detect)
        fmt_row.addWidget(self.detect_btn)

        layout.addLayout(fmt_row)

        # ── Code input ──
        self.code_edit = QPlainTextEdit()
        self.code_edit.setPlaceholderText(
            'Paste your code here...\n\n'
            'OpenAI Function example:\n'
            '  {"name": "get_weather", "description": "Get weather", "parameters": {...}}\n\n'
            'LangChain Tool example:\n'
            '  from langchain.tools import BaseTool\n'
            '  class WeatherTool(BaseTool):\n'
            '      name = "get_weather"\n'
            '      description = "Get weather"\n'
            '      def _run(self, location: str) -> str: ...'
        )
        self.code_edit.setStyleSheet(
            "QPlainTextEdit {"
            "  background-color: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 8px;"
            "  color: #cccccc; font-size: 12px; font-family: 'Consolas', 'Courier New', monospace;"
            "  padding: 8px;"
            "}"
            "QPlainTextEdit:focus { border-color: #007acc; }"
        )
        layout.addWidget(self.code_edit, stretch=2)

        # ── Preview section ──
        preview_label = QLabel("Preview:")
        preview_label.setStyleSheet("color: #cccccc; font-size: 12px; font-weight: 600;")
        layout.addWidget(preview_label)

        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setPlaceholderText("Paste code and click 'Preview' to see the parsed skill...")
        self.preview_edit.setStyleSheet(
            "QPlainTextEdit {"
            "  background-color: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 8px;"
            "  color: #858585; font-size: 11px; font-family: 'Consolas', 'Courier New', monospace;"
            "  padding: 8px;"
            "}"
        )
        layout.addWidget(self.preview_edit, stretch=1)

        # ── Bottom buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.preview_btn = QPushButton("Preview")
        self.preview_btn.setFixedHeight(30)
        self.preview_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #3c3c3c; border: 1px solid #555; border-radius: 6px;"
            "  color: #cccccc; padding: 4px 16px; font-size: 12px;"
            "}"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        self.preview_btn.clicked.connect(self._preview)
        btn_row.addWidget(self.preview_btn)

        btn_row.addStretch(1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        button_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            "QPushButton {"
            "  background-color: #007acc; border: none; border-radius: 6px;"
            "  color: #e0e0e0; padding: 4px 20px; font-size: 12px; font-weight: 600;"
            "}"
            "QPushButton:hover { background-color: #0098ff; }"
        )
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            "QPushButton {"
            "  background-color: #3c3c3c; border: none; border-radius: 6px;"
            "  color: #cccccc; padding: 4px 16px; font-size: 12px;"
            "}"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        btn_row.addWidget(button_box)

        layout.addLayout(btn_row)

        self._parsed_skill = None

    # ── Public ─────────────────────────────────────────────────────────────

    def get_skill(self):
        """Return the parsed Skill after dialog is accepted."""
        return self._parsed_skill

    def get_source(self) -> str:
        return self.code_edit.toPlainText().strip()

    # ── Internals ──────────────────────────────────────────────────────────

    def _get_selected_format(self) -> str:
        idx = self.format_combo.currentIndex()
        if idx == 0:
            return ""  # auto-detect
        elif idx == 1:
            return "openai_function"
        elif idx == 2:
            return "langchain_tool"
        return "yaml_skill"

    def _on_format_changed(self, _index: int) -> None:
        self._parsed_skill = None

    def _auto_detect(self) -> None:
        source = self.get_source()
        if not source:
            return
        fmt = detect_format(source)
        label_map = {
            "openai_function": 1,
            "langchain_tool": 2,
            "yaml_skill": 3,
        }
        idx = label_map.get(fmt, 0)
        self.format_combo.setCurrentIndex(idx)

    def _preview(self) -> None:
        source = self.get_source()
        if not source:
            self.preview_edit.setPlainText("No code pasted.")
            return

        manual_format = self._get_selected_format()
        adapter = None

        if manual_format == "openai_function":
            adapter = OpenAIFunctionAdapter()
        elif manual_format == "langchain_tool":
            adapter = LangChainToolAdapter()
        elif manual_format == "yaml_skill":
            adapter = YamlSkillAdapter()
        else:
            # Auto-detect
            for a in (OpenAIFunctionAdapter(), LangChainToolAdapter(), YamlSkillAdapter()):
                if a.detect(source):
                    adapter = a
                    break

        if adapter is None:
            self.preview_edit.setPlainText("Could not detect or parse the pasted code.\nCheck the format and try again.")
            return

        try:
            skill = adapter.parse(source)
            self._parsed_skill = skill
            lines = [
                f"name: {skill.name}",
                f"description: {skill.description}",
                f"type: {skill.type}",
                f"source_format: {skill.source_format}",
                f"",
                f"--- Prompt Extension ---",
                skill.prompt_extension,
            ]
            self.preview_edit.setPlainText("\n".join(lines))
            # Show which adapter was used
            idx_map = {"openai_function": 1, "langchain_tool": 2, "yaml_skill": 3}
            self.format_combo.setCurrentIndex(idx_map.get(skill.source_format, 0))
        except Exception as e:
            self.preview_edit.setPlainText(f"Parse error: {e}")

    def accept(self) -> None:
        source = self.get_source()
        if not source:
            self.reject()
            return

        if self._parsed_skill is None:
            self._preview()

        if self._parsed_skill is not None:
            super().accept()
        else:
            self.preview_edit.setPlainText("Cannot import. Click 'Preview' to check for errors.")
