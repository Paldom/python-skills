# AGENTS.md

Canonical agent instructions for this repository — `CLAUDE.md` simply imports this
file, so every agent (Claude Code, Copilot, Cursor, Codex, …) reads the same rules.

Agent Skills repository — skills live in `skills/<name>/` (one purpose per skill),
distributed via the plugin manifest in `.claude-plugin/`.

## Commands

- Validate everything (the only gate): `make check`
- Validate one file: `python3 scripts/validate_skills.py --file skills/<name>/SKILL.md`

## Non-negotiable conventions

- **Eval-first**: write `skills/<name>/evals/evals.json` before the SKILL.md body.
- Frontmatter `description` is a **single line** (multi-line silently disables the
  skill), third person, with trigger phrasings and a "Not for …" exclusion.
- `name` equals the folder name, kebab-case.
- SKILL.md bodies < 500 lines; long material goes to `references/` (linked one level
  deep); deterministic steps go to `scripts/` with non-zero exit on failure.
- Every added/changed skill updates the README catalog table and `CHANGELOG.md`.
- Never use `git commit --no-verify` or force-push main (hooks block the common
  forms in agent sessions; the server-side `main` ruleset is the real gate).
- `.local/` is gitignored personal material (only its README is committed) — read it,
  never commit its contents, never cite it as a committed path.

## Where things are

- Authoring rules: `docs/skill-authoring.md` · Eval methodology: `docs/evals.md`
- Session goal prompt: `.local/PROMPT.md` — personal, created at scaffold time,
  never committed; if it is missing, ask the maintainer for their goal prompt.
- Hooks: `.claude/hooks/` (SKILL.md write-time validation, bash guard) — wired in
  `.claude/settings.json`; changes to them get PR-level scrutiny.
- The `add-skill` skill (`.claude/skills/add-skill/`) walks the authoring
  workflow — prefer it over ad-hoc skill writing.
