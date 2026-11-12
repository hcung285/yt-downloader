"""Cookie-based authentication (for private / members-only / age-restricted videos)."""
from __future__ import annotations

from pathlib import Path

BROWSERS = {"brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale"}


class AuthError(ValueError):
    pass


def cookie_opts(browser: str | None, cookies_file: Path | None) -> dict:
    """Return yt-dlp options for the chosen cookie source. Cookie contents are never logged."""
    if browser and cookies_file:
        raise AuthError("Use either --cookies-from-browser or --cookies, not both.")
    if cookies_file is not None:
        if not cookies_file.is_file():
            raise AuthError(f"Cookies file not found: {cookies_file}")
        return {"cookiefile": str(cookies_file)}
    if browser:
        # "chrome" or "chrome:ProfileName"
        name, _, profile = browser.partition(":")
        name = name.lower()
        if name not in BROWSERS:
            raise AuthError(f"Unsupported browser {name!r}. Choose from: {', '.join(sorted(BROWSERS))}")
        return {"cookiesfrombrowser": (name, profile or None, None, None)}
    return {}


AUTH_HINTS = (
    "sign in",
    "private video",
    "members-only",
    "confirm your age",
    "login required",
    "cookies",
)


def looks_like_auth_error(message: str) -> bool:
    m = message.lower()
    return any(h in m for h in AUTH_HINTS)
