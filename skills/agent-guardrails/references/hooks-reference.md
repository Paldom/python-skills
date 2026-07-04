# Claude Code hooks — mechanics reference

Contents: [Exit codes per event](#exit-codes-per-event) ·
[settings.json shape](#settingsjson-shape) · [Matchers](#matchers) ·
[The if field](#the-if-field) · [JSON decision channel](#json-decision-channel) ·
[Timeouts](#timeouts) · [Scopes and merging](#scopes-and-merging) ·
[Coverage gaps](#coverage-gaps) · [Known issues and version drift](#known-issues-and-version-drift) ·
[Debugging checklist](#debugging-checklist) · [Sources](#sources)

Everything here is subject to version drift — the hook surface has been
changing fast (third-party sources within the same two months have counted
anywhere from 4 to 32 lifecycle events). Only `PreToolUse`, `PostToolUse`,
`Stop`, and `SubagentStop` are stable enough to build on without checking.
Canonical, current truth: https://code.claude.com/docs/en/hooks

## Exit codes per event

The contract: `exit 0` proceed · `exit 2` block · **anything else =
non-blocking, logged, action proceeds** (the exit-1 footgun).

| Event | What exit 2 does | Notes |
| --- | --- | --- |
| `PreToolUse` | prevents the tool call | the only true prevention point; fires even under skip-permissions modes — hooks tighten, never loosen |
| `PostToolUse` | nothing to prevent — the tool already ran | stderr becomes corrective feedback to the agent; use for reaction, never prevention |
| `Stop` / `SubagentStop` | prevents *stopping* — forces continued work | MUST guard on `stop_hook_active` in stdin JSON; harness overrides after 8 consecutive blocks |
| `UserPromptSubmit` | blocks the prompt | stdout on exit 0 is injected into context (redaction/injection point) |
| `SessionStart` / `SessionEnd` | not blockable | context injection / cleanup only |

On `exit 2`, **stdout is discarded** — a hook that exits 2 and prints a JSON
decision loses the JSON; the reason must go to stderr.

## settings.json shape

Three levels of nesting; getting this wrong fails silently:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/lint-edited-file.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

- `$CLAUDE_PROJECT_DIR` is the documented way to reference project-relative
  scripts; literal `$HOME` in the command string may not expand — another
  silent failure.
- Handler types beyond `command`: `http` (blocks only via a 2xx response
  carrying `decision:"block"` — 4xx/5xx/timeouts degrade to non-blocking),
  `prompt` and `agent` (model-judgment handlers), `mcp_tool`. For hard policy
  use `command` hooks only: anything that can time out or disconnect fails
  open.
- Hook input arrives as JSON on stdin. The stable extraction pattern is
  `jq -r '.tool_input.file_path // empty'` (file events) and
  `jq -r '.tool_input.command // empty'` (Bash). Community-documented
  environment variables for the same data vary across versions — prefer stdin
  JSON.

## Matchers

- Case-sensitive. `bash` and `edit` match nothing, silently.
- Only letters/digits/underscore/pipe → exact tool name or `A|B` list.
  Any other character → treated as an (unanchored) regex: `Edit.*` also
  matches `NotebookEdit`; `mcp__memory` alone matches nothing — use
  `mcp__memory__.*`.
- Empty string, `*`, or omitted → matches every occurrence of the event.
- Per-event matcher targets differ: tool name for tool events; source
  (`startup`/`resume`/`clear`/`compact`) for `SessionStart`; trigger for
  `PreCompact`; notification type for `Notification`.
- Multiple matching hooks all run (in parallel); a deny does not cancel
  siblings; for PreToolUse the most restrictive merged decision wins.

## The if field

`"if": "Bash(git *)"`-style filters (permission-rule syntax) narrow tool
events without editing the script. Two hard caveats: older versions silently
ignore the field (hook then runs on every match), and the docs call the
filter **best-effort — it fails open** on commands it cannot parse. Use the
permission system, not `if`, for anything that must hold.

## JSON decision channel

The fine-grained alternative to exit codes (pick ONE channel per hook — JSON
on stdout is only read on exit 0):

- `PreToolUse`: `hookSpecificOutput.permissionDecision` of
  `allow`/`deny`/`ask`/`defer` (plus input-rewriting via `updatedInput`).
  Note `ask` is the middle ground exit codes cannot express — human sign-off.
- Other blockable events: top-level `{"decision": "block", "reason": "..."}`.
- `Stop`/`SubagentStop` can return `hookSpecificOutput.additionalContext` for
  soft steering without a hook-error label.

## Timeouts

Per-hook `"timeout"` is in seconds. Default timeouts are generous (commonly
reported as minutes for command hooks) — always set an explicit small value on
PostToolUse hooks; they run synchronously in the hot path of every matching
tool call. Keep PostToolUse work sub-second; defer heavier checks to Stop,
pre-commit, or CI.

## Scopes and merging

| File | Scope | Committed? |
| --- | --- | --- |
| `~/.claude/settings.json` | user, all projects | no |
| `.claude/settings.json` | project, whole team | yes — treat as code |
| `.claude/settings.local.json` | project, this machine | no (gitignore it) |
| managed policy | organization | admin-controlled |

All scopes merge **additively** — every matching hook from every layer runs;
a project file cannot disable a user hook. `"disableAllHooks": true` in a
settings file is the global off-switch (managed policy hooks survive it).

## Coverage gaps

- `Edit|Write` never fires for shell-driven edits (`sed -i`, `cat >`,
  heredocs). Mitigations: also match `Bash` and inspect
  `git status --porcelain`, or run a Stop-hook worktree scan once per turn.
- Subagent-dispatched tool calls can skip the parent session's PreToolUse
  hooks.
- An agent with write access to the settings file can edit its own guardrails
  — keep settings behind CODEOWNERS and treat changes as code review.
- Command-string regex guards are bypassable via aliases/functions; whitelist
  utilities rather than blacklisting patterns where it matters.
- `/rewind` checkpoints track Edit/Write only — bash file operations bypass
  the rollback net too.

## Known issues and version drift

Community-reported, some single-source — verify against your installed
version before relying on any of them; all are anthropics/claude-code issues:

- #24327 — a PreToolUse exit-2 can make the agent stop cold rather than retry
  with the error (reason to keep hard denies rare and their stderr actionable).
- #13744 — PreToolUse blocking reported working for Bash but not Write/Edit
  in some builds (single-source).
- #19009 — PostToolUse "blocking error" label shown while the edit succeeded
  anyway (by design: PostToolUse cannot block).
- #10412 — plugin-installed hooks reportedly behave differently from
  `.claude/hooks/` ones (single-source; workaround: keep scripts in
  `.claude/hooks/`).
- #55334 — reports that sync PreToolUse blocking needed
  `{"continue": false}` + exit 0 instead of exit 2 in some versions —
  conflicts with the mainline contract; test on your version.
- #34600 — intentional exit-2 blocks render as scary "errors" in the UI;
  closed not-planned; set team expectations.

## Debugging checklist

1. Run the script standalone with realistic stdin JSON; confirm the exit code
   and that the reason is on stderr.
2. `/hooks` — read-only view of what is actually configured after merging.
3. Matcher case and regex anchoring; settings nesting (three levels).
4. `jq` installed? `$CLAUDE_PROJECT_DIR` used instead of `$HOME`? Script
   executable?
5. `set -e` in a bash hook can convert an unrelated failure into a spurious
   non-zero exit — test the script under failure conditions.
6. PostToolUse may also fire when the tool call *errored* — handle
   missing/half-written files defensively.

## Sources

- Hooks reference — https://code.claude.com/docs/en/hooks
- Hooks guide — https://code.claude.com/docs/en/hooks-guide
- Exit-code footguns write-up — https://thepromptshelf.dev/blog/claude-code-hooks-complete-reference-2026/
- Matcher/`if` mechanics — https://blakecrosley.com/blog/claude-code-hooks-explained
- Reference configs — https://github.com/trailofbits/claude-code-config
