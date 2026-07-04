#!/usr/bin/env python3
"""Read-only audit of a repo's agent-guardrail setup (Claude Code hooks,
settings scopes, rules files). Never modifies anything.

Usage: python3 check_guardrails.py [--root PATH]

Exit codes: 0 = no errors (warnings allowed), 1 = defects found.
Output: one `OK|WARN|ERROR <area>: <detail>` line per finding.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

KNOWN_TOOLS = {
    "Bash", "Edit", "Write", "MultiEdit", "NotebookEdit", "Read", "Glob",
    "Grep", "WebFetch", "WebSearch", "Task", "Agent",
}
BLOCKABLE_EVENTS = {"PreToolUse", "PostToolUse", "Stop", "SubagentStop",
                    "UserPromptSubmit"}

errors = 0
warnings = 0


def report(level: str, area: str, msg: str) -> None:
    global errors, warnings
    if level == "ERROR":
        errors += 1
    elif level == "WARN":
        warnings += 1
    print(f"{level:5s} {area}: {msg}")


def check_settings_file(path: Path, root: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report("ERROR", str(path), f"unreadable or invalid JSON ({exc}) — the whole file is ignored silently")
        return
    hooks = data.get("hooks")
    if hooks is None:
        report("OK", str(path), "valid JSON, no hooks key")
        return
    if not isinstance(hooks, dict):
        report("ERROR", str(path), '"hooks" must be an object keyed by event name')
        return
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            report("ERROR", str(path), f'hooks.{event} must be a LIST of matcher groups — got {type(groups).__name__} (wrong nesting fails silently)')
            continue
        for gi, group in enumerate(groups):
            where = f"hooks.{event}[{gi}]"
            if not isinstance(group, dict) or "hooks" not in group:
                report("ERROR", str(path), f'{where} needs an inner "hooks" array (three-level nesting)')
                continue
            matcher = group.get("matcher", "")
            if isinstance(matcher, str) and matcher and re.fullmatch(r"[A-Za-z0-9_|, ]+", matcher):
                for tool in re.split(r"[|,]", matcher):
                    tool = tool.strip()
                    if tool and tool not in KNOWN_TOOLS and tool.lower() in {t.lower() for t in KNOWN_TOOLS}:
                        report("ERROR", str(path), f'{where} matcher {tool!r} — matchers are case-sensitive; this never fires (did you mean {next(t for t in KNOWN_TOOLS if t.lower() == tool.lower())!r}?)')
            for hi, h in enumerate(group.get("hooks") or []):
                if not isinstance(h, dict):
                    continue
                cmd = h.get("command", "")
                hwhere = f"{where}.hooks[{hi}]"
                if h.get("type") == "command" and cmd:
                    if "$HOME" in cmd:
                        report("WARN", str(path), f"{hwhere} uses $HOME — may not expand; use $CLAUDE_PROJECT_DIR for project scripts")
                    m = re.search(r"\$CLAUDE_PROJECT_DIR[\"']?(/[^\s\"']+)", cmd)
                    if m:
                        script = root / m.group(1).lstrip("/")
                        if not script.is_file():
                            report("ERROR", str(path), f"{hwhere} points at missing script {m.group(1)}")
                        elif not os.access(script, os.X_OK):
                            report("ERROR", str(path), f"{hwhere} script {m.group(1)} is not executable (chmod +x) — hook fails silently")
                        else:
                            check_hook_script(script, event)
                    if "timeout" not in h and event == "PostToolUse":
                        report("WARN", str(path), f"{hwhere} has no timeout — PostToolUse hooks run in the hot path; set a small explicit timeout")


def check_hook_script(script: Path, event: str) -> None:
    try:
        text = script.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    # exit 1 used where a block was clearly intended
    for lineno, line in enumerate(text.splitlines(), 1):
        if re.search(r"\bexit 1\b", line) and re.search(r"block|deny|fail|refus", text, re.I):
            report("WARN", str(script), f"line {lineno}: 'exit 1' does NOT block — only exit 2 does; anything else is logged and the action proceeds")
            break
    if event == "Stop" and "stop_hook_active" not in text:
        report("ERROR", str(script), "Stop hook without a stop_hook_active guard — this loops the first time verification cannot be fixed immediately")
    if "jq " in text and "command -v jq" not in text:
        report("WARN", str(script), "uses jq without checking it exists — on machines without jq the hook fails silently")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path.cwd())
    args = ap.parse_args()
    root = args.root.resolve()

    # settings scopes
    proj = root / ".claude" / "settings.json"
    local = root / ".claude" / "settings.local.json"
    if proj.is_file():
        check_settings_file(proj, root)
    else:
        report("WARN", str(proj), "no committed project settings — no team-shared hooks are installed")
    if local.is_file():
        check_settings_file(local, root)
        gi = root / ".gitignore"
        if not (gi.is_file() and "settings.local.json" in gi.read_text(errors="replace")):
            report("ERROR", str(local), "settings.local.json exists but is not gitignored — personal config will be committed")

    # orphaned hook scripts
    hooks_dir = root / ".claude" / "hooks"
    if hooks_dir.is_dir():
        wired = ""
        for f in (proj, local):
            if f.is_file():
                wired += f.read_text(errors="replace")
        for script in sorted(hooks_dir.iterdir()):
            if script.is_file() and script.name not in wired:
                report("WARN", str(script), "hook script present but not referenced by any settings file — dead code or missing wiring")

    # rules files
    agents = root / "AGENTS.md"
    claude = root / "CLAUDE.md"
    if agents.is_file():
        n = len(agents.read_text(errors="replace").splitlines())
        if n > 250:
            report("WARN", str(agents), f"{n} lines — rules files past ~200 lines are token overhead the model increasingly ignores; trim")
        else:
            report("OK", str(agents), f"present ({n} lines)")
        if claude.is_file() and "@AGENTS.md" not in claude.read_text(errors="replace"):
            report("WARN", str(claude), "CLAUDE.md exists but does not import AGENTS.md — two rule files will drift; make one canonical")
    elif claude.is_file():
        report("OK", str(claude), "CLAUDE.md present (consider AGENTS.md as the vendor-neutral canonical file)")
    else:
        report("WARN", str(root), "no AGENTS.md or CLAUDE.md — the agent has no repo rules at all")

    print(f"{'FAIL' if errors else 'OK'}: {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
