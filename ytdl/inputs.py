"""Collect target URLs from CLI args and/or a text file."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


class InputError(ValueError):
    pass


def _is_url(s: str) -> bool:
    p = urlparse(s)
    return p.scheme in ("http", "https") and bool(p.netloc)


def parse_lines(lines: list[str]) -> list[str]:
    """One URL per line; blank lines and '# comments' (full-line or trailing) are ignored."""
    out: list[str] = []
    for raw in lines:
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        # allow trailing comment: "URL  # note"
        line = line.split(" #", 1)[0].strip()
        out.append(line)
    return out


def collect_targets(urls: list[str], file: Path | None) -> list[str]:
    candidates = [u.strip() for u in urls]
    if file is not None:
        if not file.is_file():
            raise InputError(f"Input file not found: {file}")
        candidates += parse_lines(file.read_text(encoding="utf-8").splitlines())
    seen: set[str] = set()
    targets: list[str] = []
    for c in candidates:
        if not c:
            continue
        if not _is_url(c):
            raise InputError(f"Not a valid http(s) URL: {c!r}")
        if c not in seen:
            seen.add(c)
            targets.append(c)
    if not targets:
        raise InputError("No URLs given. Pass URLs as arguments or use --file links.txt")
    return targets
