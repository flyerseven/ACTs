from __future__ import annotations

import html
import json
import re
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
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
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    _HAS_WEBENGINE = True
except Exception:
    QWebEngineView = None
    QWebEngineSettings = None
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


# ── Chat bubble ──────────────────────────────────────────────────────────


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
        self._text_color = "#f8fafc"
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

        # ── content area ──
        if self._use_web:
            self.label = QWebEngineView()
            self.label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            settings = self.label.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
            self.label.page().setBackgroundColor(Qt.GlobalColor.transparent)
            self.label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
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
            self.label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        self.set_content(content, render_latex=True)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        layout.addLayout(header_layout)
        layout.addWidget(self.label)

        self._apply_role_style(role)

    # ── Public API ──────────────────────────────────────────────────────

    def set_content(self, content: str, render_latex: bool = False) -> None:
        """Replace the entire content and re-render."""
        self._render_latex = render_latex
        self._raw_text = content
        self._buffer.reset()
        if content:
            self._buffer.feed(content)
        self._render()
        self._apply_width_constraints()

    def append_chunk(self, chunk: str, render_latex: bool = True) -> None:
        """Append a streaming chunk and re-render the full accumulated text."""
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
            self.label.setMarkdown(self._raw_text)

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
            bg = "#2563eb"
            fg = "#f8fafc"
            border = "#1d4ed8"
        elif role == "assistant":
            bg = "#1f2937"
            fg = "#f8fafc"
            border = "#334155"
        else:
            bg = "#111827"
            fg = "#94a3b8"
            border = "#334155"

        self.setStyleSheet(
            "QFrame {"
            f"background-color: {bg};"
            f"color: {fg};"
            f"border: 1px solid {border};"
            "border-radius: 10px;"
            "}"
        )
        self._text_color = fg
        if isinstance(self.label, QTextBrowser):
            self.label.setStyleSheet(
                "QTextBrowser {"
                "background: transparent;"
                "border: none;"
                f"color: {fg};"
                "font-size: 12.5px;"
                "}"
                "QTextBrowser a { color: #60a5fa; }"
                "QTextBrowser code { background: rgba(15, 23, 42, 0.6); padding: 1px 4px; }"
                "QTextBrowser pre { background: rgba(15, 23, 42, 0.6); padding: 8px; border-radius: 6px; }"
                "QTextBrowser blockquote { color: #94a3b8; border-left: 3px solid #334155; margin: 6px 0; padding-left: 8px; }"
            )
        self.avatar.setStyleSheet(
            "QLabel {"
            f"background: {border};"
            f"color: {fg};"
            "border-radius: 11px;"
            "font-size: 10px;"
            "font-weight: 600;"
            "}"
        )
        self.copy_button.setStyleSheet(
            "QPushButton {"
            "background: transparent;"
            f"color: {fg};"
            "border: 1px solid transparent;"
            "padding: 0 6px;"
            "font-size: 10px;"
            "}"
            "QPushButton:hover {"
            "border-color: rgba(148, 163, 184, 0.6);"
            "background: rgba(15, 23, 42, 0.4);"
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
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(8, 8, 8, 8)
        self.container_layout.setSpacing(12)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._spacer = QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.container_layout.addItem(self._spacer)

        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

    def clear(self) -> None:
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
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
body {{ margin: 0; background: transparent; color: {color}; font-family: 'IBM Plex Sans','Segoe UI',sans-serif; font-size: 12.5px; }}
#content {{ white-space: pre-wrap; word-break: break-word; }}
pre, code {{ font-family: 'JetBrains Mono','Cascadia Code','Fira Code',monospace; font-size: 11.5px; }}
pre {{ white-space: pre-wrap; padding: 8px; border-radius: 6px; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid rgba(148,163,184,0.3); padding: 4px 6px; }}
blockquote {{ color: #94a3b8; border-left: 3px solid #334155; margin: 6px 0; padding-left: 8px; }}
img {{ max-width: 100%; }}
a {{ color: #60a5fa; }}
.katex-display {{ overflow-x: auto; overflow-y: hidden; padding: 4px 0; }}
</style>
<script src="katex.min.js"></script>
<script src="auto-render.min.js"></script>
<script src="../highlight/highlight.min.js"></script>
<script>
const delimiters = [
  {{left: "\\\\(", right: "\\\\)", display: false}},
  {{left: "\\\\[", right: "\\\\]", display: true}},
  {{left: "$$", right: "$$", display: true}},
  {{left: "$", right: "$", display: false}}
];

function setHtml(html, renderLatex) {{
  const content = document.getElementById("content");
  content.innerHTML = html || "";
  if (window.hljs) {{
    try {{ hljs.highlightAll(); }} catch(e) {{ console.error(e); }}
  }}
  if (renderLatex && window.renderMathInElement) {{
    try {{
      renderMathInElement(content, {{delimiters: delimiters, throwOnError: false}});
    }} catch(e) {{ console.error(e); }}
  }}
}}

function getHeight() {{
  return Math.ceil(document.body.scrollHeight);
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

    math_blocks = []

    def stash(m: re.Match) -> str:
        math_blocks.append(m.group(0))
        return f"<!--MATHBLOCK{len(math_blocks) - 1}-->"

    # Stash math blocks before Markdown conversion so their contents
    # (underscores, asterisks, etc.) are not interpreted as Markdown.
    text = re.sub(r"\\\[[\s\S]*?\\\]", stash, text)
    text = re.sub(r"\\\([\s\S]*?\\\)", stash, text)
    text = re.sub(r"\$\$[\s\S]*?\$\$", stash, text)
    text = re.sub(r"\$[^$\n\r]+?\$", stash, text)

    html_out = markdown.markdown(text, extensions=["fenced_code", "tables", "sane_lists", "nl2br"])

    for i, block in enumerate(math_blocks):
        html_out = html_out.replace(f"<!--MATHBLOCK{i}-->", html.escape(block))

    return html_out
