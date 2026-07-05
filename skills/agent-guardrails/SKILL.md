---
name: agent-guardrails
description: Installs agentic guardrails into a Python repo — Claude Code hooks with the exit-code contract, settings wiring, AGENTS.md/CLAUDE.md rules files, vetted public skills — and troubleshoots hooks that don't fire or block. Use for 'add Claude Code hooks', 'write an AGENTS.md', 'make this repo agent-ready', 'agent keeps bypassing checks'. Not for git pre-commit hooks or validating LLM output.
license: MIT
---

# agent-guardrails

Install the agent-facing enforcement layer of a Python repo: Claude Code hooks
that give a coding agent instant, deterministic feedback (and hard-block the
few things it must never do), the settings wiring that ships them, a concise
rules file, and vetted public skills. The failure this skill fixes is
advisory-only guardrails — rules the model forgets under context pressure,
hooks that silently never fire, and `exit 1` "blocks" that block nothing.

## When NOT to use

- Git hooks — `.pre-commit-config.yaml`, commit-msg/pre-push stages. The
  python-precommit skill, if installed, owns the commit-time layer.
- CI workflows, required checks, branch rulesets — the python-ci skill. CI is
  the authoritative gate this skill's layers feed into, not what it installs.
- Validating LLM *output data* — Pydantic/Instructor schema validation,
  retry-with-error-context, SQL safety validators. That is runtime data
  validation in your application, not repo guardrails; this skill does not
  cover it.
- Tuning what the checks themselves do — ruff rules (python-lint), type
  checker config (python-typing), test infra (python-testing). This skill
  wires *when* checks run against agent actions, not their contents.
- Generic prompt engineering or system-prompt writing.

## The layer model (read this first)

Guardrails only work layered; each layer catches what the previous cannot
(convention, not an official spec — but it is strong cross-source consensus):

| Layer | Runs | Catches | Bypassable? |
| --- | --- | --- | --- |
| Rules file (AGENTS.md/CLAUDE.md) | read at session start | conventions, commands | yes — advice the model can forget |
| Claude Code hooks | at the moment of each agent action | bad writes/commands *before or as they happen* | yes — local, user-controlled |
| pre-commit | at commit | whole-diff issues | yes — `--no-verify` |
| CI + rulesets | at merge | everything, on infra the agent doesn't control | no — the only real gate |

Two consequences to state to the user every time: **anything that must always
happen belongs in a hook, not prose** (rules files are wishes; hooks are
contracts the harness executes), and **hooks are never the security
boundary** — a determined agent can be dispatched around them (subagents,
`bash` instead of Edit), so CI and server-side rules stay authoritative.
Hooks' one unique power: PreToolUse denial happens *before the file ever
exists on disk* — the only layer that can do prevention rather than cleanup.

## Workflow

