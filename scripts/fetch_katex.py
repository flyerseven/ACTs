from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "src" / "ui" / "assets" / "katex"
FONT_DIR = ASSET_DIR / "fonts"
ASSET_DIR.mkdir(parents=True, exist_ok=True)
FONT_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist"

FILES = {
    "katex.min.css": f"{BASE}/katex.min.css",
    "katex.min.js": f"{BASE}/katex.min.js",
    "auto-render.min.js": f"{BASE}/contrib/auto-render.min.js",
}

FONTS = [
    "KaTeX_AMS-Regular.woff2",
    "KaTeX_Caligraphic-Bold.woff2",
    "KaTeX_Caligraphic-Regular.woff2",
    "KaTeX_Fraktur-Bold.woff2",
    "KaTeX_Fraktur-Regular.woff2",
    "KaTeX_Main-Bold.woff2",
    "KaTeX_Main-Italic.woff2",
    "KaTeX_Main-Regular.woff2",
    "KaTeX_Math-BoldItalic.woff2",
    "KaTeX_Math-Italic.woff2",
    "KaTeX_SansSerif-Bold.woff2",
    "KaTeX_SansSerif-Italic.woff2",
    "KaTeX_SansSerif-Regular.woff2",
    "KaTeX_Script-Regular.woff2",
    "KaTeX_Size1-Regular.woff2",
    "KaTeX_Size2-Regular.woff2",
    "KaTeX_Size3-Regular.woff2",
    "KaTeX_Size4-Regular.woff2",
    "KaTeX_Typewriter-Regular.woff2",
]

for name, url in FILES.items():
    data = urlopen(url).read()
    (ASSET_DIR / name).write_bytes(data)
    print(f"Saved {name} ({len(data)} bytes)")

for name in FONTS:
    url = f"{BASE}/fonts/{name}"
    data = urlopen(url).read()
    (FONT_DIR / name).write_bytes(data)
    print(f"Saved fonts/{name} ({len(data)} bytes)")
