# ytdl — YouTube Downloader

CLI that downloads YouTube videos and playlists (including private/unlisted ones via your logged-in
browser) into a folder. Built on [yt-dlp](https://github.com/yt-dlp/yt-dlp). Works on Windows, macOS and Linux.
See [PLAN.md](PLAN.md) for the roadmap.

> Only download content you own or have the right to download. YouTube's Terms of Service restrict the rest.

## Install

Requires Python 3.10+. ffmpeg is needed to merge video+audio; if none is on PATH, a bundled copy (imageio-ffmpeg) is used. A JavaScript runtime (deno, node or bun) is auto-detected for YouTube extraction.

```bash
pipx install git+ssh://git@github.com-hcung285/hcung285/yt-downloader.git   # or: pip install -e .
# ffmpeg:  winget install ffmpeg | brew install ffmpeg | sudo apt install ffmpeg
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

Behaviour:
- Finished videos are recorded in `<dest>/archive.txt` and skipped on re-runs (`--no-archive` to disable).
- Partial downloads resume. One failing video never stops the run.
- Failures are listed at the end and saved to `<dest>/failed.txt` — retry with `ytdl -f <dest>/failed.txt`.
- Exit code is 1 if anything failed, 2 on bad input.

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
pytest
```
