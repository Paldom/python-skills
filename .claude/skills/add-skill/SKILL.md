---
name: add-skill
description: Authors or improves one Agent Skill via the eval-first workflow - scope a single purpose, write trigger evals, draft SKILL.md, validate, iterate. Use when the user asks to create, add, write, refine, or fix a skill ("add a skill for X", "improve triggering of Y"). Not for infrastructure work - hooks, CI, the validator, or docs.
argument-hint: <skill-name or idea>
# Side-effecting maintainer tool that writes a whole skill folder, invoked as
# /add-skill - exactly like its sibling publish-repo. Nothing routes it, so its
# trigger evals are waived (docs/evals.md).
disable-model-invocation: true
metadata:
  internal: true
---

# add-skill

Builds one production-quality skill in `skills/<name>/`, eval-first. Read
`docs/skill-authoring.md` and `docs/evals.md` once per session before starting;
they are the rulebook this workflow enforces. If invoked as `/add-skill <args>`,
treat `$ARGUMENTS` as the skill name or idea to scope in step 1.

## When NOT to use

- Creating a new skills *repository* → that happens in the workspace above this repo.
- Infrastructure work (hooks, CI, validator, docs) → plain editing, PR-level scrutiny.
- A "skill" that merely restates what the model already does well → don't build it;
  a skill must fix a specific observed failure.

## Workflow

1. **Scope, and pick the invocation mode.** State in one sentence what the skill
   does and the concrete failure it fixes. If the sentence needs "and", split into
   multiple skills and do them one at a time. Check `skills/` and the README catalog
   for overlap — near-neighbor descriptions steal each other's triggers; adjust scope
   or plan disjoint wording. Then decide *who invokes it*, because it changes the
   name, the description, and the eval set: **model-invoked** (default) or
   **user-invoked** (`disable-model-invocation: true` — the user types `/name`;
   correct for side-effecting skills and memorable commands). See the mode table and
   the alias-over-engine split in `docs/skill-authoring.md`.
2. **Gather.** Read `.local/` recursively — every subfolder and file is source
   material (research, examples, constraints). Then research beyond it: web-search
   the topic for current facts, official docs, and prior art; verify anything
   load-bearing against primary sources, and cross-validate contested or
   high-stakes facts (external APIs, schemas, security claims) with /cross when
   available. Verified facts a skill depends on go into `skills/<name>/references/`
   as cleaned, tracked files — never cite `.local/` paths from a skill.
3. **Evals first.** Create `skills/<name>/evals/evals.json` per `docs/evals.md`:
   ≥8 `should_trigger` (vary formality, typos, terseness), ≥8 `should_not_trigger`
   (near-misses sharing keywords), 3–5 `quality` cases with plain-language
   `expected_behavior` assertions. If you can't write these, the scope is unclear —
   go back to step 1. For a **user-invoked** skill both trigger counts are waived —
   no router weighs its description — so write the `quality` cases only.
4. **Draft SKILL.md.** Frontmatter: `name` == folder name; `description` on a
   **single line**, third person. Model-invoked: `[what] + [use when …] + [not for
   …]`, 150–400 chars, trigger keywords in the first ~120. User-invoked: one
   verb-first line that reads well in a `/` menu. Body per the structure in
   `docs/skill-authoring.md`: purpose → when/when-not → numbered workflow → output
   spec → gotchas → pointers. Under 500 lines; deterministic steps as `scripts/`
   (non-zero exit on failure); long material as `references/` with a TOC.
5. **Validate.** `make check` must exit 0 — it runs the validator, then
   `scripts/run_evals.py`, which scores every trigger prompt against every sibling
   description and fails on no-overlap prompts, a sibling outranking the skill, or a
   near-duplicate description. The write-time hook already validated the file; fix
   every error and triage every warning. Fix the description it points at, never the
   evals.
6. **Trigger self-test.** For at least 3 should-trigger and 2 should-not-trigger
   prompts, reason explicitly: would the description alone (not the body) route this
   prompt here, against every other skill in the catalog? Fix the description, not
   the evals. Recommend the user run 2–3 fresh-session probes for the riskiest cases.
   (Skip for user-invoked skills — nothing routes them.)
7. **Register.** Add/update the skill's row in the README catalog table, add a
   `CHANGELOG.md` entry, and put the skill in exactly one `skills.sh.json`
   grouping (engaging one-sentence group descriptions — that file is the repo's
   skills.sh listing copy). The schema shape is `"groupings": [{"title": ...,
   "description": ..., "skills": [...]}]` — the schema rejects other keys
   (`groups`/`name`) and skills.sh silently ignores a non-conforming file;
   `make check` validates it. Re-check descriptions of sibling skills for new
   overlap. Do **not** commit or push — leave all changes for the owner to review.

## Output spec (Definition of Done)

- `skills/<name>/` with SKILL.md + evals/evals.json (+ scripts/references as needed)
- `make check` → 0 errors; README catalog + CHANGELOG updated
- A 3-line summary: purpose, trigger phrase examples, known limitations

## Gotchas

- Keep `description` on ONE physical line — multi-line values have failed to load
  in some runtimes and the validator blocks them; never work around the validator.
- Don't paste failed eval prompts verbatim into the description (overfitting);
  generalize the missing verb/noun instead.
- Over-triggering fix = add targeted "Not for …" noun phrases from the actual
  false-positive overlap; don't delete positive triggers.
- Model upgrades shift routing — note in your summary that evals should be re-run
  after the next model release.
