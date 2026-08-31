#!/usr/bin/env python3
"""PostToolUse hook (matcher: Edit|Write): lint a Python file the instant it is written.

Ruff at write time closes the gap between an agent finishing an edit and CI telling
it something was wrong ten minutes later. Exit 2 feeds stderr back to Claude as
actionable feedback (the write already landed — PostToolUse cannot undo it, only
steer the next step). Anything that is not a .py file exits 0 untouched.

Ruff is dev tooling, not a runtime dependency of this repo, so a machine without it
skips silently rather than nagging: the gate that matters is CI. `uvx` with the pin
comes first and a PATH `ruff` second, deliberately — ruff.toml sets
`required-version`, so a stale PATH ruff refuses to run, and reporting that as a
lint failure would be a lie about the file. Must stay sub-second, so it is scoped
to the single edited file.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

# Keep in lockstep with requirements-dev.txt and .pre-commit-config.yaml.
RUFF_PIN = "0.15.10"
TIMEOUT = 30
# ruff.toml's `required-version` makes a mismatched ruff abort. That says nothing
# about the file being edited, so it must never be reported as a lint failure.
VERSION_MISMATCH = "Required version"


def ruff_argv() -> list[str] | None:
    """The command prefix that runs the *pinned* ruff here, or None if unavailable.

    uvx first: it always resolves the pin. A PATH ruff is only a fallback because
    ruff.toml sets `required-version`, so the wrong one aborts instead of
    disagreeing with CI — see VERSION_MISMATCH below.
    """
    if shutil.which("uvx"):
        return ["uvx", "--from", f"ruff=={RUFF_PIN}", "ruff"]
    if shutil.which("ruff"):
        return ["ruff"]
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0  # unparseable event: never block on our own bug
    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not file_path.endswith(".py"):
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if not os.path.isabs(file_path):
        file_path = os.path.join(project_dir, file_path)
    if not os.path.isfile(file_path):
        return 0

    prefix = ruff_argv()
    if prefix is None:
        return 0  # ruff unavailable: CI still enforces this

    problems = []
    for args, label in (
        (["check", "--force-exclude", "--output-format=concise"], "lint"),
        (["format", "--check", "--force-exclude"], "format"),
    ):
        try:
            # S603: fixed argv — a resolved ruff, literal flags, and the edited
            # file's path in argument position. No shell.
            proc = subprocess.run(
                [*prefix, *args, file_path],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                cwd=project_dir,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return 0  # tooling problem, not a code problem
        output = (proc.stdout or proc.stderr).strip()
        if proc.returncode != 0:
            if VERSION_MISMATCH in output:
                return 0  # wrong ruff on PATH: a tooling problem, not this file's
            problems.append((label, output))

    if not problems:
        return 0

    sys.stderr.write("Ruff found problems in the file just written:\n")
    for label, detail in problems:
        sys.stderr.write(f"[{label}]\n{detail}\n")
    sys.stderr.write(
        "Fix them now — `ruff check --fix` and `ruff format` handle most. "
        "Rules live in ruff.toml; do not add a blanket noqa to get past this.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
