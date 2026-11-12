"""Settings: defaults < config.toml < command-line flags."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

import platformdirs

DEFAULT_TEMPLATE = "%(title)s [%(id)s].%(ext)s"
CONTAINERS = ("mp4", "mkv")
AUDIO_FORMATS = ("mp3", "m4a", "opus", "flac", "wav", "aac")
MAX_CONCURRENCY = 8


class ConfigError(ValueError):
    pass


@dataclass
class Settings:
    output: Path = Path("downloads")
    quality: int | None = None  # max video height, e.g. 1080; None = best
    audio_only: bool = False
    audio_format: str = "mp3"
    container: str = "mp4"
    subs: list[str] = field(default_factory=list)  # subtitle languages, e.g. ["en", "vi"]
    embed: bool = False  # embed thumbnail, metadata and subtitles into the file
    concurrency: int = 2
    retries: int = 3  # extra attempts per video for transient errors
    sleep: float = 0.0  # seconds to wait between requests (politeness)
    template: str = DEFAULT_TEMPLATE
    archive: bool = True
    cookies_from_browser: str | None = None
    cookies: Path | None = None


_TYPES: dict[str, tuple[type, ...]] = {
    "output": (str, Path), "quality": (int,), "audio_only": (bool,), "audio_format": (str,),
    "container": (str,), "subs": (str, list), "embed": (bool,), "concurrency": (int,),
    "retries": (int,), "sleep": (int, float), "template": (str,), "archive": (bool,),
    "cookies_from_browser": (str,), "cookies": (str, Path),
}


def config_path() -> Path:
    return Path(platformdirs.user_config_dir("ytdl", appauthor=False)) / "config.toml"


def load_config(path: Path | None = None) -> dict:
    """Read config.toml (default location is optional; an explicit --config must exist)."""
    p = path or config_path()
    if not p.is_file():
        if path is not None:
            raise ConfigError(f"Config file not found: {p}")
        return {}
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML in {p}: {e}") from e
    unknown = set(data) - set(_TYPES)
    if unknown:
        raise ConfigError(f"Unknown key(s) in {p}: {', '.join(sorted(unknown))}")
    return data


def _split_langs(v: str | list) -> list[str]:
    parts = v.split(",") if isinstance(v, str) else v
    return [str(p).strip() for p in parts if str(p).strip()]


def build_settings(config: dict, overrides: dict) -> Settings:
    """Merge config file and CLI overrides (CLI wins) into validated Settings."""
    merged = dict(config)
    if "cookies" in overrides or "cookies_from_browser" in overrides:
        # a cookie source on the command line replaces the one from the config file
        merged.pop("cookies", None)
        merged.pop("cookies_from_browser", None)
    merged.update(overrides)

    s = Settings()
    valid = {f.name for f in fields(Settings)}
    for key, val in merged.items():
        if key not in valid:
            raise ConfigError(f"Unknown setting: {key}")
        # bool is a subclass of int, so reject it explicitly for numeric settings
        ok = isinstance(val, _TYPES[key]) and not (isinstance(val, bool) and bool not in _TYPES[key])
        if not ok:
            raise ConfigError(f"Setting {key!r} has the wrong type: {val!r}")
        setattr(s, key, val)

    s.output = Path(s.output).expanduser()
    s.cookies = Path(s.cookies).expanduser() if s.cookies else None
    s.subs = _split_langs(s.subs)
    s.audio_format = s.audio_format.lower()
    s.container = s.container.lower()

    if s.quality is not None and s.quality < 1:
        raise ConfigError("quality must be a positive number of pixels, e.g. 720 or 1080")
    if s.container not in CONTAINERS:
        raise ConfigError(f"container must be one of: {', '.join(CONTAINERS)}")
    if s.audio_format not in AUDIO_FORMATS:
        raise ConfigError(f"audio_format must be one of: {', '.join(AUDIO_FORMATS)}")
    if not 1 <= s.concurrency <= MAX_CONCURRENCY:
        raise ConfigError(f"concurrency must be between 1 and {MAX_CONCURRENCY}")
    if s.retries < 0:
        raise ConfigError("retries must be 0 or more")
    if s.sleep < 0:
        raise ConfigError("sleep must be 0 or more")
    return s
