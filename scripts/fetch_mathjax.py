from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "src" / "ui" / "assets" / "mathjax"
ASSET_DIR.mkdir(parents=True, exist_ok=True)

FILES = {
    "tex-svg.js": "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js",
    "LICENSE": "https://cdn.jsdelivr.net/npm/mathjax@3/LICENSE",
}

for name, url in FILES.items():
    data = urlopen(url).read()
    (ASSET_DIR / name).write_bytes(data)
    print(f"Saved {name} ({len(data)} bytes)")
