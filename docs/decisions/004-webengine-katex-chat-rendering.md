# 004: WebEngine + KaTeX for Chat Rendering

**Date:** 2025 (Phase 1 MVP)

**Status:** Accepted

## Context

Chat messages from LLMs contain Markdown formatting and LaTeX mathematical expressions. The rendering must support:
- Rich Markdown (headings, bold, italic, code blocks, tables, blockquotes, links)
- LaTeX math (inline `$...$` and display `$$...$$`)
- Code syntax highlighting
- Streaming display (content arrives in chunks)

## Decision

Use **QWebEngineView** with bundled **KaTeX** and **highlight.js** assets, with a **QTextBrowser** fallback.

Two rendering paths:

| Path | Condition | Markdown | LaTeX | Highlight |
|------|-----------|----------|-------|-----------|
| WebEngine | `_HAS_WEBENGINE` + `_katex_available()` | Python `markdown` → HTML | KaTeX (client) | highlight.js |
| QTextBrowser | Fallback | Qt `setMarkdown()` | Not rendered | None |

## Rendering Pipeline (WebEngine)

```
Raw markdown (streaming chunks)
  │
  ├─ _raw_text accumulates all chunks
  │
  ▼
_markdown_to_html(_raw_text)
  ├─ Stash LaTeX blocks ($, $$, \(, \[) as HTML comments
  ├─ markdown.markdown() → HTML (extensions: fenced_code, tables, sane_lists, nl2br)
  └─ Restore LaTeX blocks (HTML-escaped)
  │
  ▼
JS setHtml(html, renderLatex)
  ├─ content.innerHTML = html
  ├─ hljs.highlightAll()
  └─ renderMathInElement() (KaTeX)
```

## Rationale

- **KaTeX**: Faster than MathJax, offline-capable, bundled as static assets
- **Python Markdown**: Full-featured, extensible, runs offline
- **WebEngine**: Full browser rendering, correct CSS cascade, JavaScript for interactive features
- **Fallback**: QTextBrowser works without WebEngine dependency, useful for environments where WebEngine is unavailable

## Streaming Strategy

Each chunk triggers a **full re-render** of the accumulated `_raw_text`. This is simpler than incremental DOM updates and avoids issues with partial Markdown constructs (e.g., unclosed code fences crossing chunk boundaries).

## Consequences

- Offline-capable: all rendering assets (KaTeX CSS/JS/fonts, highlight.js CSS/JS) are bundled
- Full re-render on each chunk may cause performance issues for very long responses (>10K chars)
- The `markdown` Python library must be installed; fallback wraps content in `<pre>` tags
- LaTeX delimiters are preserved by stashing them before Markdown conversion (prevents underscores in math from being interpreted as emphasis)
