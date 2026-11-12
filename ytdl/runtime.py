"""YouTube extraction needs a JavaScript runtime (yt-dlp EJS). yt-dlp only auto-enables deno,
so detect whichever of deno / node / bun / quickjs is installed and pass it explicitly."""
from __future__ import annotations

import shutil

# Preference order. quickjs binary is usually named "qjs".
_CANDIDATES = (("deno", "deno"), ("node", "node"), ("bun", "bun"), ("quickjs", "qjs"))


def detect_js_runtime() -> tuple[str, str] | None:
    """Return (yt-dlp runtime name, executable path) or None."""
    for name, exe in _CANDIDATES:
        path = shutil.which(exe)
        if path:
            return name, path
    return None


def js_opts() -> dict:
    found = detect_js_runtime()
    if not found:
        return {}
    name, path = found
    return {"js_runtimes": {name: {"path": path}}}


JS_HINT = (
    "No JavaScript runtime found (deno/node/bun). YouTube downloads may fail with "
    "'Requested format is not available'. Install one: winget install DenoLand.Deno | "
    "brew install deno | npm i -g deno (or install Node.js)."
)
