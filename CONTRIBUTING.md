# Contributing

Thanks for helping improve Python Skills! This repo distributes Agent Skills, so the
bar is: every skill must trigger reliably, do one thing well, and pass the validator.

## Proposing a skill

Open a [skill proposal issue](https://github.com/Paldom/python-skills/issues/new?template=skill_proposal.md)
first for anything non-trivial. Say what the skill does, when it should trigger, when it should
NOT trigger, and what Claude currently gets wrong without it ("a good skill is a scar,
not a resume" — if you can't name the failure it fixes, it probably shouldn't exist).

## Authoring workflow (eval-first)

1. Read [docs/skill-authoring.md](docs/skill-authoring.md) and [docs/evals.md](docs/evals.md).
2. Scope **one** purpose per skill. Split anything broader.
3. Write trigger evals **before** the skill body: `skills/<name>/evals/evals.json`
   with ≥8 should-trigger and ≥8 should-not-trigger prompts.
4. Draft `skills/<name>/SKILL.md`. Frontmatter rules that break silently if violated:
   - `name`: kebab-case, must equal the folder name.
   - `description`: **single line** (no YAML `|`/`>` block scalars — they silently
     disable the skill), third person, states what it does + when to use it + when not.
5. Validate: `make check` (also runs on every file write via hooks, and in CI).
6. Test triggering in a **fresh** Claude Code session with prompts from your evals.
7. Update the README skill catalog table and `CHANGELOG.md`.

If you work with Claude Code in this repo, the bundled `add-skill` skill walks
these steps for you.

## Pull requests

- One skill (or one focused change) per PR; keep diffs reviewable.
- CI must be green — `make check` locally reproduces it.
- Never commit `.local/` content or use `git commit --no-verify` (a hook blocks it
  for agent sessions; reviewers will bounce it for humans).
- Fill in the PR template checklist.

**Reviewing PRs safely:** this repo ships executable enforcement (`.claude/` hooks
run in any Claude Code session here; `make check` runs `scripts/`). Review diffs to
`.claude/**`, `scripts/**`, `Makefile`, and `.github/workflows/**` **in the GitHub
UI before checking out a PR branch** and starting Claude Code or running `make`.
These paths are CODEOWNERS-protected; maintainers should also enable a ruleset on
`main` (require PR + **code-owner review** + the `validate` check, block force
pushes) — CODEOWNERS does nothing until the ruleset requires code-owner review,
and client-side hooks are convenience; the ruleset is the real gate.

## Local development

No dependencies beyond Python 3.10+ stdlib. `make check` is the whole gate.
