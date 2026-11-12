"""Expand user targets (videos or playlists) into individual downloadable items."""
from __future__ import annotations

from dataclasses import dataclass

import yt_dlp


@dataclass
class Item:
    id: str
    url: str
    title: str | None = None
    playlist: str | None = None  # playlist title, if part of one
    index: int | None = None  # 1-based position in the full playlist
    total: int | None = None  # full playlist length
    extractor: str = "youtube"

    @property
    def archive_key(self) -> str:
        """Same format yt-dlp uses in its download archive."""
        return f"{self.extractor} {self.id}"


@dataclass
class ResolveFailure:
    target: str
    error: str


# A parsed --items spec: list of inclusive (start, end) ranges; end None = open-ended.
Ranges = list[tuple[int, int | None]]


def parse_items(spec: str) -> Ranges:
    """Parse '1-10,15,20-' into ranges (1-based, inclusive)."""
    ranges: Ranges = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, _, b = part.partition("-")
                start, end = (int(a) if a else 1), (int(b) if b else None)
            else:
                start = end = int(part)
        except ValueError:
            raise ValueError(f"Invalid --items value {part!r} (use e.g. 1-10,15,20-)") from None
        if start < 1 or (end is not None and end < start):
            raise ValueError(f"Invalid --items range {part!r}")
        ranges.append((start, end))
    if not ranges:
        raise ValueError("--items is empty")
    return ranges


def in_ranges(index: int, ranges: Ranges | None) -> bool:
    if ranges is None:
        return True
    return any(s <= index and (e is None or index <= e) for s, e in ranges)


def _clean(msg: str) -> str:
    return yt_dlp.utils.remove_terminal_sequences(msg).removeprefix("ERROR: ").strip()


def resolve(target: str, base_opts: dict,
            ranges: Ranges | None = None) -> tuple[list[Item], list[ResolveFailure]]:
    opts = {**base_opts, "extract_flat": "in_playlist", "skip_download": True,
            "quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=False)
    except yt_dlp.utils.DownloadError as e:
        return [], [ResolveFailure(target, _clean(str(e)))]
    if info is None:
        return [], [ResolveFailure(target, "No information returned")]

    if info.get("_type") != "playlist":
        return [Item(id=info["id"], url=info.get("webpage_url") or target, title=info.get("title"),
                     extractor=(info.get("extractor_key") or "youtube").lower())], []

    entries = [e for e in (info.get("entries") or []) if e]
    title = info.get("title") or info.get("id") or "playlist"
    items: list[Item] = []
    for i, e in enumerate(entries, 1):
        if not in_ranges(i, ranges):
            continue
        url = e.get("url") or e.get("webpage_url")
        if not url and e.get("id"):
            url = f"https://www.youtube.com/watch?v={e['id']}"
        if not url:
            continue
        items.append(Item(id=e.get("id") or url, url=url, title=e.get("title"),
                          playlist=title, index=i, total=len(entries),
                          extractor=(e.get("ie_key") or "youtube").lower()))
    if not items:
        why = "No playlist items match --items" if entries else \
            "Playlist is empty or not accessible (login needed?)"
        return [], [ResolveFailure(target, why)]
    return items, []
