# ytdl — YouTube Downloader

CLI that downloads YouTube videos and playlists (including private/unlisted ones via your logged-in
browser) into a folder. Built on [yt-dlp](https://github.com/yt-dlp/yt-dlp). Works on Windows, macOS and Linux.
See [PLAN.md](PLAN.md) for the roadmap.

> Only download content you own or have the right to download. YouTube's Terms of Service restrict the rest.

## Install

Requires Python 3.11+. ffmpeg is needed to merge video+audio; if none is on PATH, a bundled copy (imageio-ffmpeg) is used. A JavaScript runtime (deno, node or bun) is auto-detected for YouTube extraction.

```bash
pipx install git+ssh://git@github.com/hcung285/yt-downloader.git   # or: pip install -e .
# full ffmpeg (recommended, needed for --embed):  winget install ffmpeg | brew install ffmpeg | sudo apt install ffmpeg
```

## Use

```bash
ytdl "https://youtu.be/VIDEO_ID" -o ~/Videos/YT          # one video
ytdl "https://www.youtube.com/playlist?list=PL..."       # a playlist
ytdl -f links.txt -o ~/Videos/YT                         # many URLs from a file
ytdl -f links.txt --cookies-from-browser chrome          # private / members-only / age-restricted
ytdl -f links.txt --cookies cookies.txt                  # same, with an exported cookies file
```

`links.txt`: one URL per line, videos and playlists can be mixed; blank lines and `# comments` are ignored.

Output: `<dest>/<Title> [id].mp4` for single videos, `<dest>/<Playlist>/<NN> - <Title> [id].mp4` for playlists.

### Options

| Option | Meaning |
|---|---|
| `-o, --output DIR` | Destination folder (default `./downloads`) |
| `-q, --quality 1080` | Cap video height in pixels (default: best) |
| `--audio-only`, `--audio-format mp3\|m4a\|opus\|flac\|wav\|aac` | Audio only (default mp3) |
| `--container mp4\|mkv` | Video container (default mp4) |
| `--subs en,vi` | Download subtitles (saved as `.srt` next to the video) |
| `--embed` | Embed thumbnail, metadata and subtitles in the file (needs full ffmpeg with ffprobe) |
| `-c, --concurrency 1-8` | Parallel downloads (default 2) |
| `--retries N` | Extra attempts per video on network errors/429, with backoff (default 3) |
| `--sleep SECONDS` | Wait between requests, to be gentle with YouTube |
| `--template TPL` | [yt-dlp filename template](https://github.com/yt-dlp/yt-dlp#output-template), e.g. `%(uploader)s - %(title)s.%(ext)s` |
| `--items 1-10,15,20-` | Only these playlist positions |
| `--no-archive` | Don't skip previously downloaded videos |
| `--cookies-from-browser`, `--cookies` | Login for private videos (see below) |
| `--config FILE` | Use a specific config file |
| `--update` | Upgrade yt-dlp (do this when downloads suddenly break) |

### Config file

Defaults can live in a TOML file so you don't repeat flags; command-line flags always win.
Location: `%LOCALAPPDATA%\ytdl\config.toml` (Windows), `~/Library/Application Support/ytdl/config.toml` (macOS),
`~/.config/ytdl/config.toml` (Linux).

```toml
output = "~/Videos/YT"
quality = 1080
concurrency = 3
subs = ["en"]
cookies_from_browser = "chrome"
# also: audio_only, audio_format, container, embed, retries, sleep, template, archive, cookies
```

### Behaviour
- Finished videos are recorded in `<dest>/archive.txt` and skipped on re-runs.
- Partial downloads resume. One failing video never stops the run.
- Network errors and rate limits (429) are retried with exponential backoff; "private", "unavailable" and login errors fail immediately.
- Failures are listed at the end and saved to `<dest>/failed.txt` — retry with `ytdl -f <dest>/failed.txt -o <dest>`.
- Ctrl+C stops cleanly; re-run the same command to continue.
- Exit code: 0 ok, 1 something failed, 2 bad input/config, 130 interrupted.
- A hint is shown when the installed yt-dlp is more than 30 days old.

## Private / unlisted videos
- **Unlisted**: the URL is enough.
- **Private / members-only / age-restricted**: log in to YouTube in your browser, then use
  `--cookies-from-browser <browser>` (chrome, firefox, edge, brave, ...; `chrome:ProfileName` for a profile).
  If the browser's cookies can't be read (e.g. Chrome on Windows), export `cookies.txt` with a browser
  extension and use `--cookies`. Password login is intentionally not supported.
- Treat cookie files like passwords: they give access to your account. `cookies*.txt` is git-ignored.

## Develop

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"   # Windows: .venv\Scripts\pip
ruff check . && pytest
```

CI runs lint and tests on Linux, macOS and Windows (Python 3.11 and 3.13).