### 1. Audit what exists

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/check_guardrails.py" --root .
```

Read-only: reports settings files and scopes, wired hooks and their matchers,
rules files and their length, obvious defects (lowercase matchers, `exit 1`
used as a block, missing script files, unguarded Stop hooks). Also check
`claude --version` — hook behavior has version drift; the current docs are
the source of truth: https://code.claude.com/docs/en/hooks

### 2. Rules file — context, not enforcement

Write (or trim) `AGENTS.md` at the repo root, with `CLAUDE.md` containing only
`@AGENTS.md` so every agent reads one canonical file. Start from
[assets/AGENTS.md.template](assets/AGENTS.md.template). Rules that earn their
place in a Python repo:

- exact commands, not prose — `uv sync`, `uv run pytest`,
  `uv run ruff check --fix`, `uv run mypy src/`
- "Use uv, never pip or poetry" (the single most-reported agent failure:
  defaulting to global pip installs)
- "Run lint + typecheck + tests before calling a task done"
- "Never weaken a gate to pass it — no lowering coverage, skipping tests, or
  `|| true`" (agents under pressure take the cheapest path to green)
- blast-radius lines: "flag changes to auth, dependencies, or lockfiles for
  human review"

Keep it under ~200 lines and hand-curated: auto-generated context files have
measurably *hurt* agent success in evaluations — write what is specific to
this repo, not a generic overview. Recurring PR-review corrections are the
best source of new lines.

### 3. Hooks — the deterministic layer

Copy the three hook scripts from [assets/hooks/](assets/hooks/) into
`.claude/hooks/`, make them executable, then wire
[assets/settings.json.template](assets/settings.json.template) into
`.claude/settings.json`. The architecture is thin JSON, heavy script: the
settings file only routes events; logic lives in versioned scripts.

| Goal | Event + matcher | Script |
| --- | --- | --- |
| Block dangerous bash (`--no-verify`, force-push main, bare pip) | `PreToolUse` on `Bash` | `guard-bash.sh` |
| Instant lint/format feedback on the file just edited | `PostToolUse` on `Edit\|Write` | `lint-edited-file.sh` |
| Don't stop while verification fails | `Stop` | `stop-verify.sh` |

The exit-code contract — the part everyone gets wrong:

- **`exit 0`** — proceed (stdout may carry JSON decisions).
- **`exit 2`** — the ONLY blocking exit code. Reason goes to **stderr**
  (stdout is discarded on exit 2). What "block" means is event-dependent:
  PreToolUse prevents the call; PostToolUse cannot undo — stderr is feedback
  only; Stop *prevents stopping* and forces the agent to keep working.
- **`exit 1` (or any other code) — non-blocking.** Logged, ignored, the
  action proceeds. This single fact breaks a large share of hook setups.

Rules for hooks that survive contact with a team:

- Scope PostToolUse to the single edited file and keep it sub-second — it
  runs synchronously on every matching call. Anything slower (mypy, tests)
  belongs in the Stop hook, pre-commit, or CI.
- Stop hooks MUST check `stop_hook_active` in the stdin JSON and exit 0 when
  set, or they loop; the harness force-overrides after 8 consecutive blocks.
- Matchers are case-sensitive exact names or regex: `bash` never matches
  `Bash`; `Edit.*` also catches `NotebookEdit` — use `Edit|Write`.
- `Edit|Write` misses shell-driven edits (`sed -i`, heredocs). Cover the gap
  with the Stop-hook verification pass, which sees the whole worktree.
- Hard-deny (`exit 2`) only deterministic, unambiguous violations; prefer
  non-blocking feedback for style-level issues — an over-eager PreToolUse
  block can stall the agent entirely instead of guiding it.
- Roll out observe → warn → enforce: log-only first, then narrow denies for
  patterns that caused real damage.

Full mechanics (per-event exit-2 semantics, matcher and `if`-field rules, JSON
decision channels, scopes, known version-drift issues):
[references/hooks-reference.md](references/hooks-reference.md).
Which check belongs at which layer:
[references/layer-assignment.md](references/layer-assignment.md).

### 4. Settings scopes and permissions

- `.claude/settings.json` — committed, applies to every contributor. This is
  the team contract; changes to it deserve PR-level scrutiny (see security
  below).
- `.claude/settings.local.json` — gitignored, personal experiments.
- `~/.claude/settings.json` — user-global. All scopes merge additively; a
  project file cannot switch off a user hook, only add.
- Hooks tighten policy but do not replace the permission system: a hook
  `exit 0` does not approve anything, and the `if` filter is best-effort and
  fails open on ambiguous commands. Hard allow/deny of tools belongs in
  `permissions` rules; hooks add checks the permission grammar cannot express.

### 5. Install and vet public skills

Recommend established public skills instead of rebuilding them — but treat
every third-party skill, plugin, and MCP server as an unreviewed dependency
with full user permissions. Minimum vet before install: read the plugin
manifest (an `mcpServers` entry means network access), every hook it ships and
the commands they run, and each full SKILL.md body; check requested
permissions are proportional to the stated function; pin versions and review
updates like dependency bumps. Curated starting points and the full checklist:
[references/vetting-skills-and-plugins.md](references/vetting-skills-and-plugins.md).

### 6. Verify by tripping every wire

A guardrail that has never fired is unverified. Test each one deliberately:

```bash
# 1. Scripts standalone, with realistic stdin — check exit code + stderr
echo '{"tool_input":{"command":"git commit --no-verify -m x"}}' \
  | .claude/hooks/guard-bash.sh; echo "exit=$?"        # expect exit=2
