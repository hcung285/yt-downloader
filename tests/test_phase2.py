from datetime import date
from pathlib import Path
from typing import ClassVar

import pytest
import yt_dlp
from typer.testing import CliRunner

from ytdl import cli, downloader
from ytdl.downloader import Downloader, format_selector, is_retryable, postprocessors
from ytdl.resolver import Item, in_ranges, parse_items
from ytdl.settings import ConfigError, Settings, build_settings, load_config
from ytdl.updater import stale_hint, yt_dlp_release_date

# ---------- settings / config ----------


def test_defaults():
    s = build_settings({}, {})
    assert (s.quality, s.audio_only, s.concurrency, s.retries, s.archive) == (None, False, 2, 3, True)


def test_cli_overrides_config():
    s = build_settings({"quality": 720, "concurrency": 4}, {"quality": 1080})
    assert (s.quality, s.concurrency) == (1080, 4)


def test_cookie_source_on_cli_replaces_config_one(tmp_path: Path):
    s = build_settings({"cookies_from_browser": "firefox"}, {"cookies": str(tmp_path / "c.txt")})
    assert s.cookies_from_browser is None and s.cookies is not None


def test_subs_accepts_string_or_list():
    assert build_settings({}, {"subs": "en, vi"}).subs == ["en", "vi"]
    assert build_settings({"subs": ["en"]}, {}).subs == ["en"]


@pytest.mark.parametrize("bad", [
    {"quality": 0}, {"container": "avi"}, {"audio_format": "ogg"}, {"concurrency": 0},
    {"concurrency": 99}, {"retries": -1}, {"sleep": -1}, {"embed": "yes"}, {"quality": True},
])
def test_invalid_settings(bad):
    with pytest.raises(ConfigError):
        build_settings({}, bad)


