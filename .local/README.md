# .local/ — private working area (gitignored)

Everything here stays on your machine: it is the raw material for skill building,
never part of the published repo.

Put here:

- `PROMPT.md` — the paste-ready `/goal` command that drives an agent session in this
  repo. Created by the scaffolder and personal to you — there is no committed copy,
  so keep it (or your edits to it) safe on this machine.
- `sources/` — research dumps, reference implementations, API docs, transcripts.
- `notes.md` — decisions, failed experiments, trigger-eval run logs.
- Anything with secrets, licensing doubts, or half-baked drafts.

If a fact in here becomes load-bearing for a skill, move a cleaned version into the
skill's `references/` (committed) — skills must work for people who don't have your
`.local/`.