echo '{"tool_input":{"command":"git status"}}' \
  | .claude/hooks/guard-bash.sh; echo "exit=$?"        # expect exit=0
# 2. Audit passes
python3 "${CLAUDE_SKILL_DIR}/scripts/check_guardrails.py" --root .
```

Then, in a live session: ask the agent to do a blocked action (expect a
blocked call with the reason), edit a file with a deliberate lint error
(expect hook feedback), and end a turn with a failing check (expect the Stop
gate to push back). If a hook doesn't fire: matcher case, settings nesting,
`jq` present on the machine, and script executable bit — in that order.

## Output spec

Done means:

- `AGENTS.md` (≲200 lines, repo-specific) with `CLAUDE.md` importing it.
- `.claude/settings.json` wiring PreToolUse guard, PostToolUse single-file
  check, and a Stop verification gate; scripts in `.claude/hooks/`,
  executable, blocking only via exit 2 + stderr, Stop guarded by
  `stop_hook_active`.
- Every hook demonstrated to fire and to block (step 6 transcript).
- `scripts/check_guardrails.py` exits 0.
- The user told, in one sentence each: hooks are convenience, CI is the gate;
  and committed hooks execute on every contributor's machine.

## Failure modes & gotchas

| Symptom | Cause / fix |
| --- | --- |
| Hook "blocks" but the action proceeds | `exit 1` — only exit 2 blocks; everything else is logged and ignored |
| Block reason never shown to the agent | reason printed to stdout — on exit 2 stdout is discarded; use stderr |
| Hook never fires | case-sensitive matcher (`bash`≠`Bash`), wrong settings nesting, missing `jq`, unexpanded `$HOME`, or script not executable — all fail silently |
| Stop hook loops forever | missing `stop_hook_active` guard; harness caps at 8 blocks but fix the guard |
| Agent edits files but the format hook is silent | edit made via Bash (`sed -i`, `cat >`) — `Edit\|Write` never fires; rely on the Stop-hook worktree pass |
| Formatter hook fights the agent | post-edit rewrite trips the agent's stale-file check on its next edit; format on save/commit instead, or accept the re-read cost |
| PreToolUse exit-2 stalls the agent instead of correcting it | known behavior in some versions — keep hard denies rare and actionable; put style feedback in non-blocking channels |
| Hooks treated as security | they are local and user-controlled; subagent dispatch and alternate tool paths route around them — CI + rulesets are the boundary |
| Committed hook = code execution on every clone | `.claude/` changes are code: CODEOWNERS them, review in the web UI before checking out PR branches (real CVEs exist here) |
| Plugin/skill turns out malicious | vet before install (step 5), pin versions, prefer official/curated sources |
| Hook advice from tutorials doesn't match behavior | the event surface and blocking semantics drift across versions — trust https://code.claude.com/docs/en/hooks over any static list, including this skill's |

## Files

- `scripts/check_guardrails.py` — read-only audit of settings, hooks, matchers
  and rules files; non-zero exit on defects.
- `assets/settings.json.template` — hook wiring for the three-script setup.
- `assets/hooks/guard-bash.sh` — PreToolUse deny: `--no-verify`, force-push to
  main, bare pip/python outside uv.
- `assets/hooks/lint-edited-file.sh` — PostToolUse single-file ruff check+format.
- `assets/hooks/stop-verify.sh` — Stop gate template with `stop_hook_active`
  guard; project verify command goes in one marked line.
- `assets/AGENTS.md.template` — starting rules file.
- `references/hooks-reference.md` — full hook mechanics + known issues.
- `references/layer-assignment.md` — which check runs at which layer.
- `references/vetting-skills-and-plugins.md` — vetting checklist + curated skills.
