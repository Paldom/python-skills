# One-run setup prompt

One paste-ready `/goal` prompt applying every skill here to a target Python project. Order follows write surfaces: packaging first; lint, typing, testing sequential (shared `pyproject.toml`, overlapping `.py` files); precommit, supply-chain, guardrails in parallel (disjoint files); CI then release last. Read-only `scripts/check_*.py` verifiers bracket the run.

## Prerequisites

- Install the plugin (Claude Code):

  ```
  /plugin marketplace add Paldom/python-skills
  /plugin install python-skills@python-skills
  ```

  Plugin skills may be namespaced as `/python-skills:<name>`.
- `uv`; `gh` authenticated with repo admin rights and `workflow` scope; Python 3.11+.
- Run from the target repo root on a clean git tree.

## The prompt

````text
/goal Set up this repo with the python-skills toolchain until every bundled
verifier exits 0. NOBODY (orchestrator or subagents) runs `git commit` or
`git push`: all changes stay in the working tree for my review. Subagents
never run `uv add`/`uv lock`; the orchestrator owns the lockfile.
If anything blocks a step, report it and continue; never silently skip it.

Phase 0 — baseline (read-only): verify clean git status, uv, gh auth, and
that all nine skills are installed: python-packaging,
python-lint, python-typing, python-testing, python-precommit,
python-supply-chain, agent-guardrails, python-ci, python-release. Run each
skill's verifier (check_wheel.py, check_ruff_config.py, check_py_typed.py,
check_test_config.py, check_precommit_config.py, check_supply_chain.py
--github, check_guardrails.py, check_workflows.py, check_release_setup.py);
record error counts as the baseline.

Phase 1: invoke /python-packaging: metadata, build backend, src layout,
committed uv.lock, `uv build`; check_wheel.py to 0.

Phase 2 (sequential — these three share pyproject.toml and overlapping .py
edits): invoke /python-lint ([tool.ruff] explicit select, pinned ruff,
repo-wide fix+format; check_ruff_config.py to 0), then /python-typing (one
pinned checker, py.typed; check_py_typed.py to 0), then /python-testing
(pytest + branch coverage with a proven fail_under gate;
check_test_config.py to 0, suite green).

Phase 3 — three parallel subagents (name the skill explicitly in each;
auto-triggering in subagents is unreliable):
A. /python-precommit — owns .pre-commit-config.yaml and pre-commit.yml only;
   hook revs match Phase-2 pins; check_precommit_config.py to 0.
B. /python-supply-chain — owns dependabot.yml, CODEOWNERS, SECURITY.md, gh
   security settings; only agent allowed to touch pyproject.toml ([tool.uv]
   exclude-newer only); check_supply_chain.py --github to 0 FAILs.
C. /agent-guardrails — owns .claude/settings.json, .claude/hooks/, AGENTS.md,
   CLAUDE.md; wire the Stop hook to the Phase-2 gate; trip every hook;
   check_guardrails.py to 0.
Then orchestrator: one `uv add --dev` pass for deps the subagents reported,
pre-commit run --all-files clean, re-run the three verifiers.

Phase 4: invoke /python-ci: ci.yml running exactly the Phase-2 commands
(check mode, uv sync --locked), all-checks-passed aggregator, SHA-pinned
actions, rulesets requiring only the aggregator; don't touch pre-commit.yml;
check_workflows.py to 0. Then /python-release — CHANGELOG, tag-triggered
publish.yml with gated pypi environment; PyPI trusted-publisher registration
is a HUMAN step (emit settings, leave unchecked); check_release_setup.py to 0.

Phase 5: re-run all nine verifiers, pre-commit, zizmor, tests; review the
full diff for cross-file consistency (same tool versions and commands in
pyproject.toml, pre-commit, AGENTS.md, and CI).

Definition of Done: all nine verifiers exit 0 (residual warnings listed with
reasons); before/after table vs baseline; manual steps as unchecked boxes,
never marked passed; nothing committed — no --no-verify, no push.
````

## Notes

If parallel subagents aren't possible, run Phase 3 sequentially A→B→C. Anything skipped must appear in the final report.
