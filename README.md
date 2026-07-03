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
| _none yet_ | Skills are added via the workflow in [CONTRIBUTING.md](CONTRIBUTING.md). |

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
