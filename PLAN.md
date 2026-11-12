# YouTube Downloader — Plan & Tech Stack

## 1. Goals
- Paste a video or playlist URL, **or** pass a `.txt` file of URLs (videos and/or playlists) → everything downloads to a destination folder.
- Support private / unlisted / members-only / age-restricted content via the user's own logged-in account.
- Cross-platform: Windows, macOS, Linux.
- Resumable, skips already-downloaded items, keeps going when one item fails.

## 2. Key decisions

| Decision | Choice | Why |
|---|---|---|
| Download engine | **yt-dlp** (used as a Python library) | The maintained standard; handles YouTube changes, playlists, formats, subtitles, cookies, resume, archive. Do not reimplement. |
| Language | **Python 3.11+** | yt-dlp is Python; embedding it gives progress hooks and structured errors instead of parsing subprocess output. |
| Media merging | **ffmpeg** | Needed to merge best video + audio streams, embed thumbnails/metadata, convert to mp3. |
| Interface | **CLI first** (Typer + Rich), optional GUI in Phase 3 | Fastest path to a working tool; CLI fits text-file batch use. |
| Authentication | **Browser cookies** (`--cookies-from-browser`) or exported `cookies.txt` | See section 4. |
| Packaging | `pipx install` for dev use; **PyInstaller** single-file binaries per OS via GitHub Actions | Users without Python can run it. |

Rejected alternatives: Node/`ytdl-core` (less maintained, breaks often), Go/Rust rewrite (huge effort, no gain), Electron GUI first (heavy, delays value).

## 3. Usage (target UX)

```bash
ytdl "https://youtu.be/VIDEO_ID"                    # single video
ytdl "https://youtube.com/playlist?list=PL..."      # whole playlist
ytdl -f links.txt -o ~/Videos/YT                    # batch from file
ytdl -f links.txt --cookies-from-browser chrome     # private/unlisted
ytdl URL --audio-only --format mp3
ytdl URL --quality 1080 --subs en --archive
```

`links.txt` format: one URL per line; blank lines and `# comments` ignored; videos and playlists may be mixed.

Output layout (configurable template):
```
<dest>/<Playlist Title>/<NN> - <Video Title> [<id>].mp4
<dest>/<Channel or "Videos">/<Video Title> [<id>].mp4     # single videos
```

## 4. Authentication (private / unlisted)
- **Unlisted** videos need no login — the URL is enough.
- **Private / members-only / age-restricted**: use the logged-in session.
  1. **Preferred:** `--cookies-from-browser chrome|firefox|edge|brave|safari` — reads cookies from the browser profile where the user is already logged in. No password ever touches the tool.
  2. **Fallback:** `--cookies cookies.txt` (Netscape format, exported with a browser extension). Required on some setups (e.g. Chrome app-bound encryption on Windows, headless servers).
- **Not supported: email/password login.** Google blocks automated sign-in and yt-dlp no longer supports it; it would also mean storing the password. Cookies are more reliable and safer.
- Security rules: never log cookie contents, add `cookies*.txt` to `.gitignore`, document that cookie files grant full account access, warn when a cookie file is world-readable.
- Caveat: cookies expire/rotate; on auth failure print a clear "re-login in browser / re-export cookies" message.
- Legal note: only download content you own or have the right to download; YouTube ToS restricts downloading otherwise.

## 5. Architecture

```
ytdl/
  cli.py          # Typer entry point, arg parsing, rich progress
  inputs.py       # parse URL args / txt file → list of Targets, dedupe, validate
  resolver.py     # extract_flat to expand playlists → entries (id, title, url)
  downloader.py   # wraps yt_dlp.YoutubeDL, progress hooks, per-item error capture
  auth.py         # cookie source selection + validation + warnings
  config.py       # defaults + optional ~/.config/ytdl/config.toml (platformdirs)
  report.py       # end-of-run summary: ok / skipped / failed (+ failed.txt for retry)
tests/
pyproject.toml
```

Flow: inputs → resolver (expand playlists) → queue → worker pool (N concurrent, default 2–3) → downloader (resume, archive check, retries with backoff) → report.

Key behaviours:
- **Download archive** (`archive.txt` of video IDs) so re-running a list skips finished items.
- **Per-item failure isolation**: unavailable/private/deleted videos are logged, run continues, failures written to `failed.txt` for re-run.
- **Resume** partial downloads (`.part` files).
- **Rate limiting / politeness**: modest concurrency, `--sleep-interval`, retry with backoff to avoid 429s.
- **Format default**: `bv*+ba/b` → mp4/mkv merged; `--quality` caps height; `--audio-only` → m4a/mp3.
- **Extras (flags)**: subtitles, thumbnail + metadata embed, chapters, playlist range (`--items 1-10`).
- **ffmpeg handling**: detect on PATH; if missing, print per-OS install hint (or bundle via `static-ffmpeg` / `imageio-ffmpeg` in the packaged build).
- **Keeping yt-dlp fresh**: YouTube breaks extractors often → `ytdl update` command (pip upgrade of yt-dlp), and a startup hint when yt-dlp is older than ~30 days.

## 6. Tech stack summary
- Python 3.11+, `yt-dlp`, `typer`, `rich`, `platformdirs`, `tomllib` (stdlib)
- ffmpeg (external or bundled)
- Testing: `pytest`, `pytest-mock`; integration tests against short public/unlisted CC videos
- Lint/format: `ruff`; typing: `mypy` (light)
- Packaging/CI: `uv` or `pip`, GitHub Actions matrix (windows/macos/ubuntu), PyInstaller artifacts attached to Releases

## 7. Phases

**Phase 1 — MVP (CLI core)**
- Project scaffold, `pyproject.toml`
- Single URL + playlist download, destination folder, rich progress bar
- `.txt` batch input (comments, dedupe)
- Cookies from browser / cookies file → private & unlisted verified
- Archive + resume + per-item error handling + summary

**Phase 2 — Hardening & options**
- Quality/format/audio-only flags, subtitles, metadata/thumbnail embed
- Concurrency, retries/backoff, `failed.txt` retry mode
- Config file, filename templates, `ytdl update`, ffmpeg detection
- Unit + integration tests, cross-OS CI

**Phase 3 — Distribution & GUI (optional)**
- PyInstaller binaries for Win/macOS/Linux
- GUI: **local web UI** (NiceGUI or FastAPI + small frontend, opened in the browser) — shares the same core, no extra installer weight. Alternative: Textual TUI. Tauri/Electron only if a native app feel is required.
- Features: paste box, file drop, queue view, per-item progress, cookie-source picker.

## 8. Risks
| Risk | Mitigation |
|---|---|
| YouTube changes break extraction | Pin-but-update yt-dlp; `ytdl update`; clear error text |
| Cookie extraction fails (Chrome on Windows, locked DB) | cookies.txt fallback; try Firefox/Edge; close-browser hint |
| Account flagged for heavy automated use | Low concurrency, sleeps, don't use primary account for huge batches |
| 429 / bot checks | Backoff, cookies, optional PO-token / JS runtime guidance per yt-dlp docs |
| ffmpeg missing | Detection + install hint / bundling |
| Legal / ToS | README disclaimer; personal-use / owned-content intent |

## 9. Open questions (answer before / during Phase 1)
1. Is a **CLI** acceptable for v1, with a GUI later? (Recommended.)
2. Preferred output container: mp4 (compatible) vs mkv (best quality, no re-encode)?
3. Which browser are you logged in with (Chrome / Edge / Firefox)? Affects cookie method.
4. Typical size of batches (tens vs hundreds of videos)? Drives concurrency defaults.
