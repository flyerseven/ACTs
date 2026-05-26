APP_STYLE = """
QWidget {
    background-color: #0f172a;
    color: #f8fafc;
    font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    font-size: 12px;
}
QMainWindow {
    background-color: #0f172a;
}
QSplitter::handle {
    background-color: #1e293b;
}
QListWidget {
    background-color: #111827;
    border: 1px solid #334155;
    padding: 4px;
}
QListWidget::item {
    padding: 6px 8px;
}
QListWidget::item:selected {
    background-color: #1e40af;
    color: #f8fafc;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #0b1220;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 6px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border-color: #3b82f6;
}
QComboBox::drop-down {
    border-left: 1px solid #334155;
    width: 20px;
}
QPushButton {
    background-color: #1f2937;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 6px 12px;
}
QPushButton:hover {
    background-color: #374151;
}
QPushButton:disabled {
    background-color: #111827;
    color: #64748b;
}
QLabel#titleLabel {
    font-size: 14px;
    font-weight: 600;
}
"""
