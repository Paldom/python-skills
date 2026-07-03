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
    if base.lower() != "skill.md":
        return 0
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

    proc = subprocess.run(
        [sys.executable, validator, "--file", file_path, "--root", project_dir],
        capture_output=True, text=True, timeout=30, cwd=project_dir,
    )
    if proc.returncode != 0:
        sys.stderr.write(
            "SKILL.md validation failed — fix these before continuing "
            "(rules: docs/skill-authoring.md):\n"
            + (proc.stderr or proc.stdout)
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
