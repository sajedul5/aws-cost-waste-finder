#!/usr/bin/env bash
# PostToolUse hook (Write|Edit): ruff format + ruff check --fix on the edited .py file.
# Reads the hook JSON from stdin. Always exits 0, so a missing ruff or jq never blocks Claude.
ruff="$CLAUDE_PROJECT_DIR/.venv/bin/ruff"
file=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)

[[ "$file" == *.py && -f "$file" && -x "$ruff" ]] || exit 0

"$ruff" format --quiet "$file" >/dev/null 2>&1
"$ruff" check --fix --quiet "$file" >/dev/null 2>&1
exit 0
