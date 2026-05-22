"""Regression for the `next` builtin shadow in guten_morgen.cli.

Background: `def next(...)` at module scope (the `gm next` click command) bound the
name `next` in `guten_morgen.cli`'s globals to a click `Command` object, shadowing
the `next` builtin for any other function in the same module. Calls like
`next(iterator, default)` inside `events_update` resolved to the click Command's
`__call__`, which re-entered click's parser and failed with `TypeError: object of
type 'Event' has no len()`.

These tests pin the invariant: no top-level name in `guten_morgen.cli` may shadow
a Python builtin.
"""

from __future__ import annotations

import builtins

import guten_morgen.cli as cli_mod


def test_no_module_globals_shadow_builtins() -> None:
    """Module-level names in `guten_morgen.cli` must not shadow Python builtins.

    Click commands that share a name with a builtin must use `@cli.command("name")`
    on a differently-named Python function (e.g. `def gm_next(...)`), so the CLI
    surface stays `gm <name>` while the module global is safe.
    """
    builtin_names = {n for n in dir(builtins) if not n.startswith("_")}
    offenders = []
    for name in dir(cli_mod):
        if name.startswith("_"):
            continue
        if name in builtin_names:
            value = getattr(cli_mod, name)
            if value is not getattr(builtins, name, None):
                offenders.append((name, type(value).__name__))
    assert not offenders, (
        f"guten_morgen.cli shadows Python builtins at module scope: {offenders}. "
        f"Rename the Python function (keep the CLI name via @cli.command('<name>'))."
    )


def test_next_resolves_to_builtin_in_cli_module() -> None:
    """`next` must be the builtin when accessed via `guten_morgen.cli.next` (no override)."""
    assert getattr(cli_mod, "next", builtins.next) is builtins.next, (
        "guten_morgen.cli.next is not the builtin — a top-level def or import has shadowed it."
    )
