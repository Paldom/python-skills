# One-run setup prompt

A paste-ready `/goal` prompt that applies **every skill in this repository** to a
target Python project in a single orchestrated run: baseline audit → sequential
foundation work → parallel subagents where write surfaces are provably disjoint →
dependent skills → deep review → one commit on a PR branch.

## Why this order (derived from the skills' write surfaces, not vibes)

| Skill | Writes | Read-only verifier |
| --- | --- | --- |
| python-packaging | `pyproject.toml` (owner: `[project]`, `[build-system]`, `[dependency-groups]`), `uv.lock`, `src/` layout, `dist/` | `scripts/check_wheel.py` |
| python-lint | `pyproject.toml` (`[tool.ruff]`), dev deps, **repo-wide `.py` reformat/fixes** | `scripts/check_ruff_config.py` |
| python-typing | `pyproject.toml` (`[tool.mypy]` / `[tool.pyright]`), dev deps, `py.typed`, type fixes in `src/` | `scripts/check_py_typed.py` |
| python-testing | `pyproject.toml` (`[tool.pytest.ini_options]`, `[tool.coverage.*]`), dev deps, `tests/` | `scripts/check_test_config.py` |
| python-precommit | `.pre-commit-config.yaml`, `.github/workflows/pre-commit.yml` | `scripts/check_precommit_config.py` |
| python-supply-chain | `.github/dependabot.yml`, `.github/CODEOWNERS`, `[tool.uv] exclude-newer`, GitHub security settings via `gh` | `scripts/check_supply_chain.py` |
| agent-guardrails | `.claude/settings.json`, `.claude/hooks/`, `AGENTS.md`, `CLAUDE.md` | `scripts/check_guardrails.py` |
| python-ci | `.github/workflows/ci.yml`, branch rulesets / required checks via `gh` | `scripts/check_workflows.py` |
| python-release | `.github/workflows/publish.yml`, `CHANGELOG.md`, versioning config, PyPI trusted-publisher (manual) | `scripts/check_release_setup.py` |

- **packaging runs first, alone** — every later skill assumes a sane
  `pyproject.toml`, a committed `uv.lock`, and a working `uv sync`.
- **lint → typing → testing run sequentially** — all three edit `pyproject.toml`
  and overlapping `.py` files (a repo-wide reformat racing type-fix edits in one
  working tree corrupts both). Lint first so later edits land on formatted code;
  typing before testing so new tests are written against checked types.
- **precommit ∥ supply-chain ∥ agent-guardrails run as parallel subagents** —
  their file write-sets are disjoint (see table), *given two extra clauses in the
  prompt*: parallel agents never run `uv add`/`uv lock` (they report needed dev
  dependencies instead — the lockfile is a shared surface), and only
  python-supply-chain may touch `pyproject.toml` (the `[tool.uv]` table only).
  They run after lint/typing/testing because pre-commit hook revs must be in
  lockstep with the ruff/mypy versions those skills just pinned, and the
  guardrails Stop-hook needs the project's real verify commands to exist.
- **python-ci runs after everything above** — its jobs must run the exact
  commands the earlier skills configured, and it must not duplicate or edit the
  pre-commit mirror workflow (owned by python-precommit).
- **python-release runs last among writers** — its publish workflow gates on the
  CI quality gate existing, and tag protection interacts with the rulesets
  python-ci just created.
- **Read-only verifiers bracket the run**: all nine `scripts/check_*.py` are
  non-mutating with non-zero exit on findings, so they are safe as a baseline
  before any change and as the proof afterwards.
- **The final push is a branch + PR, not a push to `main`** — the run itself
  enables required checks on `main`, so a direct push would (correctly) be
  rejected by the very gate it just installed.

## Prerequisites

