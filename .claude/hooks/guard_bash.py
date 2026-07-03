#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash): block quality-gate bypasses before they run.

Exit 2 blocks the tool call and feeds stderr back to Claude. Deny only
deterministic, unambiguous violations; everything else passes through to the
normal permission flow.

Scope honesty: this guards the *agent's* Bash tool as a convenience. It is not a
security boundary — humans and other processes are not covered, and server-side
protection (a GitHub ruleset on main blocking force pushes) is the real gate.
"""
from __future__ import annotations

import json
import re
import shlex
import sys

MAIN_REF_RE = re.compile(r"(^|:)(refs/heads/)?(main|master)$")
OPERATORS = {";", "&&", "||", "|", "&", ";;"}
GROUPING = {"(", ")", "{", "}", "((", "))"}
WRAPPERS = {"sudo", "command", "nohup", "time", "env", "doas"}
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


def git_subcommand(toks: list[str]):
    """Return (subcommand, args_after_subcommand) if this segment is a git call."""
    toks = strip_wrappers(toks)
    if not toks:
        return None, []
    if toks[0].rsplit("/", 1)[-1] != "git":
        return None, []
    j = 1
    while j < len(toks) and toks[j].startswith("-"):
        j += 2 if toks[j] in GIT_VALUE_OPTS else 1
    if j >= len(toks):
        return None, []
    return toks[j], toks[j + 1 :]


def is_force_flag(t: str) -> bool:
    if t == "--force":
        return True
    return bool(re.match(r"^-[a-zA-Z]+$", t)) and "f" in t


def has_noverify(args: list[str]) -> bool:
    for t in args:
        if t == "--no-verify":
            return True
        if re.match(r"^-[a-zA-Z]+$", t) and "n" in t:
            return True
    return False


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

    sub, args = git_subcommand(toks)
    if sub == "commit" and has_noverify(args):
        return (
            "Blocked: `git commit --no-verify` (or -n) bypasses this repo's quality "
            "gates. Run `make check`, fix the failures, then commit normally."
        )
    if sub == "push":
        forced = any(is_force_flag(t) for t in args if t.startswith("-")
                     and not t.startswith("--force-with-lease")
                     and not t.startswith("--force-if-includes"))
        positionals: list[str] = []
        k = 0
        while k < len(args):
            t = args[k]
            if t in ("-o", "--push-option", "--repo", "--receive-pack", "--exec"):
                k += 2
                continue
            if t.startswith("-"):
                k += 1
                continue
            positionals.append(t)
            k += 1
        refspecs = positionals[1:]  # positionals[0] is the remote
        plus_main = any(r.startswith("+") and MAIN_REF_RE.search(r[1:]) for r in refspecs)
        target_main = any(MAIN_REF_RE.search(r.lstrip("+")) for r in refspecs)
        if plus_main or (forced and (target_main or not refspecs)):
            return (
                "Blocked: force-pushing main/master (or a force push with no explicit "
                "branch) rewrites shared history. Push a feature branch, or use "
                "--force-with-lease on a branch you own."
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
    for seg in segments(lex(command)):
        verdict = check_segment(seg)
        if verdict:
            sys.stderr.write(verdict + "\n")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
