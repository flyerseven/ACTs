"""Download highlight.js v11.9.0 assets for offline use via jsDelivr."""
from pathlib import Path
import urllib.request
import sys
import ssl

HLJS_VERSION = "11.9.0"
ASSETS = Path(__file__).resolve().parent.parent / "src" / "ui" / "assets" / "highlight"
ASSETS.mkdir(parents=True, exist_ok=True)

FILES = [
    (f"highlight.min.js", f"https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@{HLJS_VERSION}/build/highlight.min.js"),
    (f"github-dark.min.css", f"https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@{HLJS_VERSION}/build/styles/github-dark.min.css"),
]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

for name, url in FILES:
    dest = ASSETS / name
    print(f"Downloading {name}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            dest.write_bytes(resp.read())
        print(f"  -> {dest} ({dest.stat().st_size} bytes)")
    except Exception as e:
        print(f"  FAILED: {e}", file=sys.stderr)

print("Done.")
