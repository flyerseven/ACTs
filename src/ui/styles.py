"""Global dark-theme stylesheet for ACTs."""

APP_STYLE = """
/* ═══════════════════════════════════════════════════════════════════════════
   ACTs Dark Theme — Global Stylesheet
   ═══════════════════════════════════════════════════════════════════════ */

/* ── Palette ─────────────────────────────────────────────────────────── */

QWidget {
    background-color: #0b1120;
    color: #e2e8f0;
    font-family: "IBM Plex Sans", "Segoe UI", "Noto Sans SC", sans-serif;
    font-size: 12.5px;
}

QMainWindow {
    background-color: #0b1120;
}

/* ── Scrollbars ──────────────────────────────────────────────────────── */

QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #334155;
    border-radius: 3px;
    min-height: 40px;
}
QScrollBar::handle:vertical:hover {
    background: #475569;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    background: transparent;
    height: 6px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #334155;
    border-radius: 3px;
    min-width: 40px;
}
QScrollBar::handle:horizontal:hover {
    background: #475569;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
}
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: none;
}

/* ── Splitters ───────────────────────────────────────────────────────── */

QSplitter::handle {
    background-color: #1e293b;
    width: 1px;
}

QSplitter::handle:horizontal {
    width: 1px;
}

QSplitter::handle:vertical {
    height: 1px;
}

/* ── Lists ───────────────────────────────────────────────────────────── */

QListWidget {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}

QListWidget::item {
    padding: 8px 10px;
    border-radius: 6px;
    margin: 1px 0;
    color: #cbd5e1;
}

QListWidget::item:hover {
    background-color: #1e293b;
    color: #f1f5f9;
}

QListWidget::item:selected {
    background-color: #1d4ed8;
    color: #f8fafc;
}

/* ── Inputs ──────────────────────────────────────────────────────────── */

QLineEdit,
QTextEdit,
QPlainTextEdit {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 8px 10px;
    color: #e2e8f0;
    selection-background-color: #1d4ed8;
    selection-color: #f8fafc;
}

QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus {
    border-color: #3b82f6;
    background-color: #0f172a;
}

QLineEdit:disabled,
QTextEdit:disabled,
QPlainTextEdit:disabled {
    background-color: #0f172a;
    color: #64748b;
    border-color: #1e293b;
}

QLineEdit[placeholderText],
QTextEdit[placeholderText] {
    color: #475569;
}

/* ── Combo boxes ─────────────────────────────────────────────────────── */

QComboBox {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 20px;
    color: #e2e8f0;
}

QComboBox:hover {
    border-color: #334155;
}

QComboBox:focus,
QComboBox:on {
    border-color: #3b82f6;
}

QComboBox::drop-down {
    border: none;
    width: 28px;
    padding-right: 6px;
}

QComboBox::down-arrow {
    border: none;
    width: 10px;
    height: 10px;
}

QComboBox QAbstractItemView {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 4px;
    selection-background-color: #1d4ed8;
    selection-color: #f8fafc;
    outline: none;
}

QComboBox QAbstractItemView::item {
    padding: 6px 10px;
    border-radius: 4px;
    min-height: 22px;
}

QComboBox:disabled {
    background-color: #0f172a;
    color: #64748b;
}

/* ── Spin boxes ──────────────────────────────────────────────────────── */

QSpinBox,
QDoubleSpinBox {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 20px;
    color: #e2e8f0;
}

QSpinBox:focus,
QDoubleSpinBox:focus {
    border-color: #3b82f6;
}

QSpinBox::up-button,
QDoubleSpinBox::up-button {
    border: none;
    border-left: 1px solid #1e293b;
    width: 22px;
}

QSpinBox::down-button,
QDoubleSpinBox::down-button {
    border: none;
    border-left: 1px solid #1e293b;
    width: 22px;
}

QSpinBox::up-arrow,
QDoubleSpinBox::up-arrow {
    border: none;
    width: 8px;
    height: 8px;
}

QSpinBox::down-arrow,
QDoubleSpinBox::down-arrow {
    border: none;
    width: 8px;
    height: 8px;
}

QSpinBox:disabled,
QDoubleSpinBox:disabled {
    color: #64748b;
}

/* ── Standard buttons ────────────────────────────────────────────────── */

QPushButton {
    background-color: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 7px 16px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #334155;
    border-color: #475569;
}

QPushButton:pressed {
    background-color: #0f172a;
}

QPushButton:disabled {
    background-color: #0f172a;
    color: #475569;
    border-color: #1e293b;
}

/* Primary button variant */
QPushButton[cssClass="primary"] {
    background-color: #1d4ed8;
    border-color: #1d4ed8;
    color: #f8fafc;
}

QPushButton[cssClass="primary"]:hover {
    background-color: #2563eb;
    border-color: #2563eb;
}

QPushButton[cssClass="primary"]:pressed {
    background-color: #1e40af;
}

QPushButton[cssClass="primary"]:disabled {
    background-color: #1e3a8a;
    border-color: #1e3a8a;
    color: #64748b;
}

/* Danger button variant */
QPushButton[cssClass="danger"] {
    background-color: transparent;
    border-color: #dc2626;
    color: #fca5a5;
}

QPushButton[cssClass="danger"]:hover {
    background-color: #7f1d1d;
    border-color: #ef4444;
    color: #fecaca;
}

QPushButton[cssClass="danger"]:pressed {
    background-color: #991b1b;
}

/* Ghost button variant */
QPushButton[cssClass="ghost"] {
    background-color: transparent;
    border-color: transparent;
    color: #94a3b8;
}

QPushButton[cssClass="ghost"]:hover {
    background-color: #1e293b;
    color: #e2e8f0;
}

/* Small button variant */
QPushButton[cssClass="small"] {
    padding: 4px 10px;
    font-size: 11px;
    border-radius: 6px;
}

/* ── Checkable tab buttons ───────────────────────────────────────────── */

QPushButton[checkable="true"] {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 7px 14px;
    color: #94a3b8;
    font-weight: 500;
    font-size: 12px;
}

QPushButton[checkable="true"]:hover {
    background-color: #1e293b;
    color: #e2e8f0;
}

QPushButton[checkable="true"]:checked {
    background-color: #1d4ed8;
    border-color: #1d4ed8;
    color: #f8fafc;
}

/* ── Labels ──────────────────────────────────────────────────────────── */

QLabel#titleLabel {
    font-size: 15px;
    font-weight: 700;
    color: #f8fafc;
}

QLabel#sectionLabel {
    color: #94a3b8;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 8px;
}

QLabel#subtitleLabel {
    color: #64748b;
    font-size: 10px;
}

/* ── Frames / Cards ──────────────────────────────────────────────────── */

QFrame#card {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 0;
}

QFrame#titleBar {
    background-color: #0f172a;
    border-bottom: 1px solid #1e293b;
}

/* ── Tool tips ───────────────────────────────────────────────────────── */

QToolTip {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
}
"""
