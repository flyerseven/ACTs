"""Tests for the streaming LaTeX parse state machine and Markdown math stash.

The JavaScript state machine in chat_widget._katex_shell_html is ported
to Python here for testability. The logic mirrors the JS implementation
exactly: same delimiter pairs, same escape rules, same boundary handling.
"""

from __future__ import annotations

import re

# ── Python port of the JS parse state machine ──────────────────────────

DELIM_PAIRS = [
    {"open": "\\[", "close": "\\]", "display": True},
    {"open": "\\(", "close": "\\)", "display": False},
    {"open": "$$", "close": "$$", "display": True},
    {"open": "$", "close": "$", "display": False},
]


def is_escaped(s: str, pos: int) -> bool:
    """Return True if the character at `pos` in `s` is escaped by an odd
    number of backslashes (mirrors JS isEscaped)."""
    bs = 0
    while pos - 1 - bs >= 0 and s[pos - 1 - bs] == "\\":
        bs += 1
    return bs % 2 == 1


def find_unmatched_open(s: str) -> int:
    """Return the position of the earliest unmatched opening delimiter in `s`,
    or -1 if all delimiters are properly closed.

    A delimiter is "unmatched" when its closing partner is never found (or
    the closing partner itself is escaped).
    """
    best_pos = -1
    for dp in DELIM_PAIRS:
        i = 0
        while i < len(s):
            idx = s.find(dp["open"], i)
            if idx == -1:
                break
            if not is_escaped(s, idx):
                close_idx = s.find(dp["close"], idx + len(dp["open"]))
                if close_idx == -1 or is_escaped(s, close_idx):
                    # unmatched open
                    if best_pos == -1 or idx < best_pos:
                        best_pos = idx
                    break
                i = close_idx + len(dp["close"])
            else:
                i = idx + len(dp["open"])
    return best_pos


class StreamingBuffer:
    """Simulates the JS rawBuffer / renderedLength / renderStep pipeline."""

    def __init__(self) -> None:
        self._raw: str = ""
        self._rendered: int = 0
        self._output: list[str] = []

    @property
    def raw(self) -> str:
        return self._raw

    @property
    def pending(self) -> str:
        """Text that has been fed but not yet rendered."""
        return self._raw[self._rendered:]

    def feed(self, chunk: str) -> list[str]:
        """Feed a chunk into the buffer. Returns a list of rendered text segments
        that are safe to display (no unmatched open delimiters)."""
        self._raw += chunk
        new_text = self._raw[self._rendered:]
        if not new_text:
            return []

        rendered: list[str] = []
        while new_text:
            open_pos = find_unmatched_open(new_text)
            if open_pos == 0:
                # The very start is an unmatched open — can't render anything
                break
            if open_pos == -1:
                # All delimiters are closed — render everything
                rendered.append(new_text)
                self._rendered += len(new_text)
                break
            if open_pos > 0:
                # Render safe prefix before the unmatched open
                rendered.append(new_text[:open_pos])
                self._rendered += open_pos
            break  # stop at first unmatched

        return rendered

    def flush(self) -> str:
        """Return all remaining text (to be rendered when stream ends)."""
        tail = self._raw[self._rendered:]
        self._rendered = len(self._raw)
        return tail


# ── Tests: escape handling ──────────────────────────────────────────────


class TestEscapeHandling:
    def test_escaped_dollar(self):
        assert is_escaped(r"\$", 1) is True

    def test_double_escaped_dollar(self):
        # \\$ — first backslash escapes second, so $ is NOT escaped
        assert is_escaped(r"\\$", 2) is False

    def test_triple_escaped_dollar(self):
        # \\\$ — odd backslashes → escaped
        assert is_escaped(r"\\\$", 3) is True

    def test_unescaped_dollar(self):
        assert is_escaped("$", 0) is False

    def test_escaped_backslash_before_dollar(self):
        # a\\$b → a, \, \, $, b
        # Positions: a=0, \=1, \=2, $=3, b=4
        # $ at position 3 has two backslashes before it → not escaped
        assert is_escaped(r"a\\$b", 3) is False

    def test_escaped_bracket_open(self):
        assert is_escaped(r"\(", 1) is True


