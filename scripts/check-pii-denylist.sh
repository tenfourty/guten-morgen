#!/usr/bin/env bash
# Guard: fail if any internal PII marker appears in tracked/staged files.
#
# guten-morgen is PUBLIC. ggshield catches *secrets*, but internal infra hosts,
# corporate emails, and private workspace slugs are not secrets — this guard
# covers those. The denylist patterns are themselves sensitive, so they are
# NEVER stored in this repo. Provide them via (first match wins):
#
#   1) $PII_DENYLIST       newline- or comma-separated regexes
#                          (CI: inject from a repo/org Actions secret)
#   2) $PII_DENYLIST_FILE  path to a gitignored file of regexes (one per line)
#   3) .git/pii-denylist   local fallback (inside .git, never tracked by git)
#
# If no denylist is configured the guard SKIPS (exit 0) with a notice — so it
# never blocks contributors who have not set it up, and CI stays green until the
# PII_DENYLIST secret is added. CI enforcement activates once the secret exists.
#
# Reports only the FILE names that matched, never the matched text, so the
# patterns/PII never end up in (public) CI logs. Lines starting with # in the
# denylist are treated as comments.
#
# Usage: scripts/check-pii-denylist.sh [file ...]   (no args => all tracked files)
set -euo pipefail

raw=""
if [ -n "${PII_DENYLIST:-}" ]; then
  raw="$(printf '%s' "$PII_DENYLIST" | tr ',' '\n')"
elif [ -n "${PII_DENYLIST_FILE:-}" ] && [ -f "${PII_DENYLIST_FILE}" ]; then
  raw="$(cat "${PII_DENYLIST_FILE}")"
elif [ -f .git/pii-denylist ]; then
  raw="$(cat .git/pii-denylist)"
else
  echo "PII scan: no denylist configured (PII_DENYLIST / PII_DENYLIST_FILE / .git/pii-denylist) — skipping." >&2
  exit 0
fi

# Files to scan: explicit args (pre-commit passes staged files) or all tracked files.
if [ "$#" -eq 0 ]; then
  # shellcheck disable=SC2046
  set -- $(git ls-files)
fi
[ "$#" -gt 0 ] || exit 0

hit=0
while IFS= read -r pat; do
  [ -z "$pat" ] && continue
  case "$pat" in \#*) continue ;; esac
  # -l: list matching files only (never echo matched content); -I: skip binary.
  if files_hit="$(grep -lIE -e "$pat" "$@" 2>/dev/null)"; then
    if [ -n "$files_hit" ]; then
      echo "ERROR: internal-marker denylist hit in:" >&2
      echo "$files_hit" | sort -u | sed 's/^/  /' >&2
      hit=1
    fi
  fi
done <<EOF
$raw
EOF

if [ "$hit" -ne 0 ]; then
  echo "" >&2
  echo "Remove the internal references in the file(s) above before committing to a public repo." >&2
  exit 1
fi
exit 0
