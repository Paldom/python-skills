#!/usr/bin/env bash
# Stop hook — refuse to end the turn while verification fails.
# Parity rule: an agent may only sign off a change set the repo's commit gate
# would accept. When .pre-commit-config.yaml exists this runs pre-commit
# itself on the change set — the identical gate `git commit` runs, zero drift.
# Exit 2 on Stop means "keep working". The stop_hook_active guard below is
# MANDATORY — on the retry round we re-verify but always release (exit 0):
# one blocking feedback round max, never a loop (the harness's cap of 8
# consecutive blocks stays an untouched backstop).
set -u

command -v jq >/dev/null 2>&1 || exit 0
INPUT=$(cat)
ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null) || exit 0

# block <reason> [details] — exit 2, except on the retry round: release loudly.
block() {
  if [ "$ACTIVE" = "true" ]; then
    echo "stop-verify: still failing after a fix round — releasing to avoid a loop. NOT verified: $1" >&2
    exit 0
  fi
  echo "$1" >&2
  [ -n "${2:-}" ] && echo "$2" | tail -30 >&2
  exit 2
}

if [ -f .pre-commit-config.yaml ]; then
  # The commit gate exists: run pre-commit itself, never a re-implementation.
  if command -v pre-commit >/dev/null 2>&1; then PC="pre-commit"
  elif command -v uv >/dev/null 2>&1 && uv run pre-commit --version >/dev/null 2>&1; then PC="uv run pre-commit"
  else
    block "this repo has a commit gate (.pre-commit-config.yaml) but pre-commit is not runnable. Install it (uv add --dev pre-commit && uv run pre-commit install --install-hooks) and run it on the changed files until green before finishing."
  fi
  # Change set = tracked changes vs HEAD (deletions excluded) + untracked files.
  FILES=$( { git diff --name-only --diff-filter=d HEAD -- 2>/dev/null
             git ls-files --others --exclude-standard 2>/dev/null; } | sort -u )
  [ -z "$FILES" ] && exit 0
  gate() { printf '%s\n' "$FILES" | tr '\n' '\0' | xargs -0 $PC run --files; }  # $PC unquoted on purpose
  gate >/dev/null 2>&1 && exit 0   # clean first pass
  # Auto-fix hooks exit non-zero AFTER repairing the tree; the second run is the verdict.
  OUT=$(gate 2>&1) && exit 0
  block "pre-commit would reject this change set — the same gate 'git commit' runs. Fix, or run '$PC run --files <file>...' until green:" "$OUT"
fi

# No pre-commit in this repo: ONE fast, project-specific verify command.
# Keep it seconds, not minutes — this runs at the end of every turn. The full
# suite belongs in CI.
VERIFY_CMD="uv run ruff check ."
# Examples: "make check" · "uv run pytest -q -x tests/smoke" ·
#           "uv run ruff check . && uv run mypy src/"

OUT=$($VERIFY_CMD 2>&1) || block "Verification failed ($VERIFY_CMD). Fix before finishing:" "$OUT"
exit 0
