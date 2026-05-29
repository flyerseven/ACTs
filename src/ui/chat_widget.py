from __future__ import annotations

import html
import json
import re
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QSpacerItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    _HAS_WEBENGINE = True
except Exception:
    QWebEngineView = None
    QWebEngineSettings = None
    QWebEnginePage = None
    _HAS_WEBENGINE = False

try:
    import markdown

    _HAS_MARKDOWN = True
except Exception:
    markdown = None
    _HAS_MARKDOWN = False


# ── LaTeX delimiter helpers (for QTextBrowser fallback) ─────────────────

DELIM_PAIRS = [
    {"open": "\\[", "close": "\\]", "display": True},
    {"open": "\\(", "close": "\\)", "display": False},
    {"open": "$$", "close": "$$", "display": True},
    {"open": "$", "close": "$", "display": False},
]



def _is_escaped(s: str, pos: int) -> bool:
    bs = 0
    while pos - 1 - bs >= 0 and s[pos - 1 - bs] == "\\":
        bs += 1
    return bs % 2 == 1


def _find_unmatched_open(s: str) -> int:
    best_pos = -1
    for dp in DELIM_PAIRS:
        i = 0
        while i < len(s):
            idx = s.find(dp["open"], i)
            if idx == -1:
                break
            if not _is_escaped(s, idx):
                close_idx = s.find(dp["close"], idx + len(dp["open"]))
                if close_idx == -1 or _is_escaped(s, close_idx):
                    if best_pos == -1 or idx < best_pos:
                        best_pos = idx
                    break
                i = close_idx + len(dp["close"])
            else:
                i = idx + len(dp["open"])
    return best_pos


class StreamingBuffer:
    """Incremental text buffer for QTextBrowser fallback — holds back text
    with unmatched LaTeX delimiters until they are closed."""

    def __init__(self) -> None:
        self._raw: str = ""
        self._rendered: int = 0

    def feed(self, chunk: str) -> list[str]:
        self._raw += chunk
        new_text = self._raw[self._rendered:]
        if not new_text:
            return []

        rendered: list[str] = []
        while new_text:
            open_pos = _find_unmatched_open(new_text)
            if open_pos == 0:
                break
            if open_pos == -1:
                rendered.append(new_text)
                self._rendered += len(new_text)
                break
            if open_pos > 0:
                rendered.append(new_text[:open_pos])
                self._rendered += open_pos
            break
        return rendered

    def flush(self) -> str:
        tail = self._raw[self._rendered:]
        self._rendered = len(self._raw)
        return tail

    def reset(self) -> None:
        self._raw = ""
        self._rendered = 0


# ── Thinking process display ──────────────────────────────────────────────


