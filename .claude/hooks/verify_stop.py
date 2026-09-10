#!/usr/bin/env python3
"""Stop hook: refuse to end the turn while `make check` is red.

AGENTS.md names `make check` as the only gate, so an agent may sign off only what
that gate accepts — the same rule the bundled agent-guardrails skill installs in
consumer repos. Exit 2 on Stop means "keep working"; stderr carries the failing
output. The `stop_hook_active` guard is mandatory: on the retry round we
re-verify and release (exit 0) only when the failure output is unchanged — no
progress means the agent cannot fix it, so it must not loop; a changed failure
keeps blocking (the harness's cap of 8 consecutive blocks is the backstop). A clean working tree skips the run entirely — nothing changed, nothing to
verify. Budget: `make check` is sub-second here; the settings timeout is the cap.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
import sys
import tempfile

TAIL_LINES = 30
# Below the 240 s wired in settings.json, so a slow gate reports instead of
# vanishing: a hook that hits the outer timeout is silently non-blocking.
MAKE_TIMEOUT = 200


def release(message: str) -> None:
    """Exit-0 path that still reaches the transcript.

    On exit 0 Claude Code shows stderr only in its debug log; `systemMessage` on
    stdout is the documented channel for a warning the user should actually see.
    """
    sys.stderr.write(message + "\n")
    print(json.dumps({"systemMessage": message}))


def _state_file(root: str) -> str:
    key = hashlib.sha256(os.path.abspath(root).encode()).hexdigest()[:12]
    return os.path.join(tempfile.gettempdir(), f"verify_stop-{key}.txt")


def no_progress(root: str, output: str) -> bool:
    """True when this failure output equals the last blocked round's (nothing changed)."""
    digest = hashlib.sha256(
        output.encode(errors="replace")
    ).hexdigest()  # a fingerprint, not security
    path = _state_file(root)
    try:
        with open(path, encoding="utf-8") as fh:
            previous = fh.read().strip()
    except OSError:
        previous = ""
    with contextlib.suppress(OSError), open(path, "w", encoding="utf-8") as fh:
        fh.write(digest)
    return previous == digest


def clear_state(root: str) -> None:
    with contextlib.suppress(OSError):
        os.remove(_state_file(root))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0  # unparseable event: never block on our own bug
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if not os.path.isfile(os.path.join(project_dir, "Makefile")):
        return 0

    status = subprocess.run(
        ["git", "-C", project_dir, "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode == 0 and not status.stdout.strip():
        return 0  # nothing changed this session

    try:
        proc = subprocess.run(
            ["make", "-C", project_dir, "check"],
            capture_output=True,
            text=True,
            timeout=MAKE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        release(f"verify_stop: could not run `make check` ({exc}) — NOT verified")
        return 0  # tooling problem, not a repo problem: never block on it
    if proc.returncode == 0:
        clear_state(project_dir)
        return 0

    output = proc.stdout + proc.stderr
    tail = "\n".join(output.splitlines()[-TAIL_LINES:])
    if payload.get("stop_hook_active") and no_progress(project_dir, output):
        release(
            "verify_stop: `make check` is still red after a fix round — releasing to "
            "avoid a loop. NOT verified:\n" + tail
        )
        return 0
    sys.stderr.write(
        "`make check` is red — fix it before finishing (AGENTS.md: it is the only gate):\n"
        + tail
        + "\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
