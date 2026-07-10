#!/usr/bin/env bash
# PostToolUse hook (matcher: Edit|Write) — lint/format ONLY the file just
# edited. Exit 2 cannot undo the edit (it already happened); it feeds the
# failure back into the agent's context so it self-corrects immediately.
# Keep this sub-second: it runs synchronously on every matching tool call.
set -u

command -v jq >/dev/null 2>&1 || exit 0
FILE_PATH=$(jq -r '.tool_input.file_path // empty' 2>/dev/null) || exit 0
[ -n "$FILE_PATH" ] && [ -f "$FILE_PATH" ] || exit 0   # tool may have errored

case "$FILE_PATH" in
  *.py)
    # --fix + format: auto-repair what is mechanical, report what is not.
    OUT=$(uv run ruff check --fix "$FILE_PATH" 2>&1) || {
      echo "ruff found problems in $FILE_PATH it could not auto-fix:" >&2
      echo "$OUT" >&2
      exit 2
    }
    uv run ruff format "$FILE_PATH" >/dev/null 2>&1 || true
    ;;
  *)
    # Non-Python files (yaml/md/json/toml) are deliberately NOT checked here:
    # routing them through pre-commit costs a 1-3 s env spin-up on every edit.
    # The Stop gate covers them with the repo's own pre-commit config before
    # sign-off. If you add per-type feedback, dispatch by extension — never
    # one formatter for everything.
    ;;
esac

exit 0
