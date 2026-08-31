# AGENTS.md

Canonical agent instructions for this repository — `CLAUDE.md` simply imports this
file, so every agent (Claude Code, Copilot, Cursor, Codex, …) reads the same rules.

Agent Skills repository — skills live in `skills/<name>/` (one purpose per skill),
distributed via the plugin manifest in `.claude-plugin/`.

## Commands

- Validate everything (the only gate): `make check` — validator (frontmatter,
  evals, security rules, manifests), `make lint` (ruff), `make evals` (trigger
  scoring), then the self-checks
- Install the commit-time hooks once per clone: `make hooks`
- Validate one file: `python3 scripts/validate_skills.py --file skills/<name>/SKILL.md`

## Non-negotiable conventions

- **Eval-first**: write `skills/<name>/evals/evals.json` before the SKILL.md body.
- Frontmatter `description` is a **single line** (multi-line silently disables the
  skill), third person. Model-invoked skills add trigger phrasings and a "Not for …"
  exclusion; user-invoked ones (`disable-model-invocation: true`) are never routed,
  so they get one verb-first line and no trigger cases.
- `name` equals the folder name, kebab-case.
- Shipped Python is **stdlib-only**; ruff and pre-commit are dev tooling pinned in
  `requirements-dev.txt`. Fix a ruff finding at the line with a reason, never by
  dropping the rule. Never suppress a security finding to get green.
- SKILL.md bodies target 25–150 lines (< 500 is the hard ceiling); long material goes
  to `references/` (linked one level deep); deterministic steps go to `scripts/` with
  non-zero exit on failure.
- Every added/changed skill updates the README catalog table, `CHANGELOG.md`, and
  its `skills.sh.json` grouping.
- Publication to skills.sh happens ONLY via the bundled `/publish-repo` skill
  (slash-invoked, needs the owner's go-ahead) — never flip repo visibility ad hoc.
  Deployment model: docs/deploying.md.
- **Never run `git commit` or `git push`.** Leave every change in the working
  tree for the owner to review and commit. (The bash-guard hook additionally
  blocks `--no-verify` and force-pushes as a safety net; the server-side `main`
  ruleset is the real gate.)
- `.local/` is gitignored personal material (only its README is committed) — read
  ALL of it recursively, never commit its contents, never cite it as a committed
  path.

## Where things are

- Authoring rules: `docs/skill-authoring.md` · Eval methodology: `docs/evals.md`
- Session goal prompt: `.local/PROMPT.md` — personal, created at scaffold time,
  never committed; if it is missing, ask the maintainer for their goal prompt.
- Hooks: `.claude/hooks/` (SKILL.md write-time validation, bash guard) — wired in
  `.claude/settings.json`; changes to them get PR-level scrutiny.
- The `add-skill` skill (`.claude/skills/add-skill/`) walks the authoring
  workflow — prefer it over ad-hoc skill writing. The `publish-repo` skill
  (`.claude/skills/publish-repo/`) walks skills.sh deployment.
