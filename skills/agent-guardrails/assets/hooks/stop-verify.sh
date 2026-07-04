#!/usr/bin/env bash
# Stop hook — refuse to end the turn while fast verification fails.
# Exit 2 on Stop means "keep working"; the harness force-overrides after 8
# consecutive blocks. The stop_hook_active guard below is MANDATORY — without
# it this hook loops the first time the agent cannot immediately fix a failure.
set -u

command -v jq >/dev/null 2>&1 || exit 0
INPUT=$(cat)
ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null) || exit 0
[ "$ACTIVE" = "true" ] && exit 0   # already re-running because of us — let go

# ONE fast, project-specific verify command. Keep it seconds, not minutes —
# this runs at the end of every turn. The full suite belongs in CI.
VERIFY_CMD="uv run ruff check ."
# Examples: "make check" · "uv run pytest -q -x tests/smoke" ·
#           "uv run ruff check . && uv run mypy src/"

OUT=$($VERIFY_CMD 2>&1) || {
  echo "Verification failed ($VERIFY_CMD). Fix before finishing:" >&2
  echo "$OUT" | tail -30 >&2
  exit 2
}

exit 0
