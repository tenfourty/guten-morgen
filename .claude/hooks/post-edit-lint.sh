#!/bin/bash
# PostToolUse hook: auto-lint and format Python files after Edit/Write
# Reads tool input from stdin (JSON), extracts file_path, runs ruff

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only process Python files
if [[ -z "$FILE_PATH" || "$FILE_PATH" != *.py ]]; then
  exit 0
fi

# Run ruff check (auto-fix) then format
cd "$(echo "$INPUT" | jq -r '.cwd')"
uv run ruff check --fix "$FILE_PATH" 2>&1
uv run ruff format "$FILE_PATH" 2>&1

exit 0
