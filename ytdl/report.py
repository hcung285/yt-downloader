"""End-of-run summary and failed.txt for easy retry."""
from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from .downloader import Result
from .resolver import ResolveFailure

FAILED_NAME = "failed.txt"


def write_failed(dest: Path, failed_urls: list[str]) -> Path | None:
    path = dest / FAILED_NAME
    if not failed_urls:
        path.unlink(missing_ok=True)
        return None
    dest.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(dict.fromkeys(failed_urls)) + "\n", encoding="utf-8")
    return path


def print_summary(console: Console, results: list[Result], resolve_failures: list[ResolveFailure],
                  dest: Path) -> int:
    """Print summary; return process exit code (0 = no failures)."""
    ok = [r for r in results if r.status == "ok"]
    skipped = [r for r in results if r.status == "skipped"]
    failed = [r for r in results if r.status == "failed"]

    console.print()
    t = Table(title="Summary", show_header=False)
    t.add_row("Downloaded", f"[green]{len(ok)}[/]")
    t.add_row("Skipped (already downloaded)", f"[yellow]{len(skipped)}[/]")
    t.add_row("Failed", f"[red]{len(failed) + len(resolve_failures)}[/]")
    t.add_row("Destination", str(dest))
    console.print(t)

    for f in resolve_failures:
        console.print(f"[red]x[/] {f.target}\n    {f.error}")
    for r in failed:
        console.print(f"[red]x[/] {r.item.title or r.item.id} ({r.item.url})\n    {r.error}")

    if any(r.auth_hint for r in failed) or any(
        "sign in" in f.error.lower() or "private" in f.error.lower() for f in resolve_failures
    ):
        console.print(
            "\n[yellow]Looks like a login problem.[/] Use --cookies-from-browser chrome|firefox|edge "
            "(the browser must be logged in) or --cookies cookies.txt. Cookies may have expired."
        )

    urls = [r.item.url for r in failed] + [f.target for f in resolve_failures]
    path = write_failed(dest, urls)
    if path:
        console.print(f'\nFailed URLs saved to [bold]{path}[/] - retry with: ytdl -f "{path}" -o "{dest}"')
    return 1 if urls else 0
