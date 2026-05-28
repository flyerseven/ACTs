"""Global dark-theme stylesheet for ACTs — VSCode gray-black palette."""

APP_STYLE = """
/* ═══════════════════════════════════════════════════════════════════════════
   ACTs Dark Theme — Global Stylesheet (VSCode Gray-Black)
   ═══════════════════════════════════════════════════════════════════════ */

/* ── Palette ─────────────────────────────────────────────────────────── */

QWidget {
    background-color: #1e1e1e;
    color: #cccccc;
    font-family: "IBM Plex Sans", "Segoe UI", "Noto Sans SC", sans-serif;
    font-size: 12.5px;
}

QMainWindow {
    background-color: #1e1e1e;
}

/* ── Scrollbars ──────────────────────────────────────────────────────── */

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #424242;
    border-radius: 5px;
    min-height: 40px;
}
QScrollBar::handle:vertical:hover {
    background: #5a5a5a;
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
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #424242;
    border-radius: 5px;
    min-width: 40px;
}
QScrollBar::handle:horizontal:hover {
    background: #5a5a5a;
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
    background-color: #3c3c3c;
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
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}

QListWidget::item {
    padding: 8px 10px;
    border-radius: 6px;
    margin: 1px 0;
    color: #ababab;
}

QListWidget::item:hover {
    background-color: #2a2d2e;
    color: #e0e0e0;
}

QListWidget::item:selected {
    background-color: #264f78;
    color: #e0e0e0;
}

/* ── Inputs ──────────────────────────────────────────────────────────── */

QLineEdit,
QTextEdit,
QPlainTextEdit {
    background-color: #3c3c3c;
    border: 1px solid #3c3c3c;
    border-radius: 8px;
    padding: 8px 10px;
    color: #cccccc;
    selection-background-color: #264f78;
    selection-color: #e0e0e0;
}

QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus {
    border-color: #007acc;
    background-color: #3c3c3c;
}

QLineEdit:disabled,
QTextEdit:disabled,
QPlainTextEdit:disabled {
    background-color: #3c3c3c;
    color: #6a6a6a;
    border-color: #3c3c3c;
}

QLineEdit[placeholderText],
QTextEdit[placeholderText] {
    color: #5a5a5a;
}

/* ── Combo boxes ─────────────────────────────────────────────────────── */

QComboBox {
    background-color: #3c3c3c;
    border: 1px solid #3c3c3c;
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 20px;
    color: #cccccc;
}

QComboBox:hover {
    border-color: #424242;
}

QComboBox:focus,
QComboBox:on {
    border-color: #007acc;
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
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 8px;
    padding: 4px;
    selection-background-color: #264f78;
    selection-color: #e0e0e0;
    outline: none;
}

QComboBox QAbstractItemView::item {
    padding: 6px 10px;
    border-radius: 4px;
    min-height: 22px;
}

QComboBox:disabled {
    background-color: #3c3c3c;
    color: #6a6a6a;
}

/* ── Spin boxes ──────────────────────────────────────────────────────── */

QSpinBox,
QDoubleSpinBox {
    background-color: #3c3c3c;
    border: 1px solid #3c3c3c;
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 20px;
    color: #cccccc;
}

QSpinBox:focus,
QDoubleSpinBox:focus {
    border-color: #007acc;
}

QSpinBox::up-button,
QDoubleSpinBox::up-button {
    border: none;
    border-left: 1px solid #3c3c3c;
    width: 22px;
}

QSpinBox::down-button,
QDoubleSpinBox::down-button {
    border: none;
    border-left: 1px solid #3c3c3c;
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
    color: #6a6a6a;
}

/* ── Standard buttons ────────────────────────────────────────────────── */

QPushButton {
    background-color: #3c3c3c;
    color: #cccccc;
    border: 1px solid #3c3c3c;
    border-radius: 8px;
    padding: 7px 16px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #424242;
    border-color: #5a5a5a;
}

QPushButton:pressed {
    background-color: #252526;
}

QPushButton:disabled {
    background-color: #252526;
    color: #5a5a5a;
    border-color: #3c3c3c;
}

/* Primary button variant */
QPushButton[cssClass="primary"] {
    background-color: #007acc;
    border-color: #007acc;
    color: #e0e0e0;
}

QPushButton[cssClass="primary"]:hover {
    background-color: #0098ff;
    border-color: #0098ff;
}

QPushButton[cssClass="primary"]:pressed {
    background-color: #005a9e;
}

QPushButton[cssClass="primary"]:disabled {
    background-color: #004578;
    border-color: #004578;
    color: #6a6a6a;
}

/* Danger button variant */
QPushButton[cssClass="danger"] {
    background-color: transparent;
    border-color: #f44747;
    color: #f44747;
}

QPushButton[cssClass="danger"]:hover {
    background-color: #5a1d1d;
    border-color: #f44747;
    color: #ffaaaa;
}

QPushButton[cssClass="danger"]:pressed {
    background-color: #5a1d1d;
}

/* Ghost button variant */
QPushButton[cssClass="ghost"] {
    background-color: transparent;
    border-color: transparent;
    color: #858585;
}

QPushButton[cssClass="ghost"]:hover {
    background-color: #2a2d2e;
    color: #cccccc;
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
    color: #858585;
    font-weight: 500;
    font-size: 12px;
}

QPushButton[checkable="true"]:hover {
    background-color: #2a2d2e;
    color: #cccccc;
}

QPushButton[checkable="true"]:checked {
    background-color: #264f78;
    border-color: #264f78;
    color: #e0e0e0;
}

/* ── Labels ──────────────────────────────────────────────────────────── */

QLabel#titleLabel {
    font-size: 15px;
    font-weight: 700;
    color: #e0e0e0;
}

QLabel#sectionLabel {
    color: #858585;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 8px;
}

QLabel#subtitleLabel {
    color: #6a6a6a;
    font-size: 10px;
}

/* ── Frames / Cards ──────────────────────────────────────────────────── */

QFrame#card {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 12px;
    padding: 0;
}

QFrame#titleBar {
    background-color: #252526;
    border-bottom: 1px solid #3c3c3c;
}

/* ── Tool tips ───────────────────────────────────────────────────────── */

QToolTip {
    background-color: #383838;
    color: #e0e0e0;
    border: 1px solid #424242;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
}
"""
