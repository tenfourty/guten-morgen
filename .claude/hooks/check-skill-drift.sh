#!/bin/bash
# PostToolUse hook: when src/guten_morgen/cli.py is edited, remind to re-check
# .claude/skills/gm/SKILL.md for drift.
# Reads tool input from stdin (JSON), extracts file_path.
# Background: PR #51 (eszpee) shipped an AI-generated skill that misread the
# `--group` flag's scope. Hook is a nudge to prevent future drift between the
# CLI surface and the skill's documented contract.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [[ -z "$FILE_PATH" || "$FILE_PATH" != *"src/guten_morgen/cli.py" ]]; then
  exit 0
fi

cat <<'EOF' >&2
You edited gm's CLI. Check `.claude/skills/gm/SKILL.md` for drift — commands,
flags, output shapes, defaults, the `## Scoping axes` orthogonality contract.
Update in the same commit if drifted.
EOF

exit 0
