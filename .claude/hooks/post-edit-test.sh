#!/bin/bash
# PostToolUse hook: run related test file after editing a source file
# Maps src/morgen/<module>.py -> tests/test_<module>.py
# Maps tests/test_*.py -> runs that test file directly

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only process Python files
if [[ -z "$FILE_PATH" || "$FILE_PATH" != *.py ]]; then
  exit 0
fi

cd "$(echo "$INPUT" | jq -r '.cwd')"
BASENAME=$(basename "$FILE_PATH" .py)

# If editing a test file, run it directly
if [[ "$BASENAME" == test_* ]]; then
  uv run pytest "$FILE_PATH" -x -q 2>&1
  exit 0
fi

# If editing a source file, find the matching test file(s)
if [[ "$FILE_PATH" == *src/morgen/* ]]; then
  # cli.py -> test_cli_*.py (multiple test files)
  if [[ "$BASENAME" == "cli" ]]; then
    uv run pytest tests/test_cli_*.py -x -q 2>&1
  # conftest, __init__, __main__ — skip
  elif [[ "$BASENAME" == __* || "$BASENAME" == conftest ]]; then
    exit 0
  # Standard mapping: module.py -> test_module.py
  elif [[ -f "tests/test_${BASENAME}.py" ]]; then
    uv run pytest "tests/test_${BASENAME}.py" -x -q 2>&1
  fi
fi

exit 0
