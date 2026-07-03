# Skill Authoring Guide

How to write skills that trigger reliably and actually change agent behavior.
Distilled from Anthropic's official guidance and community evidence (mid-2026).

**Contents:** [Anatomy](#anatomy) · [Frontmatter](#frontmatter) ·
[The description](#the-description-is-the-activation-api) ·
[Body structure](#body-structure) · [Progressive disclosure](#progressive-disclosure) ·
[Scripts vs prose](#scripts-vs-prose) · [Gotchas](#gotchas-silent-failure-modes) ·
[Anti-patterns](#anti-patterns)

## Anatomy

A skill is a **folder**, not a markdown file:

```
skills/<name>/
├── SKILL.md          # required — frontmatter + instructions, < 500 lines
├── evals/evals.json  # required here — trigger/quality cases, written FIRST
├── scripts/          # deterministic helpers; code never enters context, only output
├── references/       # long docs loaded on demand — link ONE level deep only
└── assets/           # output templates
```

## Frontmatter

Only `name` and `description` are required. Rules the validator enforces:

| Field | Rule | Why |
| --- | --- | --- |
| `name` | kebab-case `^[a-z0-9]+(-[a-z0-9]+)*$`, ≤ 64 chars, **equals folder name**, no "claude"/"anthropic" | drives discovery and the `/slash-command` |
| `description` | **one physical line**, ≤ 1024 chars, third person | multi-line block scalars (`|`, `>`) have failed to load in some runtimes/versions, break naive frontmatter parsers, and bloat the catalog — this repo requires one line |

Useful optional fields: `argument-hint` (slash-command placeholder),
`disable-model-invocation: true` (side-effect skills: deploy, release — slash-only),
`user-invocable: false` (background knowledge, hidden from the `/` menu),
`allowed-tools` (least privilege; treat as best-effort, not a security boundary),
`context: fork` + `agent` (run isolated in a subagent), `model` / `effort` (route
mechanical skills cheaper). Keep frontmatter under ~20 lines; nest extras under
`metadata:`. Reference bundled files via paths relative to the skill folder.

## The description is the activation API

At session start the model sees **only** `name` + `description` (~30–100 tokens).
If the description doesn't match the user's words, the body might as well not exist.
Write it for an LM router, not a human. Formula:

> **[What it does] + [When to use it — realistic trigger phrasings] + [What it is NOT for]**

```yaml
description: Generates unit and integration tests for the current file. Use when the user asks to "write tests", "add test coverage", or "create a test file". Not for reviewing existing tests or fixing failing ones.
```

Rules of thumb (community-measured, directional):

- **150–400 chars** is the sweet spot; front-load trigger keywords in the first
  ~120 chars (long descriptions can be truncated in the router).
- 3–5 intent-verb synonyms (write/draft/create/generate) and the concrete **output
  type** — the single highest-leverage word against false positives.
- Quote terse real phrasings users actually type: "fix the build", "tests failing".
- Be assertive — Claude under-triggers by default ("Use whenever the user mentions
  X, even if they do not explicitly ask for Y"). Avoid superlatives and the word
  "explicitly" (interpreted inconsistently).
- Add a negative trigger (`Not for …`) with 2–3 short noun phrases when a sibling
  skill shares keywords. Needing more than ~5 exclusions means the scope is too
  broad — split the skill.
- Skills that duplicate Claude's native competence (git commits, generic "code
  review") fail to trigger ~half the time; skills for novel domains trigger
  near-perfectly. Encode what the model *gets wrong*, not what it already knows.

## Body structure

Recommended order — aggressive H2/H3 structure, no long prose walls:

1. Purpose (one paragraph)
2. When to use / **when NOT to use** (anti-triggers — the highest-leverage section
   most authors skip)
3. Numbered workflow with concrete commands
4. Output spec (what done looks like)
5. Failure modes & gotchas (the highest-signal content — grown from real failures)
6. Pointers to `references/` and `scripts/`

Write instructions as imperatives to the agent. Move volatile, time-sensitive facts
out of the body (they decay). Support `$ARGUMENTS` if the skill takes slash args.

## Progressive disclosure

Three tiers: (1) name+description always resident; (2) body loads on invocation —
keep **under 500 lines**; (3) `references/` read only when the body directs, and
`scripts/` executed via Bash so their source never enters context. Link references
**one level deep only** — reference-to-reference chains get partially read. Give any
reference over 100 lines a table of contents so a partial read reveals its scope.
After context compaction each skill gets at most ~5k tokens re-attached — oversized
bodies get truncated mid-instruction.

## Scripts vs prose

Prose for judgment; **scripts for anything deterministic or fragile** (validation,
parsing, scaffolding, API calls). Scripts must exit non-zero on failure and print
machine-readable errors — that's what lets the agent self-correct. Pin every
downloaded dependency; a skill that runs `uvx`/`npx` unpinned is a supply-chain hole.

## Gotchas (silent failure modes)

1. **Multi-line description** (`description: >` / `|`, often introduced by a
   Markdown formatter) → has silently failed to load in some runtimes/versions and
   breaks naive Agent Skills parsers. Single line, always.
2. Missing opening `---` on line 1, or a missing closing `---` → frontmatter parsed
   as body (or body parsed as YAML). No error is shown.
3. Tabs, unquoted colons, angle brackets in frontmatter break parsing.
4. `name` ≠ folder name → discovery and `/name` break.
5. Trigger theft: two skills with overlapping descriptions — one silently wins.
   Make descriptions disjoint or add a router skill; `pdf-extract` + `pdf-create`,
   never `pdf` + `pdf-tools`.
6. Model upgrades shift trigger behavior — re-run trigger evals after each release.
7. Headless mode (`claude -p`) does not auto-trigger skills; document `/name` usage.
8. An `allowed-tools` empty list means deny-all; a missing field inherits everything.

## Anti-patterns

- **Persona skills** ("you are a world-class engineer") — prompt sludge; delete.
- Mega-skills covering a whole domain — 2–3 focused skills beat one comprehensive
  one, measurably.
- Restating defaults the model already follows — zero delta, pure context tax.
- LLM-generated context files shipped unreviewed — measured to *hurt* success.
- More than ~10 skills installed without a pruning audit — the shared description
  budget silently drops the rest.

**A good skill is a scar, not a resume**: it encodes the fix for a specific,
repeatable failure you have actually observed.
