"""Keep yt-dlp fresh: YouTube changes break old versions regularly."""
from __future__ import annotations

import subprocess
import sys
from datetime import date

import yt_dlp.version

STALE_AFTER_DAYS = 30


def yt_dlp_release_date(version: str | None = None) -> date | None:
    """yt-dlp versions look like '2026.10.26' (optionally with a '.NNNNNN' suffix)."""
    parts = (version or yt_dlp.version.__version__).split(".")
    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def stale_hint(today: date | None = None, version: str | None = None) -> str | None:
    released = yt_dlp_release_date(version)
    if released is None:
        return None
    age = ((today or date.today()) - released).days
    if age > STALE_AFTER_DAYS:
        return (f"yt-dlp is {age} days old; if downloads fail, run: ytdl --update")
    return None


def update_ytdlp() -> int:
    """Upgrade yt-dlp inside the environment ytdl is installed in. Returns the exit code."""
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
    try:
        return subprocess.run(cmd, check=False).returncode
    except OSError as e:
        print(f"Could not run pip: {e}", file=sys.stderr)
        return 1
