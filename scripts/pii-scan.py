#!/usr/bin/env python3
"""PII denylist scan — fail if a denylisted internal/PII marker appears in files.

Canonical implementation for the dev team (kbx, guten-morgen, cc-marketplace) —
copy this file VERBATIM into each repo. Public repos: ggshield catches secrets;
this catches internal infra hosts, corporate emails, real names and private
slugs, which are NOT secrets and so slip past ggshield.

The denylist patterns are themselves sensitive, so they are NEVER stored in the
repo. Patterns are resolved from (first match wins):

  1. $PII_DENYLIST       newline- or comma-separated regexes (CI: Actions secret)
  2. $PII_DENYLIST_FILE  path to a gitignored file, one regex per line
  3. .git/pii-denylist   local per-clone fallback (inside .git, never tracked)

If none is configured the scan SKIPS (exit 0) with a notice — so it never blocks
contributors who have not set it up, and CI stays green until the PII_DENYLIST
secret is added. CI enforcement activates once the secret exists.

Matching uses Python's `re`, not shell `grep -E`: macOS BSD grep silently drops
`\b` word boundaries, so a macOS audit misses identifier-embedded terms like
`acme_dir`. Each pattern is a regex searched anywhere in the file content
(SUBSTRING match, not `\b`-bounded) and case-insensitively, so identifier-
embedded and mixed-case occurrences are caught. Some false positives are
accepted by design — under-matching is the worse failure here. Write more
specific patterns (anchors, `(?-i:...)`) in the denylist when a term over-matches.

Reports matching FILENAMES only — never the matched text, line, or pattern — so
a public CI log can't leak the PII it just caught.

stdlib only; runs on any python3 (macOS + CI ubuntu).

Usage: pii-scan.py [FILE ...]   (no args => all git-tracked files)
Exit:  0 clean or skipped · 1 denylisted marker found
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


def load_raw() -> tuple[str, bool] | None:
    """Return (raw_text, from_env) for the first configured source, else None."""
    env = os.environ.get("PII_DENYLIST")
    if env:
        return env, True
    file_env = os.environ.get("PII_DENYLIST_FILE")
    if file_env and Path(file_env).is_file():
        return Path(file_env).read_text(encoding="utf-8"), False
    git_local = Path(".git/pii-denylist")
    if git_local.is_file():
        return git_local.read_text(encoding="utf-8"), False
    return None


def parse_patterns(raw: str, from_env: bool) -> list[str]:
    # $PII_DENYLIST is comma-or-newline separated (env vars are awkward multiline);
    # file sources are one-per-line so commas survive (e.g. regex quantifiers).
    parts = re.split(r"[,\n]", raw) if from_env else raw.splitlines()
    out = []
    for part in parts:
        part = part.strip()
        if part and not part.startswith("#"):
            out.append(part)
    return out


def compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    regexes = []
    for i, pat in enumerate(patterns, start=1):
        try:
            regexes.append(re.compile(pat, re.IGNORECASE))
        except re.error:
            # Never echo the pattern itself (it is sensitive); report by index.
            print(
                f"PII scan: denylist pattern #{i} is not valid regex — skipping it.",
                file=sys.stderr,
            )
    return regexes


def target_files(argv: list[str]) -> list[str]:
    files = [a for a in argv if not a.startswith("-")]
    if files:
        return files
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout
    return [line for line in out.splitlines() if line]


def file_matches(path: str, regexes: list[re.Pattern]) -> bool:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return False
    if b"\x00" in data:  # binary file — skip
        return False
    text = data.decode("utf-8", errors="replace")
    return any(r.search(text) for r in regexes)


def main(argv: list[str]) -> int:
    raw = load_raw()
    if raw is None:
        print(
            "PII scan: no denylist configured "
            "(PII_DENYLIST / PII_DENYLIST_FILE / .git/pii-denylist) — skipping.",
            file=sys.stderr,
        )
        return 0

    regexes = compile_patterns(parse_patterns(*raw))
    if not regexes:
        print(
            "PII scan: denylist configured but no usable patterns — skipping.",
            file=sys.stderr,
        )
        return 0

    hits = sorted(
        f for f in target_files(argv) if Path(f).is_file() and file_matches(f, regexes)
    )
    if hits:
        print("ERROR: internal-marker denylist hit in:", file=sys.stderr)
        for f in hits:
            print(f"  {f}", file=sys.stderr)
        print(
            "\nRemove the internal references in the file(s) above before "
            "committing to a public repo.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