- Install the skills, either as a plugin (in Claude Code):

  ```
  /plugin marketplace add Paldom/python-skills
  /plugin install python-skills@python-skills
  ```

  or by copying them into the target project:

  ```bash
  git clone https://github.com/Paldom/python-skills.git
  cp -r python-skills/skills/* your-project/.claude/skills/
  ```

  Skills copied into `.claude/skills/` are invoked as `/<skill-name>`
  (e.g. `/python-lint`); plugin-installed skills may need the namespaced form
  `/python-skills:<skill-name>` — check the `/` menu and use whichever form your
  session lists.
- `uv` installed; `gh` authenticated with admin rights on the target repo
  (rulesets, security settings) and `workflow` scope. Python 3.11+ on PATH
  (two verifier scripts need `tomllib` and exit early on 3.10 saying so).
- Run from the target repo root, on a **clean git tree**.

## The prompt

Paste this as a `/goal` (or a plain message) in a Claude Code session at the
target repo root. Replace `<pkg>` with the import package name.

````text
/goal Set up this Python repository with the python-skills toolchain, end to end,
until every bundled verifier exits 0 and the work is on a pushed PR branch.
Work autonomously. Subagents NEVER commit, never run `git`, and never run
`uv add`/`uv lock` unless their step says so — the orchestrator owns git and the
lockfile. Never use `git commit --no-verify`; never force-push. If a permission,
missing tool, or plan limit blocks a step, report it and continue — do not
silently skip it and do not claim it done.

Phase 0 — prerequisites and baseline (read-only):
1. Verify: clean `git status`, `uv --version`, `gh auth status`, Python >= 3.11,
   and that these nine skills are installed (check the / menu; plugin installs
   may namespace them as /python-skills:<name>): python-packaging, python-lint,
   python-typing, python-testing, python-precommit, python-supply-chain,
   agent-guardrails, python-ci, python-release. Report anything missing and stop.
2. Baseline: run every skill's bundled read-only verifier from its scripts/
   folder and record the error/warning counts as the "before" column:
   check_wheel.py, check_ruff_config.py, check_py_typed.py, check_test_config.py,
   check_precommit_config.py, check_supply_chain.py (with --github), 
   check_guardrails.py, check_workflows.py, check_release_setup.py. Also record
   whether the existing test suite passes. Expected: most fail before setup —
   that is the point of the baseline.

Phase 1 — foundation (sequential, main context):
3. Invoke /python-packaging: pyproject.toml metadata, build backend, src layout,
   uv-managed deps with committed uv.lock, `uv build`, and its verifier
   (check_wheel.py) to 0 errors. Everything later depends on this.

Phase 2 — tool configuration (sequential — these three share pyproject.toml and
overlapping .py edits, so they must not run concurrently):
4. Invoke /python-lint: [tool.ruff] with an explicit select, pinned ruff,
   repo-wide fix+format as its own reviewable change; check_ruff_config.py to 0.
5. Invoke /python-typing: one pinned checker, strictness strategy (ratchet on
   legacy code), py.typed for libraries; check_py_typed.py to 0 (build first).
6. Invoke /python-testing: pytest + branch-coverage config with a PROVEN
   fail_under gate, Hypothesis/mutation testing where warranted;
   check_test_config.py to 0 and the suite green via `uv run pytest`.

Phase 3 — parallel subagents (disjoint write surfaces; launch all three at once;
name the skill explicitly in each subagent's instructions — auto-triggering
inside subagents is unreliable):
7a. Subagent A — invoke /python-precommit. Owns .pre-commit-config.yaml and
    .github/workflows/pre-commit.yml only. Hook revs in lockstep with the ruff
    and mypy versions pinned in Phase 2. Do NOT run `uv add`; report the
    pre-commit dev-dependency for the orchestrator to add. Run
    check_precommit_config.py to 0 errors.
7b. Subagent B — invoke /python-supply-chain. Owns .github/dependabot.yml,
    .github/CODEOWNERS, SECURITY.md, GitHub security settings via gh, and — as
    the only agent in this phase allowed to touch pyproject.toml — the
    [tool.uv] exclude-newer key only. Report (do not change) anything that
    needs licensing or admin rights it lacks. Run check_supply_chain.py
    (with --github if gh is authenticated) to 0 FAILs.
