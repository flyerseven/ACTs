#!/usr/bin/env python
"""Interactive visual test for LaTeX streaming rendering.

Launch with:  python tests/test_latex_streaming_visual.py

Feeds simulated LLM token streams character-by-character into a
QWebEngineView running the exact same KaTeX + streaming state machine
as the production chat_widget.  Use this to visually inspect:

- Whether formulas render progressively or flicker
- How partial / incomplete delimiters are held back
- Whether escapes are handled correctly
- Whether mixed delimiter types coexist
- Display vs inline formula layout
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

# ── ensure src/ is importable ──────────────────────────────────────────
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

try:
    from PyQt6.QtWebEngineCore import QWebEngineSettings  # noqa: E402
    from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
except ModuleNotFoundError:
    print("PyQt6-WebEngine is not installed.", file=sys.stderr)
    print("Install it with:  pip install PyQt6-WebEngine", file=sys.stderr)
    print("", file=sys.stderr)
    print("Falling back to QTextBrowser-based rendering test.", file=sys.stderr)
    print("(LaTeX rendering will use plain text, not KaTeX)", file=sys.stderr)
    QWebEngineView = None  # type: ignore[assignment]
    QWebEngineSettings = None  # type: ignore[assignment]

KATEX_DIR = SRC / "ui" / "assets" / "katex"
HIGHLIGHT_DIR = SRC / "ui" / "assets" / "highlight"


# ═══════════════════════════════════════════════════════════════════════
# HTML shell — identical to production chat_widget._katex_shell_html
# ═══════════════════════════════════════════════════════════════════════

SHELL_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<link rel="stylesheet" href="katex.min.css" />
<link rel="stylesheet" href="../highlight/github-dark.min.css" />
<style>
body { margin: 0; background: #0f172a; color: #f8fafc;
       font-family: 'IBM Plex Sans','Segoe UI',sans-serif; font-size: 13px; }
#content { white-space: pre-wrap; word-break: break-word; padding: 12px; }
pre, code { font-family: 'JetBrains Mono','Cascadia Code','Fira Code',monospace; font-size: 11.5px; }
pre { white-space: pre-wrap; padding: 8px; border-radius: 6px; }
.katex-display { overflow-x: auto; overflow-y: hidden; padding: 4px 0; }
#log { margin-top: 8px; border-top: 1px solid #334155; padding: 8px 12px;
       font-size: 10px; color: #94a3b8; max-height: 80px; overflow-y: auto; }
</style>
<script src="katex.min.js"></script>
<script src="auto-render.min.js"></script>
<script src="../highlight/highlight.min.js"></script>
<script>
const delimiters = [
  {left: "\\(", right: "\\)", display: false},
  {left: "\\[", right: "\\]", display: true},
  {left: "$$", right: "$$", display: true},
  {left: "$", right: "$", display: false}
];

let rawBuffer = "";
let renderedLength = 0;
let renderScheduled = false;
const RENDER_DELAY = 60;

const DELIM_PAIRS = [
  {open: "\\[", close: "\\]", display: true},
  {open: "\\(", close: "\\)", display: false},
  {open: "$$", close: "$$", display: true},
  {open: "$", close: "$", display: false}
];

function isEscaped(str, pos) {
  let bs = 0;
  while (pos - 1 - bs >= 0 && str[pos - 1 - bs] === "\\") bs++;
  return bs % 2 === 1;
}

function findUnmatchedOpen(str) {
  let bestPos = -1;
  for (const dp of DELIM_PAIRS) {
    let i = 0;
    while (i < str.length) {
      let idx = str.indexOf(dp.open, i);
      if (idx === -1) break;
      if (!isEscaped(str, idx)) {
        let closeIdx = str.indexOf(dp.close, idx + dp.open.length);
        if (closeIdx === -1 || isEscaped(str, closeIdx)) {
          if (bestPos === -1 || idx < bestPos) bestPos = idx;
          break;
        }
        i = closeIdx + dp.close.length;
      } else {
        i = idx + dp.open.length;
      }
    }
  }
  return bestPos;
}

function setHtml(html, renderLatex) {
  rawBuffer = "";
  renderedLength = 0;
  document.getElementById("log").textContent = "";
  const content = document.getElementById("content");
  content.innerHTML = html || "";
  if (renderLatex && window.renderMathInElement) {
    try { renderMathInElement(content, {delimiters: delimiters, throwOnError: false}); }
    catch(e) { console.error(e); }
  }
  if (window.hljs) { try { hljs.highlightAll(); } catch(e) {} }
}

function appendText(text, renderLatex) {
  if (!text) return;
  rawBuffer += text;
  scheduleRender(renderLatex);
}

function scheduleRender(renderLatex) {
  if (renderScheduled) return;
  renderScheduled = true;
  setTimeout(function() {
    renderScheduled = false;
    renderStep(renderLatex);
  }, RENDER_DELAY);
}

function renderStep(renderLatex) {
  const content = document.getElementById("content");
  let newText = rawBuffer.slice(renderedLength);
  if (!newText) return;

  const openPos = findUnmatchedOpen(newText);
  if (openPos === 0) return;
  if (openPos > 0) newText = newText.slice(0, openPos);

  const span = document.createElement("span");
  span.textContent = newText;
  content.appendChild(span);
  if (renderLatex) {
    try { renderMathInElement(span, {delimiters: delimiters, throwOnError: false}); }
    catch(e) { console.error(e); }
  }
  renderedLength += newText.length;

  // update diagnostic log
  var log = document.getElementById("log");
  log.textContent = "rendered: " + renderedLength + " / pending: " +
    (rawBuffer.length - renderedLength);
}

function getHeight() { return Math.ceil(document.body.scrollHeight); }
function reset() { rawBuffer = ""; renderedLength = 0;
  document.getElementById("content").innerHTML = "";
  document.getElementById("log").textContent = ""; }

// allow Python to query state
function getRawBuffer() { return rawBuffer; }
function getRenderedLength() { return renderedLength; }
</script>
</head>
<body>
<div id="content"></div>
<div id="log"></div>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════════════
# Test case definitions
# ═══════════════════════════════════════════════════════════════════════

TestCase = tuple[str, str, list[str]]  # (title, description, chunks)


def _tc(title: str, desc: str, text: str, chunk_size: int = 1) -> TestCase:
    """Chop `text` into character-level chunks (simulates token streaming)."""
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    return (title, desc, chunks)


def _tc_words(title: str, desc: str, text: str) -> TestCase:
    """Chop `text` into word-level chunks (spaces preserved at word end)."""
    words = text.split(" ")
    chunks = []
    for i, w in enumerate(words):
        chunks.append(w if i == 0 else " " + w)
    return (title, desc, chunks)


TEST_CASES: list[TestCase] = [
    # ── basic inline ─────────────────────────────────────────────────
    _tc(
        "Inline formula",
        "$x^2 + y^2 = z^2$",
        "The Pythagorean relation $x^2 + y^2 = z^2$ is fundamental.",
        chunk_size=2,
    ),

    # ── display formula ──────────────────────────────────────────────
    _tc(
        "Display formula",
        "$$\\int_0^\\infty$$",
        "The Gaussian integral:\n$$\\int_0^\\infty e^{-x^2} dx = \\frac{\\sqrt{\\pi}}{2}$$\nis a classic result.",
        chunk_size=3,
    ),

    # ── escaped dollar ───────────────────────────────────────────────
    _tc(
        "Escaped dollar",
        "\\$100 vs $x^2$",
        "The price is \\$100 but the formula $x^2$ costs nothing.",
        chunk_size=2,
    ),

    # ── all four delimiter types ─────────────────────────────────────
    _tc(
        "All 4 delimiters",
        "$x$, $$y$$, \\(z\\), \\[w\\]",
        r"Inline $a+b$, display $$c+d$$, paren \(e+f\), bracket \[g+h\] all coexist.",
        chunk_size=3,
    ),

    # ── formula split across chunks ──────────────────────────────────
    _tc(
        "Chunk-boundary split",
        "$ opens in one chunk, closes in another",
        "Start text $then a formula here$ end text",
        chunk_size=5,
    ),

    # ── complex LaTeX (fractions, roots) ─────────────────────────────
    _tc(
        "Complex LaTeX",
        "Fractions, roots, sums",
        r"The quadratic formula: $$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$$ solves $ax^2+bx+c=0$.",
        chunk_size=4,
    ),

    # ── matrix ───────────────────────────────────────────────────────
    _tc(
        "Matrix",
        "pmatrix environment",
        r"A rotation matrix: $$R(\theta) = \begin{pmatrix} \cos\theta & -\sin\theta \\ \sin\theta & \cos\theta \end{pmatrix}$$",
        chunk_size=4,
    ),

    # ── sum with limits ──────────────────────────────────────────────
    _tc(
        "Sum with limits",
        "\\sum_{i=1}^{n}",
        r"The sum $\sum_{i=1}^{n} i = \frac{n(n+1)}{2}$ is Gauss's formula.",
        chunk_size=3,
    ),

    # ── consecutive formulas ─────────────────────────────────────────
    _tc(
        "Consecutive formulas",
        "Multiple $...$ back-to-back",
        r"Values: $a=1$, $b=2$, $c=3$, so $a+b+c=6$.",
        chunk_size=2,
    ),

    # ── display then inline ──────────────────────────────────────────
    _tc(
        "Display + inline mix",
        "$$ then $",
        r"We know $$\int_0^1 x^n dx = \frac{1}{n+1}$$ hence for $n=2$ we get $1/3$.",
        chunk_size=5,
    ),

    # ── long text with late formula ──────────────────────────────────
    _tc(
        "Late-appearing formula",
        "Long preamble then math",
        "This is a long explanatory text that goes on for a while before we finally introduce the equation $E=mc^2$ at the very end.",
        chunk_size=3,
    ),

    # ── backslash-heavy ──────────────────────────────────────────────
    _tc(
        "Backslash-heavy",
        "Many LaTeX commands",
        r"$$\Phi(x) = \frac{1}{\sqrt{2\pi}} \int_{-\infty}^{x} e^{-t^2/2} \, dt$$",
        chunk_size=3,
    ),

    # ── empty / edge ─────────────────────────────────────────────────
    _tc(
        "Single-char formula",
        "$x$",
        "Let $x$ denote an unknown and $y$ another.",
        chunk_size=1,
    ),

    # ── Unicode mix ──────────────────────────────────────────────────
    _tc(
        "Unicode + math",
        "Chinese + LaTeX",
        "根据公式 $E = mc^2$ 可知，能量与质量成正比。\n进一步有 $$\\Delta E = \\Delta m \\cdot c^2$$",
        chunk_size=3,
    ),

    # ── escaped bracket ──────────────────────────────────────────────
    _tc(
        "Escaped brackets",
        r"\\[ and \\(",
        "The delimiters \\[ and \\( are not math when escaped: "
        "\\\\[x\\\\] and \\\\\n(x\\\\) vs real \\(y\\) and \\[z\\].",
        chunk_size=4,
    ),
]


# ═══════════════════════════════════════════════════════════════════════
# Main window
# ═══════════════════════════════════════════════════════════════════════

class LatexStreamingTestWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LaTeX Streaming Render Test")
        self.resize(1100, 750)

        self._chunks: list[str] = []
        self._chunk_idx: int = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._feed_next_chunk)
        self._running: bool = False
        self._interval_ms: int = 50
        self._has_webengine: bool = True

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # ── toolbar ──────────────────────────────────────────────────
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("Case:"))
        self.case_combo = QComboBox()
        for title, desc, _ in TEST_CASES:
            self.case_combo.addItem(f"{title}  — {desc}")
        self.case_combo.currentIndexChanged.connect(self._load_case)
        toolbar.addWidget(self.case_combo, stretch=1)

        toolbar.addWidget(QLabel("Speed:"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 200)
        self.speed_slider.setValue(50)
        self.speed_slider.setFixedWidth(120)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        toolbar.addWidget(self.speed_slider)
        self.speed_label = QLabel("50ms")
        self.speed_label.setFixedWidth(40)
        toolbar.addWidget(self.speed_label)

        self.chunk_spin = QSpinBox()
        self.chunk_spin.setRange(1, 20)
        self.chunk_spin.setValue(3)
        self.chunk_spin.setPrefix("Chars/step: ")
        toolbar.addWidget(self.chunk_spin)

        self.run_btn = QPushButton("▶ Run")
        self.run_btn.clicked.connect(self._toggle_run)
        toolbar.addWidget(self.run_btn)

        self.reset_btn = QPushButton("↺ Reset")
        self.reset_btn.clicked.connect(self._reset)
        toolbar.addWidget(self.reset_btn)

        self.step_btn = QPushButton("⏭ Step")
        self.step_btn.clicked.connect(self._step)
        toolbar.addWidget(self.step_btn)

        self.flush_btn = QPushButton("⏏ Flush")
        self.flush_btn.setToolTip("Append remaining text (simulates end-of-stream)")
        self.flush_btn.clicked.connect(self._flush_remaining)
        toolbar.addWidget(self.flush_btn)

        toolbar.addStretch()
        root.addLayout(toolbar)

        # ── splitter: webview | info panel ───────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # left: webview (or fallback)
        if QWebEngineView is not None:
            self.webview: QWebEngineView | QPlainTextEdit = QWebEngineView()
            settings = self.webview.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
            base_url = QUrl.fromLocalFile(str(KATEX_DIR) + "/")
            self.webview.setHtml(SHELL_HTML, base_url)
            self._has_webengine = True
        else:
            self.webview = QPlainTextEdit()
            self.webview.setReadOnly(True)
            self.webview.setStyleSheet(
                "QPlainTextEdit { background: #0f172a; color: #f8fafc; "
                "border: 1px solid #334155; font-size: 13px; }"
            )
            self._has_webengine = False
        splitter.addWidget(self.webview)

        # right: info panel
        right = QWidget()
        right_layout = QVBoxLayout(right)

        gb1 = QGroupBox("Source text (full)")
        gb1_layout = QVBoxLayout(gb1)
        self.source_view = QPlainTextEdit()
        self.source_view.setReadOnly(True)
        self.source_view.setStyleSheet(
            "QPlainTextEdit { background: #0f172a; color: #94a3b8; "
            "border: 1px solid #334155; font-size: 11px; font-family: monospace; }"
        )
        gb1_layout.addWidget(self.source_view)
        right_layout.addWidget(gb1)

        gb2 = QGroupBox("Chunk stream")
        gb2_layout = QVBoxLayout(gb2)
        self.chunk_view = QPlainTextEdit()
        self.chunk_view.setReadOnly(True)
        self.chunk_view.setStyleSheet(
            "QPlainTextEdit { background: #0f172a; color: #f8fafc; "
            "border: 1px solid #334155; font-size: 11px; font-family: monospace; }"
        )
        gb2_layout.addWidget(self.chunk_view)
        right_layout.addWidget(gb2)

        gb3 = QGroupBox("JS State")
        gb3_layout = QVBoxLayout(gb3)
        self.state_label = QLabel("rawBuffer=0  renderedLength=0  pending=0")
        self.state_label.setStyleSheet("color: #60a5fa; font-family: monospace; font-size: 10px;")
        gb3_layout.addWidget(self.state_label)
        right_layout.addWidget(gb3)

        gb4 = QGroupBox("Status")
        gb4_layout = QVBoxLayout(gb4)
        self.status_label = QLabel("Ready. Select a test case and click Run.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        gb4_layout.addWidget(self.status_label)
        right_layout.addWidget(gb4)

        right_layout.addStretch()
        splitter.addWidget(right)
        splitter.setSizes([700, 400])

        root.addWidget(splitter)

        # ── load first case ──────────────────────────────────────────
        self._load_case(0)

    # ── case management ──────────────────────────────────────────────

    def _load_case(self, index: int) -> None:
        self._stop()
        if self._has_webengine:
            self.webview.page().runJavaScript("reset();")
        else:
            self.webview.clear()
        _, _, chunks = TEST_CASES[index]
        self._chunks = list(chunks)
        self._chunk_idx = 0
        source_text = "".join(chunks)
        self.source_view.setPlainText(source_text)
        self.chunk_view.clear()
        self._update_state_display()
        self.status_label.setText(
            f"Loaded: {len(chunks)} chunks, {len(source_text)} chars total."
        )

    # ── streaming control ────────────────────────────────────────────

    def _toggle_run(self) -> None:
        if self._running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        if self._chunk_idx >= len(self._chunks):
            self._chunk_idx = 0
            if self._has_webengine:
                self.webview.page().runJavaScript("reset();")
            else:
                self.webview.clear()
            self.chunk_view.clear()
        self._running = True
        self.run_btn.setText("⏸ Pause")
        self.step_btn.setEnabled(False)
        self._timer.start(self._interval_ms)

    def _stop(self) -> None:
        self._running = False
        self._timer.stop()
        self.run_btn.setText("▶ Run")
        self.step_btn.setEnabled(True)

    def _step(self) -> None:
        if self._chunk_idx < len(self._chunks):
            self._stop()
        self._feed_next_chunk()

    def _reset(self) -> None:
        self._stop()
        self._chunk_idx = 0
        if self._has_webengine:
            self.webview.page().runJavaScript("reset();")
        else:
            self.webview.clear()
        self.chunk_view.clear()
        self._update_state_display()
        self.status_label.setText("Reset.")

    def _flush_remaining(self) -> None:
        """Push all remaining chunks at once (simulates end-of-stream)."""
        self._stop()
        remaining = self._chunks[self._chunk_idx:]
        for chunk in remaining:
            self._push_chunk(chunk)
        self._chunk_idx = len(self._chunks)
        self._update_state_display()
        self.status_label.setText(f"Flushed {len(remaining)} remaining chunks.")

    def _on_speed_changed(self, val: int) -> None:
        self._interval_ms = val
        self.speed_label.setText(f"{val}ms")
        if self._running:
            self._timer.setInterval(val)

    # ── chunk feeding ────────────────────────────────────────────────

    def _feed_next_chunk(self) -> None:
        if self._chunk_idx >= len(self._chunks):
            self._stop()
            self.status_label.setText("Stream complete.")
            return

        chunk = self._chunks[self._chunk_idx]
        self._push_chunk(chunk)
        self._chunk_idx += 1
        self._update_state_display()

    def _push_chunk(self, chunk: str) -> None:
        from PyQt6.QtGui import QTextCursor

        if self._has_webengine:
            script = f"appendText({json.dumps(chunk)}, true);"
            self.webview.page().runJavaScript(script)
        else:
            cursor = self.webview.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(chunk)

        # append to chunk view
        display = chunk.replace("\n", "⏎\n")
        cursor = self.chunk_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chunk_view.setTextCursor(cursor)
        self.chunk_view.insertPlainText(
            f"[{self._chunk_idx:03d}] {json.dumps(display)}\n"
        )
        bar = self.chunk_view.verticalScrollBar()
        if bar:
            bar.setValue(bar.maximum())

    # ── state polling ────────────────────────────────────────────────

    def _update_state_display(self) -> None:
        if not self._has_webengine:
            return
        js = "JSON.stringify({raw: rawBuffer.length, rendered: renderedLength, pending: rawBuffer.length - renderedLength})"
        self.webview.page().runJavaScript(js, self._on_state)

    def _on_state(self, state_str: str) -> None:
        if not state_str:
            return
        try:
            state = json.loads(state_str)
            self.state_label.setText(
                f"rawBuffer={state['raw']}  "
                f"renderedLength={state['rendered']}  "
                f"pending={state['pending']}  "
                f"chunk_idx={self._chunk_idx}/{len(self._chunks)}"
            )
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # dark palette
    from PyQt6.QtGui import QPalette, QColor
    p = app.palette()
    p.setColor(QPalette.ColorRole.Window, QColor(15, 23, 42))
    p.setColor(QPalette.ColorRole.WindowText, QColor(248, 250, 252))
    p.setColor(QPalette.ColorRole.Base, QColor(15, 23, 42))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(30, 41, 59))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(248, 250, 252))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(248, 250, 252))
    p.setColor(QPalette.ColorRole.Text, QColor(248, 250, 252))
    p.setColor(QPalette.ColorRole.Button, QColor(30, 41, 59))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(248, 250, 252))
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    p.setColor(QPalette.ColorRole.Highlight, QColor(37, 99, 235))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(248, 250, 252))
    app.setPalette(p)

    win = LatexStreamingTestWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
