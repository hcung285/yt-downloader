"""Command-line interface."""
from __future__ import annotations

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
from .auth import AuthError, cookie_opts
from .downloader import Downloader, has_ffmpeg
from .inputs import InputError, collect_targets
from .report import print_summary
from .resolver import resolve
from .runtime import JS_HINT, js_opts

app = typer.Typer(add_completion=False, help="Download YouTube videos and playlists.")
console = Console()


def _version(v: bool) -> None:
    if v:
        console.print(f"ytdl {__version__}")
        raise typer.Exit()


@app.command()
def main(
    urls: Annotated[list[str] | None, typer.Argument(help="Video and/or playlist URLs")] = None,
    file: Annotated[Path | None, typer.Option(
        "--file", "-f", help="Text file: one URL per line (# comments ok)")] = None,
    output: Annotated[Path, typer.Option("--output", "-o", help="Destination folder")] = Path("downloads"),
    cookies_from_browser: Annotated[str | None, typer.Option(
        "--cookies-from-browser",
        help="Use the login of a browser: chrome, firefox, edge, ... or chrome:ProfileName")] = None,
    cookies: Annotated[Path | None, typer.Option("--cookies", help="Netscape cookies.txt file")] = None,
    no_archive: Annotated[bool, typer.Option(
        "--no-archive", help="Do not skip previously downloaded videos")] = False,
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True)] = False,
) -> None:
    """Paste URLs (or use --file links.txt) and everything is downloaded into --output."""
    if not urls and file is None:
        console.print("[red]Error:[/] give at least one URL or --file links.txt  (see --help)")
        raise typer.Exit(2)
    try:
        targets = collect_targets(urls or [], file)
        auth = cookie_opts(cookies_from_browser, cookies)
    except (InputError, AuthError) as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(2)

    if not has_ffmpeg():
        console.print(
            "[yellow]ffmpeg not found[/] - many YouTube videos will fail without it. "
            "Install: winget install ffmpeg | brew install ffmpeg | apt install ffmpeg")

    js = js_opts()
    if not js:
        console.print(f"[yellow]Warning:[/] {JS_HINT}")
    auth = {**auth, **js}

    output = output.expanduser()
    progress = Progress(TextColumn("[cyan]{task.fields[name]}"), BarColumn(), DownloadColumn(),
                        TransferSpeedColumn(), TimeRemainingColumn(), console=console, transient=True)
    state = {"task": None}

    def on_progress(item, done, total):
        if state["task"] is not None:
            progress.update(state["task"], completed=done, total=total)

    dl = Downloader(output, auth, on_progress=on_progress, use_archive=not no_archive)

    results, failures = [], []
    try:
        for n, target in enumerate(targets, 1):
            console.print(f"[bold]({n}/{len(targets)})[/] Resolving {target}")
            items, fails = resolve(target, auth)
            failures += fails
            for item in items:
                label = f"[{item.index}/{item.total}] " if item.index else ""
                name = f"{label}{(item.title or item.id)[:60]}"
                with progress:
                    state["task"] = progress.add_task("", name=name, total=None)
                    result = dl.download(item)
                    state["task"] = None
                mark = {"ok": "[green]OK[/]", "skipped": "[yellow]SKIP[/]", "failed": "[red]FAIL[/]"}
                console.print(f"{mark[result.status]} {name}")
                results.append(result)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/] Re-run the same command to resume (partial files are kept).")

    raise typer.Exit(print_summary(console, results, failures, output))


if __name__ == "__main__":
    app()