7c. Subagent C — invoke /agent-guardrails. Owns .claude/settings.json,
    .claude/hooks/, AGENTS.md, CLAUDE.md. Wire the Stop-hook verify command to
    the project's real gate from Phase 2. Trip every hook deliberately (test
    exit codes with sample stdin). Run check_guardrails.py to 0 errors.
8. Orchestrator: apply the dev-dependencies reported by the subagents in ONE
   `uv add --dev` pass, run `uv run pre-commit run --all-files` until clean,
   then re-run the three Phase-3 verifiers.

Phase 4 — dependent skills (sequential):
9. Invoke /python-ci: ci.yml running exactly the commands configured in Phase 2
   (check mode, `uv sync --locked`), version matrix from requires-python,
   all-checks-passed aggregator with if: always(), SHA-pinned actions, zizmor
   clean, rulesets requiring ONLY the aggregator. Do not modify pre-commit.yml
   (owned by Phase 3). check_workflows.py to 0 errors.
10. Invoke /python-release: versioning decision, CHANGELOG, tag-triggered
    publish.yml that re-runs the quality gate before publishing, gated `pypi`
    environment, SHA-pinned actions. The PyPI trusted-publisher registration is
    a HUMAN step — emit the exact settings to enter and leave it as an
    unchecked box, never marked done. check_release_setup.py to 0 errors
    (publisher-side items may remain warnings; say so).

Phase 5 — deep review of the combined diff:
11. Re-run ALL nine verifiers, plus `uv run pre-commit run --all-files`,
    zizmor on .github/workflows/, and the full test suite.
12. Review `git diff` end to end for cross-file consistency: the same tool
    versions in pyproject.toml, .pre-commit-config.yaml and CI; the same
    commands in AGENTS.md, the Stop hook, the Makefile (if any) and ci.yml;
    no skill weakened another's gate. If a code-review skill is available in
    the session, run it on the diff and fix or explicitly reject each finding
    with a reason; if none is available, note that.

Phase 6 — ship:
13. Produce a before/after table: per verifier, baseline errors vs final (must
    be 0), plus suite/coverage status. List every deferred item with its reason
    and every human-action item as an unchecked checkbox.
14. Single orchestrator commit of everything on a new branch
    (e.g. chore/agentic-setup), push the branch, and open a PR — main now has
    required checks, so the PR is the correct (and only) way in. Watch the PR
    checks; the run is not done until the aggregator reports green or the
    failure is diagnosed and reported.

Definition of Done:
- All nine bundled verifiers exit 0 (or a named verifier's residual warnings
  are listed with reasons); pre-commit, zizmor, and the test suite are green.
- Every category improved versus the Phase-0 baseline or is explicitly
  deferred with a stated reason.
- Unknowns are reported as unknowns; manual steps (PyPI trusted publisher,
  required-reviewer environment, licensing-gated GitHub features) appear as
  unchecked boxes for the human — never as passed.
- One commit, on a pushed PR branch, with a clean conventional message;
  no --no-verify, no force-push, no direct push to main.
````

## Trimming for smaller projects

Drop whole phases, not steps inside them: a package that will never publish to
PyPI skips step 10 (and `check_release_setup.py` stays in the baseline as
documentation of that choice); a repo without GitHub admin access runs
python-supply-chain and python-ci in report-only mode (both skills print the
`gh` commands for a human instead); a script-sized project may only want
Phases 0–2. Keep Phase 0 and Phase 5 in every variant — the baseline and the
re-verification are what make the run trustworthy.

If the session's plan or permission limits prevent parallel subagents, run
Phase 3 sequentially in the order 7a → 7b → 7c — correctness does not depend on
the parallelism, only wall-clock time does. Whatever gets skipped or downgraded
must appear in the final report; a silently missing control looks identical to
a passing one, which is exactly the failure mode this toolchain exists to
prevent.
