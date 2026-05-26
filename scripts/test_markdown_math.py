"""Quick test to verify _markdown_to_html preserves LaTeX delimiters."""
import sys
sys.path.insert(0, "src")

from ui.chat_widget import _markdown_to_html

# Build text using chr() to avoid any escape issues
S = chr(36)   # $
B = chr(92)   # backslash

text = (
    f"Hello, here is inline math: {S}x^2 + y^2 = z^2{S}\n\n"
    f"And a display formula:\n\n"
    f"{S}{S}{B}int_0^{B}infty e^{{-x^2}} dx = {B}frac{{{B}sqrt{{{B}pi}}}}{{2}}{S}{S}\n\n"
    f"Also a matrix:\n\n"
    f"{S}{S}{B}begin{{pmatrix}} a & b {B}{B} c & d {B}end{{pmatrix}}{S}{S}\n\n"
    f"And bracket math: {B}(x+y{B}) and {B}[A{B}]"
)

print("=== INPUT TEXT ===")
print(text)
print("=== REPR ===")
print(repr(text))
print()

html = _markdown_to_html(text)
print("=== HTML OUTPUT ===")
print(html)
print()

checks = [
    ("$ delimiters present (inline)", S in html),
    ("$$ delimiters present", S + S in html),
    ("\\int present", B + "int" in html),
    ("\\frac present", B + "frac" in html),
    ("\\begin{pmatrix} present", B + "begin{pmatrix" in html),
    ("matrix & preserved (not doubled escaped)", " a &amp; b " not in html),
    ("\\( preserved", B + "(" in html),
    ("\\[ preserved", B + "[" in html),
]
for label, result in checks:
    status = "OK" if result else "FAIL"
    print(f"  [{status}] {label}")
