#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash): enforce the owner-only git policy before it runs.

AGENTS.md: never `git commit` or `git push` — every change stays in the working
tree for the owner to review. A rule in prose is a wish; this hook is the contract.
Exit 2 blocks the tool call and feeds stderr back to Claude. Deny only the
deterministic, unambiguous case (a git commit/push in command position, also
inside `bash -c '...'` and behind sudo/env/time wrappers); everything else passes
through to the normal permission flow.

Scope honesty: this guards the *agent's* Bash tool as a convenience. It is not a
security boundary — humans and other processes are not covered, and the
server-side `main` ruleset (force-push and required checks) is the real gate.
"""

from __future__ import annotations

import json
import re
import shlex
import sys

OWNER_ONLY = {"commit", "push"}
OPERATORS = {";", "&&", "||", "|", "&", ";;"}
GROUPING = {"(", ")", "{", "}", "((", "))"}
WRAPPERS = {"sudo", "command", "nohup", "time", "env", "doas"}
# Shell keywords that can stand in front of a command inside one segment.
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "(", "exec"}
WRAPPER_VALUE_FLAGS = {"-u", "-g", "--user", "--group"}
GIT_VALUE_OPTS = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}


def lex(command: str) -> list[str]:
    lx = shlex.shlex(command, posix=True, punctuation_chars=True)
    lx.whitespace_split = True
    try:
        return list(lx)
    except ValueError:
        return command.split()


def segments(toks: list[str]) -> list[list[str]]:
    out: list[list[str]] = [[]]
    for t in toks:
        if t in OPERATORS or t in GROUPING or (t and set(t) <= set(";&|(){}")):
            if out[-1]:
                out.append([])
        else:
            out[-1].append(t)
    return [s for s in out if s]


def strip_wrappers(toks: list[str]) -> list[str]:
    i = 0
    while i < len(toks):
        t = toks[i]
        base = t.rsplit("/", 1)[-1]
        if t in KEYWORDS:
            i += 1
            continue
        if base in WRAPPERS:
            i += 1
            # consume the wrapper's own flags (sudo -E, env -i, sudo -u user ...)
            while i < len(toks) and (toks[i].startswith("-") or (base == "env" and "=" in toks[i])):
                i += 2 if toks[i] in WRAPPER_VALUE_FLAGS else 1
            continue
        if "=" in t and not t.startswith("-") and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1  # leading VAR=value assignment
            continue
        break
    return toks[i:]


def git_subcommand(toks: list[str]) -> str | None:
    """Return git's subcommand if this segment is a git call, else None."""
    toks = strip_wrappers(toks)
    if not toks or toks[0].rsplit("/", 1)[-1] != "git":
        return None
    j = 1
    while j < len(toks) and toks[j].startswith("-"):
        j += 2 if toks[j] in GIT_VALUE_OPTS else 1
    return toks[j] if j < len(toks) else None


def check_segment(toks: list[str]) -> str | None:
    # One level of `bash -c '...'` unwrapping (also -lc, -xec, etc.).
    inner = strip_wrappers(toks)
    if inner and inner[0].rsplit("/", 1)[-1] in SHELLS:
        for idx in range(1, len(inner)):
            t = inner[idx]
            if re.match(r"^-[a-zA-Z]+$", t) and "c" in t and idx + 1 < len(inner):
                for seg in segments(lex(inner[idx + 1])):
                    verdict = check_segment(seg)
                    if verdict:
                        return verdict
                break
    sub = git_subcommand(toks)
    if sub in OWNER_ONLY:
        return (
            f"Blocked: `git {sub}` is owner-only in this repo (AGENTS.md). Leave the "
            "change in the working tree, run `make check`, and report what changed — "
            "the owner reviews and commits."
        )
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0  # unparseable event: never block on our own bug
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command:
        return 0
    # A newline separates commands exactly like `;` — lex line by line so a
    # multi-line script cannot hide `git push` behind an innocent first line.
    for line in command.splitlines():
        for seg in segments(lex(line)):
            verdict = check_segment(seg)
            if verdict:
                sys.stderr.write(verdict + "\n")
                return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
