"""ThoughtView — QWebEngineView wrapper for collapsible thought process UI."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, Qt, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

try:
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except Exception:
    _HAS_WEBENGINE = False

from core.thought_recorder import ThoughtRecorder


def _thought_view_html_path() -> Path:
    return Path(__file__).resolve().parent / "thought_view.html"


class _Bridge(QObject):
    """Exposes save-file dialog to JS via QWebChannel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._parent = parent

    @pyqtSlot(str, str)
    def save_file(self, content: str, default_name: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self._parent, "Export", default_name,
            "Markdown (*.md);;JSON (*.json);;All Files (*)",
        )
        if path:
            Path(path).write_text(content, encoding="utf-8")


class ThoughtView(QWidget):
    """Displays the agent's decision loop as collapsible HTML."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if not _HAS_WEBENGINE:
            raise RuntimeError("QWebEngineView is not available")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._webview = QWebEngineView()
        self._webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        settings = self._webview.page().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
        self._webview.page().setBackgroundColor(QColor("#1e1e1e"))

        self._channel = QWebChannel()
        self._bridge = _Bridge(self)
        self._channel.registerObject("bridge", self._bridge)
        self._webview.page().setWebChannel(self._channel)

        html_path = _thought_view_html_path()
        self._webview.setUrl(QUrl.fromLocalFile(str(html_path)))

        layout.addWidget(self._webview)

    def set_recorder(self, recorder: ThoughtRecorder) -> None:
        """Register a ThoughtRecorder so JS can listen to its signals."""
        self._channel.registerObject("recorder", recorder)