# ── Tests: find_unmatched_open ──────────────────────────────────────────


class TestFindUnmatchedOpen:
    def test_balanced_inline_dollar(self):
        assert find_unmatched_open("$x^2$") == -1

    def test_balanced_display_dollar(self):
        assert find_unmatched_open("$$x^2$$") == -1

    def test_balanced_paren_bracket(self):
        assert find_unmatched_open(r"\(x^2\) and \[y^3\]") == -1

    def test_unmatched_open_dollar(self):
        assert find_unmatched_open("text $x^2") == 5

    def test_unmatched_display_dollar(self):
        assert find_unmatched_open("text $$x^2") == 5

    def test_unmatched_paren(self):
        assert find_unmatched_open(r"text \(x^2") == 5

    def test_unmatched_bracket(self):
        assert find_unmatched_open(r"text \[x^2") == 5

    def test_mixed_balanced(self):
        assert find_unmatched_open("$a$ and $$b$$ and \\(c\\) and \\[d\\]") == -1

    def test_first_unmatched_wins(self):
        # $ opens first, \\( also opens but later
        assert find_unmatched_open("$a \\(b") == 0

    def test_escaped_open_not_counted(self):
        assert find_unmatched_open(r"\$100") == -1

    def test_empty_string(self):
        assert find_unmatched_open("") == -1

    def test_plain_text(self):
        assert find_unmatched_open("hello world") == -1

    def test_display_math_among_text(self):
        # $$ opens at index 1
        assert find_unmatched_open("x$$y") == 1


# ── Tests: StreamingBuffer ──────────────────────────────────────────────


class TestStreamingBuffer:
    def test_plain_text_passes_through(self):
        buf = StreamingBuffer()
        result = buf.feed("hello ")
        assert result == ["hello "]
        result = buf.feed("world")
        assert result == ["world"]

    def test_complete_formula_renders(self):
        buf = StreamingBuffer()
        result = buf.feed("The formula $x^2$ is inline")
        assert "".join(result) == "The formula $x^2$ is inline"

    def test_incomplete_formula_held_back(self):
        buf = StreamingBuffer()
        result = buf.feed("Start $x^2")
        # $ opens at index 6, no close → unmatched at 6
        # So "Start " (safe prefix) renders, the rest "$x^2" is held
        assert result == ["Start "]
        assert buf.pending == "$x^2"

    def test_formula_completed_across_chunks(self):
        buf = StreamingBuffer()
        buf.feed("Start $x")
        assert buf.pending == "$x"
        # Next chunk closes the formula
        result = buf.feed("^2$ end")
        assert "".join(result) == "$x^2$ end"
        assert buf.flush() == ""

    def test_nested_dollar_in_display(self):
        # $$...$$ is display; inner $...$ should not be treated as nested
        # because once $$ opens, we look for $$ close
        buf = StreamingBuffer()
        buf.feed("$$f(x) = ")
        assert buf.pending == "$$f(x) = "
        result = buf.feed("x^2$$")
        assert "".join(result) == "$$f(x) = x^2$$"

    def test_backslash_dollar_not_a_delimiter(self):
        buf = StreamingBuffer()
        result = buf.feed(r"\$100 dollars")
        assert result == [r"\$100 dollars"]

    def test_flush_drains_remaining(self):
        buf = StreamingBuffer()
        # "incomplete $math" — $ opens at 11, no close → "incomplete " renders
        buf.feed("incomplete $math")
        # Only data that hasn't been rendered is the pending tail
        assert buf.pending == "$math"
        tail = buf.flush()
        assert tail == "$math"

    def test_empty_feed_returns_empty(self):
        buf = StreamingBuffer()
        assert buf.feed("") == []

    def test_mixed_text_and_formula(self):
        buf = StreamingBuffer()
        result = buf.feed("Hello $a+b$ world")
        assert "".join(result) == "Hello $a+b$ world"

    def test_chunk_boundary_at_delimiter(self):
        buf = StreamingBuffer()
        result = buf.feed("text $")
        assert result == ["text "]
        assert buf.pending == "$"
        result = buf.feed("x$ more")
        assert "".join(result) == "$x$ more"

    def test_multiple_incomplete(self):
        buf = StreamingBuffer()
        buf.feed("a $b $$c")
        # $ at 2 matches first $ of $$ at 5 (known edge case with $/$$ overlap).
        # $$ at 5 is the earliest truly unmatched delimiter, so safe prefix = "a $b "
        assert buf.pending == "$$c"

    def test_partial_safe_text_then_more_pending(self):
        buf = StreamingBuffer()
        buf.feed("prefix $unclosed")
        assert buf.pending == "$unclosed"
        # add more text but still no close
        result = buf.feed(" more")
        assert result == []  # nothing safe
        assert buf.pending == "$unclosed more"


