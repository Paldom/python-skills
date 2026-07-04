# Deploying to skills.sh

[skills.sh](https://skills.sh) is the open Agent Skills ecosystem: a public
catalogue, install CLI (`npx skills add`), leaderboard, and security-audit
surface. There is **no publish command** — "deploying" means making this
repository publicly installable and letting install telemetry list it. This
guide is the manual path; the bundled `publish-repo` skill (`/publish-repo`)
walks the same steps.

## How distribution works

- Consumers run `npx skills add Paldom/python-skills` — the CLI
  discovers every `skills/<name>/SKILL.md` (and the `.claude-plugin/` manifests)
  and installs into their agent of choice.
- The repo appears on the skills.sh leaderboard **automatically** after real
  installs (anonymous telemetry; disabled in CI). There is nothing to submit.
- `skills.sh.json` at the repo root customizes the skills.sh repo page —
  display-only groupings with titles and descriptions. Changes are picked up
  after telemetry next sees an install, and pages are cached: a correct change
  may take a while to appear.

## Pre-flight (all must pass)

1. `make check` — 0 errors.
2. At least one real skill under `skills/` (never publish an empty catalogue).
3. README catalogue table and CHANGELOG are current; descriptions are
   benefit-led (they are your listing copy on skills.sh).
4. CI green — including the `skills-sh` job, which runs the same discovery and
   install a consumer would:
   ```bash
   npx skills add . --list                       # every skill discovered?
   npx skills add <repo-root> --skill '*' -a claude-code -y   # installs clean?
   ```
5. Manual blockers for going public: full-history secret scan
   (gitleaks/trufflehog) and a personal/private-file review — no tool here
   ticks these for you.

## Deploy

```bash
# 0. Spec validation (GitHub CLI >= 2.90, public preview) - fix every warning
gh skill publish --dry-run

# 1. Make the repository public (this is the deployment event)
gh repo edit Paldom/python-skills --visibility public --accept-visibility-change-consequences

# 2. Turn on the public-repo protections
#    (PVR + branch ruleset + a v* tag ruleset for immutable releases -
#     see the SECURITY.md note and repo-protections guidance)
gh api repos/Paldom/python-skills/private-vulnerability-reporting --method PUT

# 3. Cut a versioned release (matches .claude-plugin/plugin.json) + topics
gh skill publish --tag v0.1.0
gh repo edit Paldom/python-skills --add-topic skills-sh

# 4. Verify installability exactly like a consumer
npx skills add Paldom/python-skills --list
mkdir -p /tmp/skills-verify && cd /tmp/skills-verify
npx skills add Paldom/python-skills --skill '*' -a claude-code -y
npx skills list -a claude-code
```

`gh skill publish` warnings worth knowing: add `license: MIT` to every skill's
frontmatter (recommended field, scaffolded by default here); the
`.claude/skills/` warning is expected — those are this repo's own bundled dev
skills, committed by design. The README ships with the install-count badge
(`https://skills.sh/b/Paldom/python-skills`) linking to the repo's
skills.sh page.

The verification install above is also what seeds the first telemetry event —
run it outside CI (telemetry is auto-disabled in CI) so the repo gets listed.

## Repo page (skills.sh.json)

Group skills with engaging, benefit-led copy — this is landing-page text:

```json
{
  "$schema": "https://skills.sh/schemas/skills.sh.schema.json",
  "notGrouped": "bottom",
  "groupings": [
    {
      "title": "Ship it",
      "description": "What these skills do for you, in one sentence.",
      "skills": ["skill-one", "skill-two"]
    }
  ]
}
```

Limits: first 50 groups and first 500 skills per group are rendered. Keep every
skill listed in exactly one group; update the file whenever a skill is added.

## Rollback

There is no unpublish lever — rollback is a git rollback: revert to the last
good commit/tag, push, and re-run the verification install. Keep the repo name
stable; consumers reinstall from the same source.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `No skills found` | Missing/invalid `SKILL.md` (needs `name` + `description`), or skills outside `skills/` |
| Skill installs but never loads | Check agent path, YAML validity, single-line description |
| Repo page ignores skills.sh.json | Invalid JSON, repo not yet seen by telemetry, or page cache — install once and wait |
| Consumers get 404 | Repo still private — visibility is the deployment switch |
