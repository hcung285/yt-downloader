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
    index: int | None = None  # 1-based position in playlist
    total: int | None = None  # playlist length


@dataclass
class ResolveFailure:
    target: str
    error: str


def _clean(msg: str) -> str:
    return yt_dlp.utils.remove_terminal_sequences(msg).removeprefix("ERROR: ").strip()


def resolve(target: str, base_opts: dict) -> tuple[list[Item], list[ResolveFailure]]:
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
        return [Item(id=info["id"], url=info.get("webpage_url") or target,
                     title=info.get("title"))], []

    entries = [e for e in (info.get("entries") or []) if e]
    title = info.get("title") or info.get("id") or "playlist"
    items: list[Item] = []
    for i, e in enumerate(entries, 1):
        url = e.get("url") or e.get("webpage_url")
        if not url and e.get("id"):
            url = f"https://www.youtube.com/watch?v={e['id']}"
        if not url:
            continue
        items.append(Item(id=e.get("id") or url, url=url, title=e.get("title"),
                          playlist=title, index=i, total=len(entries)))
    if not items:
        return [], [ResolveFailure(target, "Playlist is empty or not accessible (login needed?)")]
    return items, []
