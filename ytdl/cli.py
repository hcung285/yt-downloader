"""Command-line interface."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from . import __version__
from .auth import cookie_opts
from .downloader import Downloader, Result, find_ffmpeg, find_ffprobe
from .inputs import collect_targets
from .report import print_summary
from .resolver import Item, ResolveFailure, parse_items, resolve
from .runtime import JS_HINT, js_opts
from .settings import AUDIO_FORMATS, CONTAINERS, DEFAULT_TEMPLATE, build_settings, load_config
from .updater import stale_hint, update_ytdlp

app = typer.Typer(add_completion=False, help="Download YouTube videos and playlists.")
console = Console()

MARKS = {"ok": "[green]OK[/]", "skipped": "[yellow]SKIP[/]", "failed": "[red]FAIL[/]",
         "cancelled": "[yellow]STOP[/]"}


def _version(v: bool) -> None:
    if v:
        console.print(f"ytdl {__version__}")
        raise typer.Exit()


def _update(v: bool) -> None:
    if v:
        raise typer.Exit(update_ytdlp())


def _label(item: Item) -> str:
    pos = f"[{item.index}/{item.total}] " if item.index else ""
    return f"{pos}{(item.title or item.id)[:60]}"


@app.command()
def main(
    urls: Annotated[list[str] | None, typer.Argument(help="Video and/or playlist URLs")] = None,
    file: Annotated[Path | None, typer.Option(
        "--file", "-f", help="Text file: one URL per line (# comments ok)")] = None,
    output: Annotated[Path | None, typer.Option(
        "--output", "-o", help="Destination folder (default: ./downloads)")] = None,
    quality: Annotated[int | None, typer.Option(
        "--quality", "-q", help="Max video height in pixels, e.g. 720 or 1080 (default: best)")] = None,
    audio_only: Annotated[bool | None, typer.Option(
        "--audio-only/--no-audio-only", help="Download audio only")] = None,
    audio_format: Annotated[str | None, typer.Option(
        "--audio-format", help=f"Audio format: {', '.join(AUDIO_FORMATS)} (default: mp3)")] = None,
    container: Annotated[str | None, typer.Option(
        "--container", help=f"Video container: {', '.join(CONTAINERS)} (default: mp4)")] = None,
    subs: Annotated[str | None, typer.Option(
        "--subs", help="Subtitle languages, comma separated, e.g. en,vi")] = None,
    embed: Annotated[bool | None, typer.Option(
        "--embed/--no-embed", help="Embed thumbnail, metadata and subtitles into the file")] = None,
    concurrency: Annotated[int | None, typer.Option(
        "--concurrency", "-c", help="Parallel downloads, 1-8 (default: 2)")] = None,
    retries: Annotated[int | None, typer.Option(
        "--retries", help="Extra attempts per video on network errors (default: 3)")] = None,
    sleep: Annotated[float | None, typer.Option(
        "--sleep", help="Seconds to wait between requests, to be gentle (default: 0)")] = None,
    template: Annotated[str | None, typer.Option(
        "--template", help=f"yt-dlp filename template (default: {DEFAULT_TEMPLATE})")] = None,
    items: Annotated[str | None, typer.Option(
        "--items", help="Only these playlist positions, e.g. 1-10,15,20-")] = None,
    archive: Annotated[bool | None, typer.Option(
        "--archive/--no-archive", help="Skip previously downloaded videos (default: on)")] = None,
    cookies_from_browser: Annotated[str | None, typer.Option(
        "--cookies-from-browser",
        help="Use the login of a browser: chrome, firefox, edge, ... or chrome:ProfileName")] = None,
    cookies: Annotated[Path | None, typer.Option("--cookies", help="Netscape cookies.txt file")] = None,
    config: Annotated[Path | None, typer.Option(
        "--config", help="Config TOML file (default: per-user config dir)")] = None,
    update: Annotated[bool, typer.Option(
        "--update", callback=_update, is_eager=True, help="Upgrade yt-dlp and exit")] = False,
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True)] = False,
) -> None:
    """Paste URLs (or use --file links.txt) and everything is downloaded into --output."""
    if not urls and file is None:
        console.print("[red]Error:[/] give at least one URL or --file links.txt  (see --help)")
        raise typer.Exit(2)

    cli_values = {
        "output": output, "quality": quality, "audio_only": audio_only,
        "audio_format": audio_format, "container": container, "subs": subs, "embed": embed,
        "concurrency": concurrency, "retries": retries, "sleep": sleep, "template": template,
        "archive": archive, "cookies_from_browser": cookies_from_browser, "cookies": cookies,
    }
    overrides = {k: v for k, v in cli_values.items() if v is not None}
    try:
        ranges = parse_items(items) if items else None
        settings = build_settings(load_config(config), overrides)
        targets = collect_targets(urls or [], file)
        auth = cookie_opts(settings.cookies_from_browser, settings.cookies)
    except ValueError as e:  # InputError, AuthError, ConfigError and bad --items
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(2) from None

    if find_ffmpeg() is None:
        console.print(
            "[yellow]ffmpeg not found[/] - many YouTube videos will fail without it. "
            "Install: winget install ffmpeg | brew install ffmpeg | apt install ffmpeg")
    if settings.embed and find_ffprobe() is None:
        console.print("[yellow]ffprobe not found[/] - --embed (thumbnail/metadata/subtitle embedding) "
                      "needs a full ffmpeg install, so it is turned off for this run. "
                      "Install: winget install ffmpeg | brew install ffmpeg | apt install ffmpeg")
        settings.embed = False
    js = js_opts()
    if not js:
        console.print(f"[yellow]Warning:[/] {JS_HINT}")
    auth = {**auth, **js}
    hint = stale_hint()
    if hint:
        console.print(f"[dim]{hint}[/]")

    # 1) resolve every target into individual videos (playlists are expanded here)
    queue: list[Item] = []
    failures: list[ResolveFailure] = []
    seen: set[str] = set()
    for n, target in enumerate(targets, 1):
        console.print(f"[bold]({n}/{len(targets)})[/] Resolving {target}")
        found, fails = resolve(target, auth, ranges)
        failures += fails
        for it in found:
            if it.archive_key not in seen:  # same video listed twice: download once
                seen.add(it.archive_key)
                queue.append(it)
    if queue:
        console.print(f"Downloading {len(queue)} video(s) to [bold]{settings.output}[/] "
                      f"({settings.concurrency} at a time)")

    # 2) download them with a small worker pool
    progress = Progress(TextColumn("[cyan]{task.fields[name]}"), BarColumn(), DownloadColumn(),
                        TransferSpeedColumn(), TimeRemainingColumn(), console=console,
                        transient=True)
    tasks: dict[str, int] = {}

    def on_progress(item: Item, done: int, total: int | None) -> None:
        tid = tasks.get(item.archive_key)
        if tid is not None:
            progress.update(tid, completed=done, total=total)

    dl = Downloader(settings, auth, on_progress=on_progress)

    def work(item: Item) -> Result:
        if dl.cancel.is_set():
            return Result(item, "cancelled")
        tid = progress.add_task("", name=_label(item), total=None)
        tasks[item.archive_key] = tid
        try:
            result = dl.download(item)
        finally:
            tasks.pop(item.archive_key, None)
            progress.remove_task(tid)
        extra = f" (after {result.attempts} attempts)" if result.attempts > 1 else ""
        progress.console.print(f"{MARKS[result.status]} {_label(item)}{extra}")
        return result

    results: list[Result] = []
    interrupted = False
    pool = ThreadPoolExecutor(max_workers=settings.concurrency)
    futures = [pool.submit(work, it) for it in queue]
    try:
        with progress:
            for fut in as_completed(futures):
                results.append(fut.result())
    except KeyboardInterrupt:
        interrupted = True
        dl.cancel.set()
        console.print("\n[yellow]Stopping...[/] finishing up; partial files are kept.")
        pool.shutdown(wait=True, cancel_futures=True)
        results = [f.result() for f in futures if f.done() and not f.cancelled()]
    else:
        pool.shutdown()

    unfinished = len(queue) - sum(1 for r in results if r.status != "cancelled")
    if interrupted or unfinished:
        console.print(f"[yellow]{unfinished} video(s) not finished.[/] "
                      "Re-run the same command to continue; finished ones are skipped.")
    code = print_summary(console, [r for r in results if r.status != "cancelled"],
                         failures, settings.output)
    raise typer.Exit(130 if interrupted else code)


if __name__ == "__main__":
    app()
