# Python Skills

[![CI](https://github.com/Paldom/python-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/Paldom/python-skills/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Agent Skills and hooks for maintaining high-quality open-source Python packages - an agentic engineering setup covering linting, testing, packaging, releases, and CI quality gates.

Agent Skills for [Claude Code](https://code.claude.com/docs/en/skills) (and any
[Agent Skills](https://agentskills.io)-compatible tool). Each skill is a folder under
[`skills/`](skills/) with a single-purpose `SKILL.md`, trigger evals, and optional
scripts/references — validated on every write, commit, and PR.

## Quick start

Install everything as a plugin (recommended; needs read access while the repo is private):

```
/plugin marketplace add Paldom/python-skills
/plugin install python-skills@python-skills
```

Or copy a single skill into a project:

```bash
git clone https://github.com/Paldom/python-skills.git
cp -r python-skills/skills/<skill-name> your-project/.claude/skills/
```

Then just describe the task in Claude Code — the skill activates on its description —
or invoke it explicitly with `/<skill-name>`.

## Skills

| Skill | Description |
| --- | --- |
| [python-lint](skills/python-lint/) | Sets up and tunes Ruff linting and formatting — `[tool.ruff]` rule selection, Black/Flake8/isort migration — and fixes lint or format failures. |
| [python-typing](skills/python-typing/) | Sets up static type checking — choosing mypy, pyright, or ty, strict configuration, per-module overrides, shipping `py.typed` — and fixes type-check errors. |
| [python-testing](skills/python-testing/) | Builds pytest infrastructure — layout and config, branch-coverage gates, Hypothesis property-based tests, mutation testing, multi-version runs via tox/nox/uv. |
| [python-packaging](skills/python-packaging/) | Configures packaging — pyproject.toml metadata, build backend choice, src layout, uv project management, building and verifying wheels and sdists. |
| [python-release](skills/python-release/) | Cuts and automates releases — version bumps, changelogs, git tags, PyPI trusted publishing (OIDC), and the tag-triggered publish workflow with a gated environment. |
| [python-ci](skills/python-ci/) | Authors GitHub Actions quality gates — lint/type/test matrices, uv caching, an all-checks-passed aggregator, required checks, rulesets, action SHA pinning. |
| [python-precommit](skills/python-precommit/) | Configures pre-commit — ruff, mypy, hygiene, commit-message and pre-push hooks, plus non-Python file formatting and validation, kept in sync with CI. |
| [python-supply-chain](skills/python-supply-chain/) | Hardens the supply chain — Dependabot with cooldown, pip-audit, secret scanning and push protection, CodeQL, Scorecard, SBOMs, CODEOWNERS. |
| [agent-guardrails](skills/agent-guardrails/) | Installs agentic guardrails — Claude Code hooks with the exit-code contract, settings wiring, AGENTS.md rules files, vetted public skills — and troubleshoots hooks. |

Together they implement a layered enforcement architecture for agent-era Python
maintenance: agent hooks (instant feedback) → pre-commit (commit gate) → CI +
rulesets (the authoritative, un-bypassable layer).

## Repository structure

```
skills/                  # distributed skills, one folder per skill (SKILL.md + evals/ + scripts/)
docs/                    # skill-authoring guide, eval methodology
scripts/                 # deterministic validator used by hooks and CI
.claude/                 # agentic dev setup: hooks + the bundled add-skill skill
.claude-plugin/          # plugin + marketplace manifests (makes this repo installable)
.local/                  # gitignored working area: sources, research, PROMPT.md (see below)
```

## Working on this repo with an agent

This repo is agent-native: canonical agent instructions live in
[AGENTS.md](AGENTS.md) (CLAUDE.md imports it), hooks validate every `SKILL.md` on
write, `make check` runs the full validator, and CI enforces the same gate on every
PR. The bundled `add-skill` skill walks the eval-first authoring workflow described
in [docs/skill-authoring.md](docs/skill-authoring.md). Maintainers drive sessions
with their own (gitignored, personal) `.local/PROMPT.md` goal prompt.

## Contributing

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the skill-proposal
process, the authoring workflow, and the PR checklist. Please note the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Support

Questions, ideas, or something not working? Start with [SUPPORT.md](SUPPORT.md) —
bugs and skill proposals have [issue templates](../../issues/new/choose), and
security concerns go through [SECURITY.md](SECURITY.md) (never a public issue).

## License

[MIT](LICENSE) © 2026 Paldom
