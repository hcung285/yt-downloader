"""Download individual items with yt-dlp: resume, archive, retries, per-item error isolation."""
from __future__ import annotations

import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yt_dlp
from yt_dlp.utils import sanitize_filename

from .auth import looks_like_auth_error
from .resolver import Item, _clean
from .settings import Settings

ARCHIVE_NAME = "archive.txt"

# progress callback: (item, downloaded_bytes, total_bytes_or_None)
ProgressCb = Callable[[Item, int, int | None], None]

# Errors worth retrying (network hiccups, throttling). Everything else fails fast.
_TRANSIENT = ("429", "too many requests", "timed out", "timeout", "connection", "temporar",
              "http error 5", "bad gateway", "reset by peer", "incompleteread", "transporterror",
              "unable to download")


@dataclass
class Result:
    item: Item
    status: str  # "ok" | "skipped" | "failed" | "cancelled"
    error: str | None = None
    auth_hint: bool = False
    attempts: int = 1


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


def find_ffprobe() -> str | None:
    """ffprobe on PATH or next to the ffmpeg we use. The bundled imageio-ffmpeg has none,
    and yt-dlp needs ffprobe to embed thumbnails/metadata/subtitles."""
    path = shutil.which("ffprobe")
    if path:
        return path
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        probe = Path(ffmpeg).with_name("ffprobe.exe" if ffmpeg.lower().endswith(".exe") else "ffprobe")
        if probe.is_file():
            return str(probe)
    return None


def is_retryable(message: str) -> bool:
    if looks_like_auth_error(message):
        return False
    m = message.lower()
    return any(t in m for t in _TRANSIENT)


def _esc(s: str) -> str:
    """Make a folder name safe and escape it for a yt-dlp output template."""
    return sanitize_filename(s, restricted=False).replace("%", "%%")


def output_template(dest: Path, item: Item, template: str) -> str:
    if item.playlist:
        width = max(2, len(str(item.total or 0)))
        return str(dest / _esc(item.playlist) / f"{item.index:0{width}d} - {template}")
    return str(dest / template)


def format_selector(quality: int | None, audio_only: bool, merge: bool) -> str:
    if audio_only:
        return "ba/b"
    cap = f"[height<={quality}]" if quality else ""
    return f"bv*{cap}+ba/b{cap}" if merge else f"b{cap}"


def postprocessors(s: Settings) -> list[dict]:
    pps: list[dict] = []
    if s.audio_only:
        pps.append({"key": "FFmpegExtractAudio", "preferredcodec": s.audio_format,
                    "preferredquality": "0"})
    if s.embed:
        pps.append({"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": True})
        pps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
        if s.subs and not s.audio_only:
            pps.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False})
        pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    return pps


def read_archive(dest: Path) -> set[str]:
    f = dest / ARCHIVE_NAME
    if not f.is_file():
        return set()
    return {ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()}


def _backoff(n: int) -> float:
    return min(2.0 ** n, 30.0)


class Downloader:
    """Thread-safe: one instance can be shared by a pool of workers."""

    def __init__(self, settings: Settings, base_opts: dict,
                 on_progress: ProgressCb | None = None, ffmpeg: str | None = None):
        self.s = settings
        self.dest = settings.output
        self.base_opts = base_opts
        self.on_progress = on_progress
        self.ffmpeg = ffmpeg if ffmpeg is not None else find_ffmpeg()
        self.merge = self.ffmpeg is not None
        self.cancel = threading.Event()
        self._lock = threading.Lock()
        self._archive = read_archive(self.dest) if settings.archive else set()

    def _opts(self, item: Item) -> dict:
        s = self.s
        opts: dict = {
            **self.base_opts,
            "outtmpl": output_template(self.dest, item, s.template),
            "format": format_selector(s.quality, s.audio_only, self.merge),
            "noplaylist": True,  # item is a single video
            "continuedl": True,
            "retries": 5,
            "fragment_retries": 5,
            "retry_sleep_functions": {"http": _backoff, "fragment": _backoff,
                                      "extractor": _backoff},
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "progress_hooks": [self._hook(item)],
        }
        if self.merge:
            if not s.audio_only:
                opts["merge_output_format"] = s.container
            opts["ffmpeg_location"] = self.ffmpeg
        if s.sleep > 0:
            opts["sleep_interval"] = s.sleep
            opts["max_sleep_interval"] = s.sleep * 2
        if s.subs and not s.audio_only:
            opts["writesubtitles"] = True
            opts["subtitleslangs"] = s.subs
            opts["subtitlesformat"] = "srt/best"
        if s.embed:
            opts["writethumbnail"] = True
        pps = postprocessors(s) if self.merge else []
        if pps:
            opts["postprocessors"] = pps
        return opts

    def _hook(self, item: Item):
        def hook(d: dict) -> None:
            if self.cancel.is_set():
                raise yt_dlp.utils.DownloadCancelled("cancelled")
            if self.on_progress and d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                self.on_progress(item, d.get("downloaded_bytes") or 0, total)

        return hook

    def _record(self, item: Item) -> None:
        if not self.s.archive:
            return
        with self._lock:
            self._archive.add(item.archive_key)
            self.dest.mkdir(parents=True, exist_ok=True)
            with (self.dest / ARCHIVE_NAME).open("a", encoding="utf-8") as f:
                f.write(item.archive_key + "\n")

    def download(self, item: Item) -> Result:
        if self.s.archive and item.archive_key in self._archive:
            return Result(item, "skipped")
        self.dest.mkdir(parents=True, exist_ok=True)
        attempt = 0
        while True:
            attempt += 1
            if self.cancel.is_set():
                return Result(item, "cancelled", attempts=attempt)
            try:
                with yt_dlp.YoutubeDL(self._opts(item)) as ydl:
                    ydl.download([item.url])
            except yt_dlp.utils.DownloadCancelled:
                return Result(item, "cancelled", attempts=attempt)
            except yt_dlp.utils.DownloadError as e:
                msg = _clean(str(e))
                if attempt <= self.s.retries and is_retryable(msg):
                    if self.cancel.wait(_backoff(attempt)):
                        return Result(item, "cancelled", attempts=attempt)
                    continue
                return Result(item, "failed", msg, auth_hint=looks_like_auth_error(msg),
                              attempts=attempt)
            except Exception as e:  # noqa: BLE001 - one bad item must never stop the batch
                return Result(item, "failed", f"{type(e).__name__}: {e}", attempts=attempt)
            self._record(item)
            return Result(item, "ok", attempts=attempt)
