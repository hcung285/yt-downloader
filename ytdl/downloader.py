"""Download individual items with yt-dlp: resume, archive, per-item error isolation."""
from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yt_dlp
from yt_dlp.utils import sanitize_filename

from .auth import looks_like_auth_error
from .resolver import Item, _clean

ARCHIVE_NAME = "archive.txt"
FORMAT_MERGE = "bv*+ba/b"  # best video + best audio (needs ffmpeg to merge)
FORMAT_SINGLE = "b"  # best single file (no ffmpeg needed)

# progress callback: (item, downloaded_bytes, total_bytes_or_None)
ProgressCb = Callable[[Item, int, int | None], None]


@dataclass
class Result:
    item: Item
    status: str  # "ok" | "skipped" | "failed"
    error: str | None = None
    auth_hint: bool = False


def find_ffmpeg() -> str | None:
    """ffmpeg on PATH, else the binary bundled with imageio-ffmpeg, else None."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - no bundled binary for this platform
        return None


def has_ffmpeg() -> bool:
    return find_ffmpeg() is not None


def _esc(s: str) -> str:
    """Make a folder name safe and escape it for a yt-dlp output template."""
    return sanitize_filename(s, restricted=False).replace("%", "%%")


def output_template(dest: Path, item: Item) -> str:
    name = "%(title)s [%(id)s].%(ext)s"
    if item.playlist:
        width = max(2, len(str(item.total or 0)))
        folder = _esc(item.playlist)
        return str(dest / folder / f"{item.index:0{width}d} - {name}")
    return str(dest / name)


def read_archive(dest: Path) -> set[str]:
    f = dest / ARCHIVE_NAME
    if not f.is_file():
        return set()
    return {ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()}


class Downloader:
    def __init__(self, dest: Path, base_opts: dict, on_progress: ProgressCb | None = None,
                 use_archive: bool = True):
        self.dest = dest
        self.base_opts = base_opts
        self.on_progress = on_progress
        self.use_archive = use_archive
        self.ffmpeg = find_ffmpeg()
        self.merge = self.ffmpeg is not None
        self._archive = read_archive(dest) if use_archive else set()

    def _opts(self, item: Item) -> dict:
        opts = {
            **self.base_opts,
            "outtmpl": output_template(self.dest, item),
            "format": FORMAT_MERGE if self.merge else FORMAT_SINGLE,
            "noplaylist": True,  # item is a single video
            "continuedl": True,
            "retries": 5,
            "fragment_retries": 5,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "progress_hooks": [self._hook(item)],
        }
        if self.merge:
            opts["merge_output_format"] = "mp4"
            opts["ffmpeg_location"] = self.ffmpeg
        if self.use_archive:
            opts["download_archive"] = str(self.dest / ARCHIVE_NAME)
        return opts

    def _hook(self, item: Item):
        def hook(d: dict) -> None:
            if self.on_progress and d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                self.on_progress(item, d.get("downloaded_bytes") or 0, total)

        return hook

    def download(self, item: Item) -> Result:
        if f"youtube {item.id}" in self._archive:
            return Result(item, "skipped")
        self.dest.mkdir(parents=True, exist_ok=True)
        try:
            with yt_dlp.YoutubeDL(self._opts(item)) as ydl:
                ydl.download([item.url])
        except yt_dlp.utils.DownloadError as e:
            msg = _clean(str(e))
            return Result(item, "failed", msg, auth_hint=looks_like_auth_error(msg))
        except Exception as e:  # noqa: BLE001 - one bad item must never stop the batch
            return Result(item, "failed", f"{type(e).__name__}: {e}")
        return Result(item, "ok")
