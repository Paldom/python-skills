#!/usr/bin/env python3
"""PostToolUse hook (matcher: Edit|Write): validate a SKILL.md the instant it is written.

Exit 2 feeds stderr back to Claude as actionable feedback (the write already landed —
PostToolUse cannot undo it, only steer the next step). Anything that is not a SKILL.md
exits 0 untouched. Scoped to the single edited file: must stay sub-second.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0  # unparseable event: never block on our own bug
    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not file_path:
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if not os.path.isabs(file_path):
        file_path = os.path.join(project_dir, file_path)

    base = os.path.basename(file_path)
    # Writes to a skill's evals or references change what the validator checks
    # (eval shape, counts) — validate the owning SKILL.md for those too.
    if base.lower() != "skill.md":
        parts = os.path.normpath(file_path).split(os.sep)
        if "skills" not in parts or not (
            (base == "evals.json" and "evals" in parts) or "references" in parts
        ):
            return 0
        skill_dir = os.sep.join(parts[: len(parts) - 2])  # <skill>/evals/x or <skill>/references/x
        candidate = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(candidate):
            return 0
        file_path, base = candidate, "SKILL.md"
    if base != "SKILL.md":
        sys.stderr.write(
            f"Skill files must be named exactly SKILL.md — {base!r} will be invisible "
            "on case-sensitive filesystems (Linux/CI). Rename it.\n"
        )
        return 2
    if not os.path.isfile(file_path):
        return 0

    validator = os.path.join(project_dir, "scripts", "validate_skills.py")
    if not os.path.isfile(validator):
        return 0

    # S603: argv is a fixed list — this interpreter, a path we just confirmed is a
    # file in this repo, and the edited file's path. No shell, so nothing in
    # file_path can be interpreted as a command.
    try:
        proc = subprocess.run(
            [sys.executable, validator, "--file", file_path, "--root", project_dir],
            capture_output=True,
            text=True,
            timeout=25,  # under the 45 s wired in settings.json, so a slow run still reports
            cwd=project_dir,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        sys.stderr.write(f"validate_skill_file: validator did not run ({exc}) — NOT validated\n")
        return 0  # tooling problem, not a skill problem
    if proc.returncode != 0:
        sys.stderr.write(
            "SKILL.md validation failed — fix these before continuing "
            "(rules: docs/skill-authoring.md):\n" + (proc.stderr or proc.stdout)
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
