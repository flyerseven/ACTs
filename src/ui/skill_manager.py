from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QBrush, QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.skill import Skill, discover_skills, write_skill_md
from core.skill_import import detect_and_import
from ui.skill_import_dialog import SkillImportDialog

# Resolve the skills/ directory relative to the project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BUILTIN_SKILLS_DIR = _PROJECT_ROOT / "skills"


class SkillManager(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Skill Manager")
        self.resize(640, 480)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("QDialog { background-color: #252526; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ── Search bar ──
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search skills...")
        self.search_input.setFixedHeight(32)
        self.search_input.setStyleSheet(
            "QLineEdit {"
            "  background-color: #3c3c3c; border: 1px solid #3c3c3c; border-radius: 8px;"
            "  padding: 4px 12px; color: #cccccc; font-size: 12px;"
            "}"
            "QLineEdit:focus { border-color: #007acc; }"
        )
        self.search_input.textChanged.connect(self._on_search)
        layout.addWidget(self.search_input)

        # ── Toolbar ──
        toolbar = QFrame()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)

        self.import_button = QPushButton("Import File")
        self.import_button.setFixedHeight(30)
        self.import_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #007acc; border: none; border-radius: 6px;"
            "  color: #e0e0e0; padding: 4px 16px; font-size: 12px; font-weight: 600;"
            "}"
            "QPushButton:hover { background-color: #0098ff; }"
        )
        self.import_button.clicked.connect(self._import_file)
        toolbar_layout.addWidget(self.import_button)

        self.paste_import_button = QPushButton("Paste Import")
        self.paste_import_button.setFixedHeight(30)
        self.paste_import_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #3c3c3c; border: 1px solid #555; border-radius: 6px;"
            "  color: #cccccc; padding: 4px 16px; font-size: 12px;"
            "}"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        self.paste_import_button.clicked.connect(self._paste_import)
        toolbar_layout.addWidget(self.paste_import_button)
        toolbar_layout.addStretch(1)

        layout.addWidget(toolbar)

        # ── Skill list ──
        self.skill_list = QListWidget()
        self.skill_list.setStyleSheet(
            "QListWidget {"
            "  background-color: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 8px;"
            "  color: #cccccc; font-size: 12px;"
            "}"
            "QListWidget::item {"
            "  padding: 8px 12px; border-bottom: 1px solid #2d2d2d;"
            "}"
            "QListWidget::item:selected {"
            "  background-color: #094771;"
            "}"
            "QListWidget::item:hover {"
            "  background-color: #2a2d2e;"
            "}"
        )
        layout.addWidget(self.skill_list, stretch=1)

        # ── Store ──
        self._skills: list[tuple[Path, Skill]] = []  # (path, Skill)

        # Load built-in + imported skills
        self._skills.extend(discover_skills(_BUILTIN_SKILLS_DIR))
        self._refresh_list()

    # ── Import ─────────────────────────────────────────────────────────────

    def _import_file(self) -> None:
        """Import skills from files (JSON, Python, YAML)."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Skills from Files",
            "",
            "Skill Files (*.json *.py *.yaml *.yml);;All Files (*)",
        )
        if not files:
            return

        imported = 0
        errors: list[str] = []
        for filepath in files:
            path = Path(filepath)
            try:
                source = path.read_text(encoding="utf-8")
                if detect_and_import(source, _BUILTIN_SKILLS_DIR) is None:
                    errors.append(f"{path.name}: format not recognized")
                else:
                    imported += 1
            except Exception as e:
                errors.append(f"{path.name}: {e}")

        # Reload skills
        self._skills = discover_skills(_BUILTIN_SKILLS_DIR)
        self._refresh_list()

        if imported > 0:
            self._show_message(
                "Import Complete",
                f"Successfully imported {imported} skill(s).",
                QMessageBox.Icon.Information,
            )
        if errors:
            self._show_message(
                "Import Errors",
                f"Failed to import {len(errors)} file(s):\n\n" + "\n".join(errors),
                QMessageBox.Icon.Warning,
            )

    def _paste_import(self) -> None:
        """Open the code paste import dialog."""
        dlg = SkillImportDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        skill = dlg.get_skill()
        if skill is None:
            return

        # Save to skills/ directory
        target_dir = _BUILTIN_SKILLS_DIR / _safe_dirname(skill.name)
        if target_dir.exists():
            reply = QMessageBox.question(
                self,
                "Overwrite?",
                f"A skill named '{skill.name}' already exists. Overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            write_skill_md(skill, target_dir)
        except Exception as e:
            self._show_message("Save Error", f"Failed to save skill: {e}", QMessageBox.Icon.Critical)
            return

        # Reload
        self._skills = discover_skills(_BUILTIN_SKILLS_DIR)
        self._refresh_list()
        self._show_message("Import Complete", f"Skill '{skill.name}' imported successfully.", QMessageBox.Icon.Information)

    # ── List ────────────────────────────────────────────────────────────────

    def _refresh_list(self, filter_text: str = "") -> None:
        self.skill_list.clear()
        text = filter_text.lower()
        for path, skill in self._skills:
            if text and text not in skill.name.lower() and text not in skill.description.lower():
                continue
            source_tag = f" [{skill.source_format}]" if skill.source_format else ""
            label = f"{skill.name}{source_tag}\n  {skill.description}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.skill_list.addItem(item)

        if self.skill_list.count() == 0:
            empty_item = QListWidgetItem("No skills found.")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.skill_list.addItem(empty_item)

    def _on_search(self, text: str) -> None:
        self._refresh_list(text)

    @staticmethod
    def _show_message(title: str, text: str, icon: QMessageBox.Icon) -> None:
        box = QMessageBox()
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(icon)
        box.setStyleSheet(
            "QMessageBox { background-color: #252526; color: #cccccc; }"
            "QPushButton {"
            "  background-color: #007acc; border: none; border-radius: 6px;"
            "  color: #e0e0e0; padding: 4px 16px; font-size: 12px;"
            "}"
        )
        box.exec()


def _safe_dirname(name: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-").lower() or "unnamed-skill"


# ═══════════════════════════════════════════════════════════════════════════
# SkillSelector — pick skills for an Agent
# ═══════════════════════════════════════════════════════════════════════════


class SkillSelector(QDialog):
    """Dialog for selecting skills to enable/disable per agent. Same layout as
    SkillManager but each skill row has a toggle switch instead of plain text."""

    def __init__(self, selected_skills: list[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Skills")
        self.resize(640, 480)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("QDialog { background-color: #252526; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ── Search bar ──
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search skills...")
        self.search_input.setFixedHeight(32)
        self.search_input.setStyleSheet(
            "QLineEdit {"
            "  background-color: #3c3c3c; border: 1px solid #3c3c3c; border-radius: 8px;"
            "  padding: 4px 12px; color: #cccccc; font-size: 12px;"
            "}"
            "QLineEdit:focus { border-color: #007acc; }"
        )
        self.search_input.textChanged.connect(self._on_search)
        layout.addWidget(self.search_input)

        # ── Toolbar ──
        toolbar = QFrame()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)

        self.import_button = QPushButton("Import File")
        self.import_button.setFixedHeight(30)
        self.import_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #007acc; border: none; border-radius: 6px;"
            "  color: #e0e0e0; padding: 4px 16px; font-size: 12px; font-weight: 600;"
            "}"
            "QPushButton:hover { background-color: #0098ff; }"
        )
        self.import_button.clicked.connect(self._import_file)
        toolbar_layout.addWidget(self.import_button)

        self.paste_import_button = QPushButton("Paste Import")
        self.paste_import_button.setFixedHeight(30)
        self.paste_import_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #3c3c3c; border: 1px solid #555; border-radius: 6px;"
            "  color: #cccccc; padding: 4px 16px; font-size: 12px;"
            "}"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        self.paste_import_button.clicked.connect(self._paste_import)
        toolbar_layout.addWidget(self.paste_import_button)
        toolbar_layout.addStretch(1)

        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: #858585; font-size: 11px;")
        toolbar_layout.addWidget(self.count_label)

        layout.addWidget(toolbar)

        # ── Scrollable skill list with toggles ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch(1)

        scroll.setWidget(self._list_container)
        layout.addWidget(scroll, stretch=1)

        # ── Bottom buttons ──
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.setStyleSheet(
            "QPushButton {"
            "  background-color: #007acc; border: none; border-radius: 6px;"
            "  color: #e0e0e0; padding: 4px 16px; font-size: 12px; font-weight: 600;"
            "}"
            "QPushButton:hover { background-color: #0098ff; }"
        )
        layout.addWidget(button_box)

        # ── Store ──
        self._skills: list[tuple[Path, Skill]] = []
        self._toggles: dict[str, QCheckBox] = {}
        self._selected: set[str] = set(selected_skills or [])

        # Load built-in + imported skills
        self._skills.extend(discover_skills(_BUILTIN_SKILLS_DIR))
        self._refresh_list()

    # ── Public API ────────────────────────────────────────────────────────

    def selected_skills(self) -> list[str]:
        return sorted(name for name, cb in self._toggles.items() if cb.isChecked())

    # ── Import ─────────────────────────────────────────────────────────────

    def _import_file(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Skills from Files",
            "",
            "Skill Files (*.json *.py *.yaml *.yml);;All Files (*)",
        )
        if not files:
            return

        imported = 0
        for filepath in files:
            path = Path(filepath)
            try:
                source = path.read_text(encoding="utf-8")
                if detect_and_import(source, _BUILTIN_SKILLS_DIR) is not None:
                    imported += 1
            except Exception:
                pass

        if imported > 0:
            self._skills = discover_skills(_BUILTIN_SKILLS_DIR)
            self._refresh_list()

    def _paste_import(self) -> None:
        dlg = SkillImportDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        skill = dlg.get_skill()
        if skill is None:
            return

        target_dir = _BUILTIN_SKILLS_DIR / _safe_dirname(skill.name)
        if target_dir.exists():
            reply = QMessageBox.question(
                self,
                "Overwrite?",
                f"A skill named '{skill.name}' already exists. Overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            write_skill_md(skill, target_dir)
        except Exception:
            return

        self._skills = discover_skills(_BUILTIN_SKILLS_DIR)
        self._refresh_list()

    # ── Internals ─────────────────────────────────────────────────────────

    def _refresh_list(self, filter_text: str = "") -> None:
        # Clear existing rows (but keep the stretch at the end)
        while self._list_layout.count() > 0:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.spacerItem():
                self._list_layout.removeItem(item)

        self._toggles.clear()
        text = filter_text.lower()

        visible_count = 0
        for path, skill in self._skills:
            if text and text not in skill.name.lower() and text not in skill.description.lower():
                continue
            visible_count += 1
            row = self._create_skill_row(skill)
            self._list_layout.addWidget(row)

        self._list_layout.addStretch(1)
        self.count_label.setText(f"{visible_count} skill{'s' if visible_count != 1 else ''}")

    def _create_skill_row(self, skill: Skill) -> QFrame:
        row = QFrame()
        row.setStyleSheet(
            "QFrame {"
            "  background-color: #1e1e1e; border: 1px solid #2d2d2d; border-radius: 8px;"
            "}"
            "QFrame:hover { background-color: #2a2d2e; }"
        )
        row.setFixedHeight(56)

        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(12, 8, 12, 8)
        row_layout.setSpacing(12)

        # Skill info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = QLabel(skill.name)
        name_label.setStyleSheet("color: #e0e0e0; font-size: 12px; font-weight: 600; border: none;")

        desc_label = QLabel(skill.description)
        desc_label.setStyleSheet("color: #858585; font-size: 11px; border: none;")
        desc_label.setWordWrap(True)

        info_layout.addWidget(name_label)
        info_layout.addWidget(desc_label)
        row_layout.addLayout(info_layout, stretch=1)

        # Toggle switch
        toggle = ToggleSwitch()
        toggle.setChecked(skill.name in self._selected)
        toggle.setFixedSize(40, 22)
        toggle.toggled.connect(lambda checked, name=skill.name: self._on_toggle(name, checked))

        self._toggles[skill.name] = toggle
        # Wrap toggle to keep it top-aligned
        toggle_wrapper = QVBoxLayout()
        toggle_wrapper.setContentsMargins(0, 0, 0, 0)
        toggle_wrapper.addWidget(toggle)
        toggle_wrapper.addStretch(1)
        row_layout.addLayout(toggle_wrapper)

        return row

    def _on_toggle(self, name: str, checked: bool) -> None:
        if checked:
            self._selected.add(name)
        else:
            self._selected.discard(name)

    def _on_search(self, text: str) -> None:
        self._refresh_list(text)

    # Override accept to capture selected skills
    def accept(self) -> None:
        super().accept()


class ToggleSwitch(QCheckBox):
    """Custom toggle switch that paints as a sliding pill."""

    TRACK_ON = QColor("#007acc")
    TRACK_OFF = QColor("#5a5a5a")
    KNOB_ON = QColor("#e0e0e0")
    KNOB_OFF = QColor("#cccccc")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        w = self.width()
        h = self.height()
        r = h / 2

        # Track
        track_color = self.TRACK_ON if self.isChecked() else self.TRACK_OFF
        p.setBrush(QBrush(track_color))
        p.drawRoundedRect(QRect(0, 0, w, h), r, r)

        # Knob
        knob_d = h - 4
        knob_color = self.KNOB_ON if self.isChecked() else self.KNOB_OFF
        p.setBrush(QBrush(knob_color))
        if self.isChecked():
            knob_x = w - knob_d - 2
        else:
            knob_x = 2
        p.drawEllipse(int(knob_x), 2, int(knob_d), int(knob_d))

        p.end()
