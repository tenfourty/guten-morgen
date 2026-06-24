#!/usr/bin/env bash
# Guard: fail if uv.lock references a non-public package index.
#
# guten-morgen is a PUBLIC repo and must resolve dependencies only against
# pypi.org / files.pythonhosted.org. A private/internal index URL in uv.lock
# leaks internal infrastructure AND breaks the lockfile for outside users.
#
# Root cause this guards against: a user-level ~/.config/uv/uv.toml index-url
# (or a UV_INDEX env var) pointing at an internal mirror silently rewrites every
# package `source` in uv.lock on the next non-frozen `uv lock` / `uv run`.
#
# Deliberately does NOT print the offending host (CI logs are public) — the fix
# is the same regardless of which internal index leaked in.
#
# Usage: scripts/check-uv-lock-registry.sh [path-to-uv.lock]
set -euo pipefail

lock="${1:-uv.lock}"
[ -f "$lock" ] || exit 0

# Every https host referenced in the lock (covers `registry = "..."` and wheel/sdist `url = "..."`).
bad="$(grep -oE 'https://[^"/]+' "$lock" \
        | sort -u \
        | grep -vxE 'https://(pypi\.org|files\.pythonhosted\.org)' || true)"

if [ -n "$bad" ]; then
  echo "ERROR: $lock references a non-public package index." >&2
  echo "Public repos must resolve only against pypi.org / files.pythonhosted.org." >&2
  echo "" >&2
  echo "Regenerate against the public index (UV_INDEX must be UNSET — UV_DEFAULT_INDEX alone is not enough):" >&2
  echo "  env -u UV_INDEX -u PIP_EXTRA_INDEX_URL UV_DEFAULT_INDEX=https://pypi.org/simple uv lock --refresh" >&2
  exit 1
fi