class ThinkingWidget(QFrame):
    """Collapsible, semi-transparent thinking process display.

    Renders above the assistant reply bubble.  Shows a 🧠 header with
    expand/collapse toggle, and the thinking text at ~65% opacity.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._thinking_text: str = ""
        self._streaming: bool = False
        self._user_folded: bool = False
        self._collapsed: bool = False
        self._start_time: float | None = None

        self._build_ui()
        self.setVisible(False)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── Header bar ──
        header = QWidget()
        header.setCursor(Qt.CursorShape.PointingHandCursor)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 3, 8, 3)
        header_layout.setSpacing(6)

        self._icon_label = QLabel("🧠")
        self._icon_label.setFixedWidth(18)
        header_layout.addWidget(self._icon_label)

        self._title_label = QLabel("思考过程")
        self._title_label.setStyleSheet(
            "color: #a0a0a0; font-size: 11px; font-weight: 500; background: transparent;"
        )
        header_layout.addWidget(self._title_label)

        self._time_label = QLabel("")
        self._time_label.setStyleSheet(
            "color: #6a6a6a; font-size: 9px; background: transparent;"
        )
        header_layout.addWidget(self._time_label)

        header_layout.addStretch(1)

        self._toggle_btn = QPushButton("▲ 收起")
        self._toggle_btn.setFixedHeight(20)
        self._toggle_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #858585; border: 1px solid rgba(255,255,255,0.06);"
            "  border-radius: 4px; padding: 0 8px; font-size: 10px;"
            "}"
            "QPushButton:hover { color: #cccccc; border-color: rgba(255,255,255,0.15); }"
        )
        self._toggle_btn.clicked.connect(self._toggle)
        header_layout.addWidget(self._toggle_btn)

        layout.addWidget(header)

        # ── Content body ──
        self._body = QTextBrowser()
        self._body.setOpenExternalLinks(False)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setFrameShape(QFrame.Shape.NoFrame)
        self._body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._body.setStyleSheet(
            "QTextBrowser {"
            "  background: transparent; border: none;"
            "  color: #a0a0a0; font-size: 11.5px;"
            "  font-style: italic; line-height: 1.55;"
            "}"
        )
        self._body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._body)

        # ── Whole-widget styling ──
        self.setStyleSheet(
            "ThinkingWidget {"
            "  border: 1px solid rgba(255,255,255,0.08);"
            "  background: rgba(255,255,255,0.04);"
            "  border-radius: 10px;"
            "}"
        )

        # Opacity effect for semi-transparency
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.65)
        self.setGraphicsEffect(self._opacity)

    # ── Public API ──────────────────────────────────────────────────────

    def start_stream(self) -> None:
        """Begin streaming mode — auto-expand and show animated dots."""
        self._streaming = True
        import time
        self._start_time = time.time()
        self._thinking_text = ""
        if not self._user_folded:
            self._collapsed = False
            self._body.setVisible(True)
            self._toggle_btn.setText("▲ 收起")
        self._title_label.setText("正在思考...")
        self.setVisible(True)

    def append_chunk(self, chunk: str) -> None:
        """Append a streaming chunk of thinking text."""
        if self._streaming:
            self._thinking_text += chunk
            # Show plain text — no markdown rendering
            self._body.setPlainText(self._thinking_text)
            # Auto-scroll to bottom
            bar = self._body.verticalScrollBar()
            if bar:
                bar.setValue(bar.maximum())

    def finalize(self) -> None:
        """Mark thinking as complete. Auto-collapse if user hasn't folded."""
        self._streaming = False
        if self._start_time:
            import time
            elapsed = time.time() - self._start_time
            self._time_label.setText(f"耗时 {elapsed:.1f}s")
        self._title_label.setText("思考过程")
        if not self._user_folded:
            self._collapse()

    def set_collapsed(self, collapsed: bool) -> None:
        """Programmatic collapse/expand."""
        if collapsed:
            self._collapse()
        else:
            self._expand()

    def is_user_folded(self) -> bool:
        return self._user_folded

    # ── Internals ───────────────────────────────────────────────────────

    def _toggle(self) -> None:
        if self._collapsed:
            self._expand()
        else:
            self._user_folded = True
            self._collapse()

    def _collapse(self) -> None:
        self._collapsed = True
        self._body.setVisible(False)
        self._toggle_btn.setText("▼ 展开")

    def _expand(self) -> None:
        self._collapsed = False
        self._body.setVisible(True)
        self._toggle_btn.setText("▲ 收起")


# ── Chat bubble ──────────────────────────────────────────────────────────


