"""Retry callback factories for human and agent output modes."""

from __future__ import annotations

import json
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def make_agent_retry_callback() -> Callable[[int, int, int], None]:
    """Return a callback that emits compact JSON to stderr, then sleeps."""

    def callback(wait: int, attempt: int, max_retries: int) -> None:
        msg = {"retry": {"wait": wait, "attempt": attempt, "max": max_retries}}
        print(json.dumps(msg, separators=(",", ":")), file=sys.stderr)
        time.sleep(wait)

    return callback


def make_human_retry_callback() -> Callable[[int, int, int], None]:
    """Return a callback that shows a Rich countdown on stderr, then sleeps."""

    def callback(wait: int, attempt: int, max_retries: int) -> None:
        try:
            from rich.console import Console
            from rich.progress import (
                BarColumn,
                Progress,
                TextColumn,
                TimeRemainingColumn,
            )

            console = Console(stderr=True)
            with Progress(
                TextColumn(f"[yellow]\u23f3 Rate limited (attempt {attempt}/{max_retries}).[/yellow]"),
                TextColumn("[bold]Retrying in"),
                BarColumn(),
                TimeRemainingColumn(elapsed_when_finished=False),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("waiting", total=wait)
                for _ in range(wait):
                    time.sleep(1)
                    progress.advance(task)
        except Exception:
            # Fallback: plain stderr + sleep if Rich fails
            print(
                f"Rate limited. Waiting {wait}s (attempt {attempt}/{max_retries})...",
                file=sys.stderr,
            )
            time.sleep(wait)

    return callback