# ── Tests: _markdown_to_html math stashing ───────────────────────────────

# We import the real function under test
from ui.chat_widget import _markdown_to_html


class TestMarkdownMathStashing:
    def test_inline_bracket_math_preserved(self):
        html = _markdown_to_html(r"text \(x^2\) more")
        assert r"\(x^2\)" in html

    def test_display_bracket_math_preserved(self):
        html = _markdown_to_html(r"text \[x^2\] more")
        assert r"\[x^2\]" in html

    def test_double_dollar_math_preserved(self):
        html = _markdown_to_html("text $$x^2$$ more")
        assert "$$x^2$$" in html

    def test_single_dollar_math_preserved(self):
        html = _markdown_to_html("text $x^2$ more")
        assert "$x^2$" in html

    def test_mixed_math_delimiters(self):
        html = _markdown_to_html(r"$a$ \(b\) $$c$$ \[d\]")
        assert "$a$" in html
        assert r"\(b\)" in html
        assert "$$c$$" in html
        assert r"\[d\]" in html

    def test_code_block_not_stashed_as_math(self):
        html = _markdown_to_html("```python\nx = $var\n```")
        # There's a newline between $ and var, so the single-$ regex won't match.
        # $$ would not match either. The stash should leave code blocks alone.
        assert "<code>" in html.lower() or "<pre>" in html.lower()

    def test_plain_text_passes_through(self):
        html = _markdown_to_html("hello world")
        assert "hello world" in html

    def test_no_markdown_fallback(self):
        # Force no-markdown path by temporarily removing markdown
        import ui.chat_widget as cw
        saved = cw._HAS_MARKDOWN
        cw._HAS_MARKDOWN = False
        try:
            result = cw._markdown_to_html("hello <world>")
            assert "&lt;world&gt;" in result or "&lt;" in result
        finally:
            cw._HAS_MARKDOWN = saved


# ── Tests: end-to-end save format ────────────────────────────────────────


class TestSessionSaveFormat:
    """Verify that messages with math content survive a save/load round-trip."""

    def test_math_content_roundtrip(self, tmp_path):
        import asyncio
        from pathlib import Path

        from core.session import Session
        from storage.file_store import FileStore

        store = FileStore(root_dir=Path(tmp_path))
        store.ensure_structure()

        async def _run():
            session = await Session.create(
                name="math-test",
                target_type="agent",
                target_id="test-agent",
                store=store,
            )
            await session.add_message("user", "solve $x^2 + y^2 = z^2$")
            await session.add_message("assistant", r"The formula $$\int_0^\infty e^{-x^2}dx$$ is classic.")
            await session.save()
            return session

        session = asyncio.run(_run())

        async def _load():
            return await Session.load(session.meta.id, store)

        loaded = asyncio.run(_load())
        assert len(loaded.messages) == 2
        assert "$x^2 + y^2 = z^2$" in loaded.messages[0].content
        assert r"\int_0^\infty" in loaded.messages[1].content
