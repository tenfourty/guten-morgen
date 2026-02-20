#!/bin/bash
# PreToolUse hook: block edits to sensitive/managed files
# Exit 2 = block the tool call with a message

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

BASENAME=$(basename "$FILE_PATH")

# Block .env files (contain API keys)
if [[ "$BASENAME" == .env || "$BASENAME" == .env.* ]]; then
  echo "BLOCKED: $BASENAME contains secrets. Edit it manually." >&2
  exit 2
fi

# Block uv.lock (managed by uv sync)
if [[ "$BASENAME" == "uv.lock" ]]; then
  echo "BLOCKED: uv.lock is managed by uv sync. Don't edit directly." >&2
  exit 2
fi

exit 0
