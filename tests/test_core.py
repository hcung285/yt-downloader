from pathlib import Path

import pytest

from ytdl.auth import AuthError, cookie_opts, looks_like_auth_error
from ytdl.downloader import output_template, read_archive
from ytdl.inputs import InputError, collect_targets, parse_lines
from ytdl.report import write_failed
from ytdl.resolver import Item


def test_parse_lines_ignores_comments_and_blanks():
    lines = ["# header", "", "  https://youtu.be/a  ", "https://youtu.be/b # note", "﻿https://youtu.be/c"]
    assert parse_lines(lines) == ["https://youtu.be/a", "https://youtu.be/b", "https://youtu.be/c"]


def test_collect_dedupes_and_merges_file(tmp_path: Path):
    f = tmp_path / "l.txt"
    f.write_text("https://youtu.be/a\nhttps://youtu.be/b\n", encoding="utf-8")
    assert collect_targets(["https://youtu.be/a"], f) == ["https://youtu.be/a", "https://youtu.be/b"]


def test_collect_errors(tmp_path: Path):
    with pytest.raises(InputError):
        collect_targets([], None)
    with pytest.raises(InputError):
        collect_targets(["not a url"], None)
    with pytest.raises(InputError):
        collect_targets([], tmp_path / "missing.txt")


def test_cookie_opts(tmp_path: Path):
    assert cookie_opts(None, None) == {}
    assert cookie_opts("Chrome:Profile 1", None)["cookiesfrombrowser"][:2] == ("chrome", "Profile 1")
    with pytest.raises(AuthError):
        cookie_opts("netscape", None)
    with pytest.raises(AuthError):
        cookie_opts("chrome", tmp_path / "c.txt")
    cf = tmp_path / "c.txt"
    cf.write_text("# Netscape")
    assert cookie_opts(None, cf) == {"cookiefile": str(cf)}


def test_auth_hint():
    assert looks_like_auth_error("Sign in to confirm your age")
    assert not looks_like_auth_error("HTTP Error 404")


def test_output_template(tmp_path: Path):
    single = Item(id="x", url="u")
    assert output_template(tmp_path, single) == str(tmp_path / "%(title)s [%(id)s].%(ext)s")
    pl = Item(id="x", url="u", playlist="My 50% mix: a/b", index=3, total=120)
    t = output_template(tmp_path, pl)
    assert "%%" in t and "/" not in Path(t).parent.name and "003 - " in t


def test_archive_and_failed(tmp_path: Path):
    assert read_archive(tmp_path) == set()
    (tmp_path / "archive.txt").write_text("youtube abc\n\nyoutube def\n")
    assert read_archive(tmp_path) == {"youtube abc", "youtube def"}
    p = write_failed(tmp_path, ["u1", "u1", "u2"])
    assert p.read_text().splitlines() == ["u1", "u2"]
    assert write_failed(tmp_path, []) is None and not p.exists()