if _HAS_WEBENGINE:

    class _ClipboardPage(QWebEnginePage):
        """Intercepts clipboard:// URLs so JS code-copy buttons can reach the
        system clipboard through PyQt6 (navigator.clipboard is blocked in
        file:// contexts)."""

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            if url.scheme() == "clipboard":
                from urllib.parse import unquote
                text = unquote(url.toString().removeprefix("clipboard://copy?text="))
                clipboard = QApplication.clipboard()
                if clipboard is not None:
                    clipboard.setText(text)
                return False
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class ChatBubbleWidget(QFrame):
    """A single chat message bubble.

    Two rendering paths:
    - WebEngine (preferred): Markdown → HTML via Python markdown library,
      LaTeX rendered client-side by KaTeX, code highlighted by highlight.js.
    - QTextBrowser (fallback): Uses Qt's built-in setMarkdown(). LaTeX
      delimiters are preserved but not rendered as math.
    """

    _MAX_WEB_TEXTURE = 8000

    def __init__(self, role: str, content: str) -> None:
        super().__init__()
        self.role = role
        self._max_width: int | None = None
        self._text_color = "#e0e0e0"
        self._render_latex = True
        self._use_web = _HAS_WEBENGINE and _katex_available()
        self._web_ready = False
        self._pending_render = False
        self._raw_text = ""
        self._buffer = StreamingBuffer()

        # ── header ──
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.avatar = QLabel(self._avatar_text(role))
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setFixedSize(22, 22)

        self.name_label = QLabel(self._role_name(role))
        self.name_label.setStyleSheet("font-weight: 600; font-size: 11px;")

        header_layout.addWidget(self.avatar)
        header_layout.addWidget(self.name_label)
        header_layout.addStretch(1)

        self.copy_button = QPushButton("Copy")
        self.copy_button.setFixedHeight(22)
        self.copy_button.clicked.connect(self._copy_content)
        header_layout.addWidget(self.copy_button)

        if role == "user":
            self.copy_button.setVisible(False)

        # ── thinking process (shown above content) ──
        self.thinking_widget = ThinkingWidget()
        self.thinking_widget.setVisible(False)

        # ── content area ──
        if self._use_web:
            from PyQt6.QtGui import QColor
            self.label = QWebEngineView()
            self.label.setPage(_ClipboardPage(self.label))
            settings = self.label.page().settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
            self.label.page().setBackgroundColor(QColor(self._bg_for_role(role)))
            self.label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self.label.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self.label.page().loadFinished.connect(self._on_web_loaded)
            base_url = QUrl.fromLocalFile(str(_katex_dir()) + "/")
            self.label.setHtml(_katex_shell_html(self._text_color), base_url)
        else:
            self.label = QTextBrowser()
            self.label.setOpenExternalLinks(True)
            self.label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.label.setFrameShape(QFrame.Shape.NoFrame)
            self.label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
            self.label.setMinimumWidth(0)
            self.label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        self.set_content(content, render_latex=True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        layout.addLayout(header_layout)
        layout.addWidget(self.thinking_widget)
        layout.addWidget(self.label)

        self._apply_role_style(role)

    # ── Public API ──────────────────────────────────────────────────────

    def set_content(self, content: str, render_latex: bool = False) -> None:
        """Replace the entire content and re-render."""
        self._render_latex = render_latex
        self._raw_text = content
        # If this bubble has thinking, make sure it's finalized (non-streaming path)
        if self.thinking_widget.isVisible():
            self.thinking_widget.finalize()
        self._buffer.reset()
        if content:
            self._buffer.feed(content)
        self._render()
        self._apply_width_constraints()

    def append_chunk(self, chunk: str, render_latex: bool = True) -> None:
        """Append a streaming chunk and re-render the full accumulated text."""
        # Auto-finalize thinking when main content starts streaming
        if (self.thinking_widget.isVisible()
            and getattr(self.thinking_widget, '_streaming', False)):
            self.thinking_widget.finalize()
        self._raw_text += chunk
        self._render_latex = self._render_latex or render_latex
        if not self._use_web:
            if self._render_latex:
                safe_segments = self._buffer.feed(chunk)
                if safe_segments:
                    self.label.setMarkdown(self._raw_text)
            else:
                self.label.setMarkdown(self._raw_text)
        else:
            self._render()
        self._apply_width_constraints()

    def flush_stream(self) -> None:
        """Final render after streaming ends."""
        if not self._use_web:
            if self._render_latex:
                tail = self._buffer.flush()
                if tail:
                    self.label.setMarkdown(self._raw_text)
        else:
            self._render()
        self._apply_width_constraints()

    def start_thinking(self) -> None:
        """Show and start the thinking widget in streaming mode."""
        self.thinking_widget.start_stream()

    def append_thinking(self, chunk: str) -> None:
        """Append a thinking text chunk during streaming."""
        self.thinking_widget.append_chunk(chunk)

    def finalize_thinking(self) -> None:
        """Complete the thinking stream — auto-collapses unless user-folded."""
        self.thinking_widget.finalize()

    # ── Sizing ──────────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_width_constraints()

    def set_max_width(self, max_width: int) -> None:
        self._max_width = max_width
        self._apply_width_constraints()

    def _apply_width_constraints(self) -> None:
        if not self._max_width:
            return

        if isinstance(self.label, QTextBrowser):
            doc = self.label.document()
            doc.setTextWidth(-1)
            natural = doc.idealWidth() + 24
            if natural > self._max_width:
                doc.setTextWidth(self._max_width - 24)
                width = self._max_width
            else:
                doc.setTextWidth(natural - 24)
                width = int(natural)

            self.setMinimumWidth(max(120, width))
            self.setMaximumWidth(self._max_width)

            doc_height = int(doc.documentLayout().documentSize().height())
            self.label.setMinimumHeight(doc_height + 2)
            self.label.setMaximumHeight(16777215)
        else:
            self.setMinimumWidth(120)
            self.setMaximumWidth(self._max_width)
            self._request_web_height()

    # ── WebEngine internals ─────────────────────────────────────────────

    def _render(self) -> None:
        """Re-render _raw_text through the active path."""
        if self._use_web:
            if self._web_ready:
                self._render_web()
            else:
                self._pending_render = True
        else:
            if self._raw_text:
                self.label.setMarkdown(self._raw_text)
            else:
                self.label.setMarkdown("*Thinking...*")

    def _render_web(self) -> None:
        html_body = _markdown_to_html(self._raw_text)
        script = f"setHtml({json.dumps(html_body)}, {str(self._render_latex).lower()});"
        self.label.page().runJavaScript(script, lambda _: self._request_web_height())

    def _on_web_loaded(self, ok: bool) -> None:
        if not ok:
            return
        self._web_ready = True
        if self._pending_render:
            self._pending_render = False
            self._render_web()
        self._request_web_height()

    def _request_web_height(self) -> None:
        if not self._web_ready:
            return
        try:
            page = self.label.page()
        except RuntimeError:
            return
        if page is None:
            return
        page.runJavaScript("getHeight()", self._apply_web_height)
        page.runJavaScript("getNaturalWidth()", self._apply_web_width)

    def _apply_web_width(self, width: int) -> None:
        if not isinstance(width, int) or width <= 0:
            return
        content_w = width + 24
        if self._max_width:
            content_w = min(content_w, self._max_width)
        content_w = max(120, content_w)
        try:
            current = self.minimumWidth()
        except RuntimeError:
            return
        if content_w == current:
            return
        self.setMinimumWidth(content_w)

    def _apply_web_height(self, height: int) -> None:
        if not isinstance(height, int):
            return
        target = max(24, min(height, self._MAX_WEB_TEXTURE))
        try:
            current = self.label.maximumHeight()
        except RuntimeError:
            return
        if target == current:
            return
        self.label.setMinimumHeight(target)
        self.label.setMaximumHeight(target)

    # ── Helpers ─────────────────────────────────────────────────────────

    def _copy_content(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._raw_text)

    @staticmethod
    def _bg_for_role(role: str) -> str:
        if role == "user":
            return "#007acc"
        if role == "assistant":
            return "#2d2d2d"
        return "#252526"

    @staticmethod
    def _avatar_text(role: str) -> str:
        if role == "user":
            return "U"
        if role == "assistant":
            return "A"
        return "S"

    @staticmethod
    def _role_name(role: str) -> str:
        if role == "user":
            return "You"
        if role == "assistant":
            return "Assistant"
        return role.title()

    def _apply_role_style(self, role: str) -> None:
        if role == "user":
            bg = "#007acc"
            fg = "#e0e0e0"
            border = "#0098ff"
            avatar_bg = "#4fc1ff"
        elif role == "assistant":
            bg = "#2d2d2d"
            fg = "#cccccc"
            border = "#3c3c3c"
            avatar_bg = "#424242"
        else:
            bg = "#252526"
            fg = "#858585"
            border = "#3c3c3c"
            avatar_bg = "#2d2d2d"

        self.setStyleSheet(
            "QFrame {"
            f"background-color: {bg};"
            f"color: {fg};"
            f"border: 1px solid {border};"
            "border-radius: 12px;"
            "}"
        )
        self._text_color = fg
        if isinstance(self.label, QWebEngineView):
            from PyQt6.QtGui import QColor
            self.label.page().setBackgroundColor(QColor(bg))
        elif isinstance(self.label, QTextBrowser):
            self.label.setStyleSheet(
                "QTextBrowser {"
                "background: transparent;"
                "border: none;"
                f"color: {fg};"
                "font-size: 12.5px;"
                "line-height: 1.6;"
                "}"
                "QTextBrowser a { color: #4fc1ff; }"
                "QTextBrowser code { background: rgba(0,0,0,0.25); padding: 2px 5px; border-radius: 4px; font-size: 11.5px; }"
                "QTextBrowser pre { background: rgba(0,0,0,0.3); padding: 10px; border-radius: 8px; font-size: 11.5px; }"
                "QTextBrowser blockquote { color: #858585; border-left: 3px solid #424242; margin: 6px 0; padding: 4px 10px; }"
            )
        self.avatar.setStyleSheet(
            "QLabel {"
            f"background-color: {avatar_bg};"
            f"color: {fg};"
            "border-radius: 11px;"
            "font-size: 10px;"
            "font-weight: 700;"
            "}"
        )
        self.copy_button.setStyleSheet(
            "QPushButton {"
            "background: transparent;"
            f"color: #6a6a6a;"
            "border: 1px solid transparent;"
            "border-radius: 4px;"
            "padding: 2px 8px;"
            "font-size: 10px;"
            "}"
            "QPushButton:hover {"
            "color: {fg};"
            "background: rgba(148, 163, 184, 0.1);"
            "}"
        )


# ── Chat row (bubble + alignment) ───────────────────────────────────────


class ChatRowWidget(QWidget):
    def __init__(self, bubble: ChatBubbleWidget, align_right: bool) -> None:
        super().__init__()
        self.bubble = bubble
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        if align_right:
            layout.addStretch(1)
            layout.addWidget(bubble)
        else:
            layout.addWidget(bubble)
            layout.addStretch(1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.width() > 0:
            max_width = int(self.width() * 0.75)
            self.bubble.set_max_width(max_width)


# ── Chat view (scrollable message list) ─────────────────────────────────


class ChatViewWidget(QWidget):
    scrolled_to_top = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(12, 12, 12, 12)
        self.container_layout.setSpacing(14)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._spacer = QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.container_layout.addItem(self._spacer)

        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        bar = self.scroll.verticalScrollBar()
        if bar is not None:
            bar.valueChanged.connect(self._on_scroll_value_changed)

    def clear(self) -> None:
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._spacer = QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.container_layout.addItem(self._spacer)

    def add_message(self, role: str, content: str, render_latex: bool = True) -> ChatBubbleWidget:
        bubble = ChatBubbleWidget(role, content)
        if render_latex:
            bubble.set_content(content, render_latex=True)
        align_right = role == "user"
        row = ChatRowWidget(bubble, align_right)
        self.container_layout.insertWidget(self.container_layout.count() - 1, row)
        self._scroll_to_bottom()
        return bubble

    def prepend_message(self, role: str, content: str, render_latex: bool = True) -> ChatBubbleWidget:
        """Insert a message at the top (for loading earlier history)."""
        bar = self.scroll.verticalScrollBar()
        old_max = bar.maximum() if bar else 0
        old_value = bar.value() if bar else 0

        bubble = ChatBubbleWidget(role, content)
        if render_latex:
            bubble.set_content(content, render_latex=True)
        align_right = role == "user"
        row = ChatRowWidget(bubble, align_right)
        self.container_layout.insertWidget(0, row)

        if bar:
            def _restore() -> None:
                new_max = bar.maximum()
                bar.setValue(old_value + (new_max - old_max))
            QTimer.singleShot(0, _restore)

        return bubble

    def update_message(self, bubble: ChatBubbleWidget, content: str, render_latex: bool = False) -> None:
        bubble.set_content(content, render_latex=render_latex)
        self._scroll_to_bottom()

    def append_to_message(self, bubble: ChatBubbleWidget, chunk: str, render_latex: bool = True) -> None:
        bubble.append_chunk(chunk, render_latex=render_latex)
        self._scroll_to_bottom()

    def flush_stream_to_message(self, bubble: ChatBubbleWidget) -> None:
        bubble.flush_stream()
        self._scroll_to_bottom()

    def scroll_to_bottom(self) -> None:
        QTimer.singleShot(50, self._scroll_to_bottom)
        QTimer.singleShot(300, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        if bar is not None:
            bar.setValue(bar.maximum())

    def _on_scroll_value_changed(self, value: int) -> None:
        if value == 0:
            self.scrolled_to_top.emit()


# ── KaTeX / highlight.js shell HTML ─────────────────────────────────────


def _katex_dir() -> Path:
    return Path(__file__).resolve().parent / "assets" / "katex"


def _katex_available() -> bool:
    return (_katex_dir() / "katex.min.js").exists()


def _katex_shell_html(color: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<link rel="stylesheet" href="katex.min.css" />
<link rel="stylesheet" href="../highlight/github-dark.min.css" />
<style>
body {{
  margin: 0; padding: 2px 0;
  background: transparent;
  color: {color};
  font-family: 'IBM Plex Sans','Segoe UI','Noto Sans SC',sans-serif;
  font-size: 12.5px;
  line-height: 1.65;
}}
#content {{ white-space: pre-wrap; word-break: break-word; }}
p {{ margin: 0.4em 0; }}
pre, code {{
  font-family: 'JetBrains Mono','Cascadia Code','Fira Code','Consolas',monospace;
  font-size: 11.5px;
}}
pre {{
  white-space: pre-wrap;
  padding: 12px;
  padding-top: 28px;
  border-radius: 8px;
  background: rgba(0,0,0,0.3);
  line-height: 1.5;
  position: relative;
}}
.code-copy-btn {{
  position: absolute;
  top: 4px; right: 6px;
  background: rgba(148,163,184,0.12);
  border: 1px solid rgba(148,163,184,0.18);
  color: #858585;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 10px;
  font-family: inherit;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s;
  z-index: 1;
}}
pre:hover .code-copy-btn {{
  opacity: 1;
}}
.code-copy-btn:hover {{
  background: rgba(204,204,204,0.15);
  color: #cccccc;
}}
code {{ background: rgba(0,0,0,0.2); padding: 2px 5px; border-radius: 4px; }}
pre code {{ background: none; padding: 0; border-radius: 0; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid rgba(148,163,184,0.2); padding: 6px 10px; text-align: left; }}
th {{ background: rgba(0,0,0,0.2); font-weight: 600; }}
blockquote {{
  color: #858585;
  border-left: 3px solid #007acc;
  margin: 8px 0;
  padding: 2px 12px;
}}
img {{ max-width: 100%; border-radius: 6px; }}
a {{ color: #4fc1ff; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.katex-display {{ overflow-x: auto; overflow-y: hidden; padding: 4px 0; }}
.katex {{ font-size: 1.05em; }}
hr {{ border: none; border-top: 1px solid #3c3c3c; margin: 12px 0; }}
ul, ol {{ padding-left: 1.5em; }}
li {{ margin: 2px 0; }}
h1, h2, h3, h4 {{ margin: 12px 0 4px 0; font-weight: 600; line-height: 1.3; }}
h1 {{ font-size: 1.3em; }}
h2 {{ font-size: 1.15em; }}
h3 {{ font-size: 1.05em; }}
.loading-dots {{
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 10px 2px;
}}
.loading-dots span {{
  width: 7px;
  height: 7px;
  background: #6a6a6a;
  border-radius: 50%;
  animation: dot-bounce 1.4s ease-in-out infinite both;
}}
.loading-dots span:nth-child(1) {{ animation-delay: -0.32s; }}
.loading-dots span:nth-child(2) {{ animation-delay: -0.16s; }}
.loading-dots span:nth-child(3) {{ animation-delay: 0s; }}
@keyframes dot-bounce {{
  0%, 80%, 100% {{ transform: scale(0.3); opacity: 0.4; }}
  40% {{ transform: scale(1); opacity: 1; }}
}}
</style>
<script src="katex.min.js"></script>
<script src="auto-render.min.js"></script>
<script src="../highlight/highlight.min.js"></script>
<script>
var delimiters = [
  {{left: "\\\\(", right: "\\\\)", display: false}},
  {{left: "\\\\[", right: "\\\\]", display: true}},
  {{left: "$$", right: "$$", display: true}},
  {{left: "$", right: "$", display: false}}
];

function setHtml(html, renderLatex) {{
  var content = document.getElementById("content");
  if (!html || html.trim() === '') {{
    content.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
    return;
  }}
  content.innerHTML = html;
  if (window.hljs) {{
    try {{ hljs.highlightAll(); }} catch(e) {{ console.error(e); }}
  }}
  addCopyButtons();
  if (renderLatex && window.renderMathInElement) {{
    try {{
      renderMathInElement(content, {{delimiters: delimiters, throwOnError: false}});
    }} catch(e) {{ console.error(e); }}
  }}
}}

function addCopyButtons() {{
  var pres = document.querySelectorAll('#content pre');
  for (var i = 0; i < pres.length; i++) {{
    (function(pre) {{
      if (pre.querySelector('.code-copy-btn')) return;
      var btn = document.createElement('button');
      btn.className = 'code-copy-btn';
      btn.textContent = 'Copy';
      btn.onclick = function() {{
        var code = pre.textContent || '';
        window.location.href = 'clipboard://copy?text=' + encodeURIComponent(code);
        btn.textContent = 'Copied!';
        btn.style.color = '#4ade80';
        setTimeout(function() {{
          btn.textContent = 'Copy';
          btn.style.color = '';
        }}, 2000);
      }};
      pre.appendChild(btn);
    }})(pres[i]);
  }}
}}

function getHeight() {{
  return Math.ceil(document.body.scrollHeight);
}}

function getNaturalWidth() {{
  var body = document.body;
  var oldWs = body.style.whiteSpace;
  var oldW = body.style.width;
  var oldMaxW = body.style.maxWidth;
  body.style.whiteSpace = 'pre';
  body.style.width = 'auto';
  body.style.maxWidth = 'none';
  var w = body.scrollWidth;
  body.style.whiteSpace = oldWs;
  body.style.width = oldW;
  body.style.maxWidth = oldMaxW;
  return w + 6;
}}
</script>
</head>
<body>
<div id="content"></div>
</body>
</html>"""


# ── Markdown → HTML ─────────────────────────────────────────────────────


def _markdown_to_html(text: str) -> str:
    """Convert Markdown to HTML, preserving LaTeX math blocks for KaTeX."""
    if not _HAS_MARKDOWN:
        return f"<pre>{html.escape(text)}</pre>"

    math_blocks: list[str] = []

    def stash_math(m: re.Match) -> str:
        math_blocks.append(m.group(0))
        return f"<!--MATHBLOCK{len(math_blocks) - 1}-->"

    # Stash math blocks before Markdown conversion so their contents
    # (underscores, asterisks, etc.) are not interpreted as Markdown.
    text = re.sub(r"\\\[[\s\S]*?\\\]", stash_math, text)
    text = re.sub(r"\\\([\s\S]*?\\\)", stash_math, text)
    text = re.sub(r"\$\$[\s\S]*?\$\$", stash_math, text)
    text = re.sub(r"\$[^$\n\r]+?\$", stash_math, text)

    html_out = markdown.markdown(text, extensions=["fenced_code", "tables", "sane_lists", "nl2br"])

    for i, block in enumerate(math_blocks):
        html_out = _restore_block(html_out, f"<!--MATHBLOCK{i}-->", html.escape(block))

    return html_out


def _restore_block(html_out: str, placeholder: str, replacement: str, *, fallback: str | None = None) -> str:
    """Replace *placeholder* with *replacement* in *html_out*.

    If the placeholder was HTML-escaped (e.g. because it landed inside a
    fenced or indented code block), restore the original source text
    instead — we do NOT attempt to render diagrams / math inside code blocks.
    """
    if placeholder in html_out:
        return html_out.replace(placeholder, replacement)

    escaped_placeholder = html.escape(placeholder)
    if escaped_placeholder in html_out:
        if fallback is not None:
            return html_out.replace(escaped_placeholder, html.escape(fallback))
        # No explicit fallback — use the escaped replacement
        escaped_replacement = html.escape(replacement)
        if escaped_replacement != escaped_placeholder:
            return html_out.replace(escaped_placeholder, escaped_replacement)

    return html_out