def test_load_config(tmp_path: Path):
    f = tmp_path / "c.toml"
    f.write_text('quality = 720\nsubs = ["en"]\noutput = "~/Videos"\n', encoding="utf-8")
    s = build_settings(load_config(f), {})
    assert s.quality == 720 and s.subs == ["en"] and "~" not in str(s.output)
    f.write_text("nonsense = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(f)
    f.write_text("= broken", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(f)
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.toml")


# ---------- format / postprocessors ----------


def test_format_selector():
    assert format_selector(None, False, True) == "bv*+ba/b"
    assert format_selector(1080, False, True) == "bv*[height<=1080]+ba/b[height<=1080]"
    assert format_selector(720, False, False) == "b[height<=720]"
    assert format_selector(720, True, True) == "ba/b"


def test_postprocessors():
    assert postprocessors(Settings()) == []
    audio = postprocessors(Settings(audio_only=True, audio_format="m4a"))
    assert audio[0]["key"] == "FFmpegExtractAudio" and audio[0]["preferredcodec"] == "m4a"
    keys = [p["key"] for p in postprocessors(Settings(embed=True, subs=["en"]))]
    assert keys == ["FFmpegMetadata", "FFmpegThumbnailsConvertor", "FFmpegEmbedSubtitle",
                    "EmbedThumbnail"]
    keys = [p["key"] for p in postprocessors(Settings(embed=True, audio_only=True, subs=["en"]))]
    assert "FFmpegEmbedSubtitle" not in keys and keys[0] == "FFmpegExtractAudio"


# ---------- playlist item ranges ----------


def test_parse_items():
    r = parse_items("1-3, 7,10-")
    assert [i for i in range(1, 13) if in_ranges(i, r)] == [1, 2, 3, 7, 10, 11, 12]
    assert in_ranges(5, None)
    for bad in ("", "a", "3-1", "0", "1-x"):
        with pytest.raises(ValueError):
            parse_items(bad)


# ---------- retries classification / updater ----------


def test_is_retryable():
    assert is_retryable("HTTP Error 429: Too Many Requests")
    assert is_retryable("Unable to download webpage: timed out")
    assert not is_retryable("Video unavailable")
    assert not is_retryable("Sign in to confirm you're not a bot")
    assert not is_retryable("Requested format is not available")


def test_updater():
    assert yt_dlp_release_date("2026.10.26.232815") == date(2026, 10, 26)
    assert yt_dlp_release_date("weird") is None
    assert stale_hint(date(2026, 11, 12), "2026.10.26") is None
    assert "--update" in stale_hint(date(2027, 1, 1), "2026.10.26")


# ---------- downloader with a fake yt-dlp ----------


class FakeYDL:
    calls: ClassVar[list[tuple[str, dict]]] = []
    # url -> exceptions (or None) to play, one per attempt
    script: ClassVar[dict[str, list]] = {}

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def download(self, urls):
        FakeYDL.calls.append((urls[0], self.opts))
        seq = FakeYDL.script.get(urls[0])
        if seq:
            err = seq.pop(0)
            if err:
                raise err


@pytest.fixture
def fake(monkeypatch):
    FakeYDL.calls, FakeYDL.script = [], {}
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(downloader, "_backoff", lambda n: 0.0)
    return FakeYDL


def mk(tmp_path, **kw):
    return Downloader(Settings(output=tmp_path, **kw), {}, ffmpeg="ffmpeg")


def test_download_ok_records_archive_and_skips_next_time(tmp_path, fake):
    item = Item(id="abc", url="https://youtu.be/abc")
    assert mk(tmp_path).download(item).status == "ok"
    assert (tmp_path / "archive.txt").read_text().splitlines() == ["youtube abc"]
    assert mk(tmp_path).download(item).status == "skipped"
    assert len(fake.calls) == 1


def test_no_archive_always_downloads(tmp_path, fake):
    item = Item(id="abc", url="u")
    d = mk(tmp_path, archive=False)
    assert d.download(item).status == "ok" and d.download(item).status == "ok"
    assert not (tmp_path / "archive.txt").exists()


def test_retries_transient_then_succeeds(tmp_path, fake):
    err = yt_dlp.utils.DownloadError("ERROR: HTTP Error 503: Service Unavailable")
    fake.script["u"] = [err, err, None]
    r = mk(tmp_path, retries=3).download(Item(id="a", url="u"))
    assert r.status == "ok" and r.attempts == 3


def test_gives_up_after_retries(tmp_path, fake):
    err = yt_dlp.utils.DownloadError("ERROR: HTTP Error 429: Too Many Requests")
    fake.script["u"] = [err] * 10
    r = mk(tmp_path, retries=2).download(Item(id="a", url="u"))
    assert r.status == "failed" and r.attempts == 3 and "429" in r.error


def test_permanent_error_fails_fast_and_flags_auth(tmp_path, fake):
    fake.script["u"] = [yt_dlp.utils.DownloadError("ERROR: Sign in to confirm your age")]
    r = mk(tmp_path, retries=5).download(Item(id="a", url="u"))
    assert r.status == "failed" and r.attempts == 1 and r.auth_hint
    assert not (tmp_path / "archive.txt").exists()  # failures are never recorded


def test_unexpected_exception_is_isolated(tmp_path, fake):
    fake.script["u"] = [RuntimeError("boom")]
    r = mk(tmp_path).download(Item(id="a", url="u"))
    assert r.status == "failed" and "boom" in r.error


def test_cancel(tmp_path, fake):
    d = mk(tmp_path)
    d.cancel.set()
    assert d.download(Item(id="a", url="u")).status == "cancelled"
    assert fake.calls == []


def test_options_passed_to_ytdlp(tmp_path, fake):
    mk(tmp_path, quality=720, subs=["en"], embed=True, sleep=2, container="mkv",
       template="%(id)s.%(ext)s").download(Item(id="a", url="u"))
    o = fake.calls[0][1]
    assert o["format"] == "bv*[height<=720]+ba/b[height<=720]"
    assert o["merge_output_format"] == "mkv" and o["ffmpeg_location"] == "ffmpeg"
    assert o["writesubtitles"] and o["subtitleslangs"] == ["en"] and o["writethumbnail"]
    assert o["sleep_interval"] == 2 and o["max_sleep_interval"] == 4
    assert o["outtmpl"].endswith("%(id)s.%(ext)s")
    assert "download_archive" not in o


# ---------- end-to-end CLI with fakes ----------


def test_cli_end_to_end_concurrent_with_failure_and_retry_file(tmp_path, fake, monkeypatch):
    items = [Item(id=f"v{i}", url=f"https://youtu.be/v{i}", title=f"T{i}") for i in range(6)]
    monkeypatch.setattr(cli, "resolve", lambda target, opts, ranges=None: (items, []))
    monkeypatch.setattr(cli, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(downloader, "find_ffmpeg", lambda: "ffmpeg")
    fake.script["https://youtu.be/v3"] = [yt_dlp.utils.DownloadError("ERROR: Private video")]
    cfg = tmp_path / "cfg.toml"
    cfg.write_text("", encoding="utf-8")
    out = tmp_path / "out"

    res = CliRunner().invoke(cli.app, ["https://example.com/list", "-o", str(out), "-c", "3",
                                       "--config", str(cfg)])
    assert res.exit_code == 1, res.output  # one failure -> exit code 1
    archived = set((out / "archive.txt").read_text().split("\n")) - {""}
    assert archived == {f"youtube v{i}" for i in range(6) if i != 3}
    assert (out / "failed.txt").read_text().strip() == "https://youtu.be/v3"

    # second run: only the failed one is attempted, now it succeeds
    res = CliRunner().invoke(cli.app, ["-f", str(out / "failed.txt"), "-o", str(out),
                                       "--config", str(cfg)])
    assert res.exit_code == 0, res.output
    assert not (out / "failed.txt").exists()


def test_cli_bad_input_exit_code():
    r = CliRunner().invoke(cli.app, ["not-a-url"])
    assert r.exit_code == 2
    r = CliRunner().invoke(cli.app, ["https://youtu.be/a", "--quality", "0"])
    assert r.exit_code == 2
    r = CliRunner().invoke(cli.app, ["https://youtu.be/a", "--items", "x"])
    assert r.exit_code == 2


def test_cli_embed_is_disabled_without_ffprobe(tmp_path, fake, monkeypatch):
    item = Item(id="a", url="https://youtu.be/a", title="T")
    monkeypatch.setattr(cli, "resolve", lambda target, opts, ranges=None: ([item], []))
    monkeypatch.setattr(cli, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(cli, "find_ffprobe", lambda: None)
    monkeypatch.setattr(downloader, "find_ffmpeg", lambda: "ffmpeg")
    cfg = tmp_path / "cfg.toml"
    cfg.write_text("", encoding="utf-8")
    res = CliRunner().invoke(cli.app, ["https://example.com/x", "-o", str(tmp_path / "o"),
                                       "--embed", "--config", str(cfg)])
    assert res.exit_code == 0, res.output
    assert "ffprobe not found" in res.output
    opts = fake.calls[0][1]
    assert "postprocessors" not in opts and "writethumbnail" not in opts
