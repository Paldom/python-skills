# Changelog

All notable changes to this repository's skills are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning: [SemVer](https://semver.org) on the plugin manifest
(breaking skill-interface change → major, new skill → minor, fix → patch).

## [Unreleased]

## [0.4.0] - 2026-09-10

### Changed
- Currency pass against primary sources (2026-09-10): Ruff 0.16 grew the default rule
  set from 59 to 413 rules and formats Python fences in Markdown by default (the
  "defaults are only E+F" scar is rewritten around "never rely on the defaults");
  `uv format` dates from uv 0.8.13; the formatter-conflicting rule list matches the docs;
  pytest 9's native `[tool.pytest]` table and `pytest.toml` precedence are stated as
  fact; pytest-cov 7 dropped subprocess coverage (use coverage's `patch = ["subprocess"]`)
  and fixed the threshold exit code in 7.1; mutmut's key is `source_paths`; mypy 2.0's
  default flips and Pyrefly 1.x; pyright `exclude` is additive; Python matrices move to
  3.11-3.14 (3.10 EOL 2026-10); `uv-dynamic-versioning` is hatchling-only; self-hosted
  runners and environment protection rules described accurately; reusable workflows
  cannot be trusted publishers; `uv publish` does not generate attestations; Dependabot's
  3-day default cooldown and native `pre-commit` ecosystem; GitHub's read-only cache for
  untrusted triggers; `language: unsupported`; every example pin and SHA refreshed
  (checkout v7.0.1, setup-uv v10.0.1, pypi-publish v1.14.2, zizmor 1.30.1, pre-commit
  4.6.2, ruff 0.16.6, mypy 2.3.1, uv_build 0.12, pip-audit 2.10.1, and the pre-commit
  mirror revs).
- `agent-guardrails`: the hooks contract now matches the current Claude Code docs —
  stdout JSON is read on every exit code, exit 2's reason is the JSON `reason` or else
  stderr, `PostToolUse` fires only on success, hooks run inside subagents, 33 events
  (`ConfigChange` and `FileChanged` close gaps the skill used to call unfixable),
  600 s default timeout, matcher exact-set includes `-`/spaces/commas, `disableAllHooks`
  precedence. The three shipped hooks are rewritten as stdlib Python (no `jq`):
  `guard_bash.py` lexes commands (catches `git push origin HEAD:main --force`,
  `git -c core.hooksPath=... commit`, `--no-verif`, `SKIP=`, `python3.12 -m pip`,
  newline-separated commands; passes `git commit -uno`), `lint_edited_file.py` reports
  instead of rewriting the file, `stop_verify.py` runs in `$CLAUDE_PROJECT_DIR` and
  releases through `systemMessage`. `check_guardrails.py` uses the documented tool and
  blockable-event lists, no longer demands an executable bit on `python3 <script>`
  invocations, and warns about auto-fixing PostToolUse hooks.
- `python-testing/scripts/check_test_config.py` knows `pytest.toml`/`.pytest.toml` and
  both pyproject tables (both present is an error).
- `python-lint/scripts/check_ruff_config.py` warns about relying on the moving default
  rule set rather than claiming it is E+F.
- Repo hooks: the bash guard enforces the owner-only `git commit`/`git push` rule (any
  wrapper, `bash -c`, or newline), a Stop gate runs `make check` before a turn can end
  (`stop_hook_active` guard, visible `systemMessage` release), the ruff pin is read from
  `requirements-dev.txt`, the write-time validator also fires for `evals.json` and
  `references/` edits, and hook timeouts leave headroom.
- Validator: body length above 500 lines is an error; the ruff pin in
  `requirements-dev.txt`, `ruff.toml` and `.pre-commit-config.yaml` must agree.
- The rank-1 routing ratchet is armed (`--min-rank1 79`) in the Makefile and CI.
- `make check` now also runs the commit-stage hygiene hooks (`make hygiene`, converging on
  auto-fixes) and CI runs them once, failing on any modification — the Stop gate and CI
  enforce the same gate `git commit` does (`detect-private-key` included).
- Bash guards (repo and shipped): shell keywords (`if …; then git push`, `for …; do git
  commit`) no longer hide a git call; Stop gates: on the retry round they release only when
  the failure output is unchanged (no progress), otherwise they keep blocking up to the
  harness cap; the shipped gate handles an unborn `HEAD`.
- `python-ci`: the coverage matrix template gives each leg its own `COVERAGE_FILE` and
  disables per-leg `fail_under` (pytest-cov applies the config's threshold per leg and
  writes one `.coverage`, so legs collided on download); the path-filtered aggregator
  requires the filter job to succeed and an explicit `"false"`; `gh api` branch-protection
  examples send a JSON body (`--field` cannot express nested objects).
- `python-packaging`: uv_build supports several modules via `module-name = [...]`;
  poetry-core reads PEP 621 since Poetry 2.0; hatchling `packages` ignores `include`
  (use `force-include` or in-package assets); setup.cfg/MANIFEST.in migration inventories
  and diffs artifacts before deleting; pip fallback installs dependency groups with
  `pip install -e . --group dev`.
- `python-release`: `uv-dynamic-versioning` needs `[tool.hatch.version] source`; publish
  attestations prove the uploading identity, not the build; pending publishers do not
  reserve names; `uv sync`/`uv run` silently rewrite a stale lockfile (only `--locked`
  fails); the release checker no longer reports `1.2.3rc1` as matching tag `v1.2.3`.
- `python-typing`: SQLAlchemy 2.x is natively typed (its mypy plugin is deprecated);
  ty's gradual guarantee is about loosening annotations, not adding them.
- `python-precommit`: pre-commit itself fails a hook that modified files, so
  `--exit-non-zero-on-fix` is not what prevents a silent fix (checker W101 → note N202;
  evals and this repo's own `.pre-commit-config.yaml` comment corrected).
- `python-lint`: formatter-conflict list matches the Ruff docs (`ISC001` is fine;
  `D203`/`Q004` added) in the checker and reference.
- `python-testing`: the Hypothesis database is a cache, not a permanent regression suite.
- `python-supply-chain`: `uv audit` (preview) named as an alternative; the `--github`
  audit resolves the repo from `--root`, not the shell cwd.
- `agent-guardrails/scripts/check_guardrails.py`: unknown event names and malformed
  handler containers are errors; a non-object settings file no longer crashes it.
- From the research pass (primary sources cited in `.local/research`): hatchling 1.32's
  Core Metadata 2.5 needs twine >= 7 / pypi-publish >= 1.14.2; PyPI rejects new files on
  releases older than 14 days (2026-07-22); pytest 9.0.x silently ignored the strict flags
  inside `addopts` (fixed 9.1.0); coverage/pytest-cov/pytest disagree on failure exit
  codes (gate on non-zero) and `fail_under` is a combined statement+branch total;
  `astral-sh/setup-uv` has no floating `@v10` tag; `exclude-newer` compares per-artifact
  upload time; prek command renames; zizmor 1.27.0's token leak; the hooks reference
  gained a Claude Code version-notes section (2.1.143–2.1.257) and the 33-event count.
  The hooks reference also records the keyv/cacheable npm worm (2026-08-04) planting
  `.claude/settings.json` hooks in host repos — the concrete case for CODEOWNERS on
  `.claude/` and a `ConfigChange` guard.
- `docs/skill-authoring.md` and the validator's known frontmatter keys follow the current
  Claude Code skills reference (1,536-char listing truncation; `arguments`,
  `disallowed-tools`, `background`, `shell`, `compatibility`).

## [0.3.0] - 2026-08-31

### Added
- Adopted the current skillskit gate: executed trigger evals scoring every trigger
  prompt against every skill description (rank-1 routing accuracy 79.6%), a security
  scan over skill content and bundled scripts, ruff lint and format, README-shape
  validation, pre-commit hooks and a write-time lint hook.

### Changed
- Skill descriptions sharpened where the eval gate showed a sibling outranking a
  skill on its own trigger prompts, or a stated non-trigger matching better than any
  trigger. Fixes changed the scope boundary, not just the wording.

### Fixed
- Findings the new lint gate surfaced in this repo's own scripts, fixed at the
  source; where a rule was wrong for a line it is suppressed there with its reason.


## [0.2.1] - 2026-07-10

### Changed
- `agent-guardrails` — the Stop gate now enforces commit-gate parity: when the
  repo has `.pre-commit-config.yaml` it runs pre-commit itself over the
  changed + untracked worktree files (twice, so auto-fix hooks like prettier
  and `ruff --fix` converge instead of reading as failures; `uv run` fallback;
  actionable block when pre-commit is missing), so the agent signs off only
  changes `git commit` would accept. Stop timeout raised to 300 s with
  pre-built-env guidance (a timed-out hook is non-blocking, i.e. a silent
  pass); the bash guard also denies `SKIP=<hook> git commit`; the audit script
  warns when a repo has pre-commit but the Stop gate never runs it.
- `python-precommit` — the non-Python formatter route is now chosen by
  toolchain (`package.json` → Prettier via the maintained fork; pure-Python →
  the Node-free stack), with node-bootstrap failure fixes
  (`language_version: system`) and an agent-parity gotcha cross-linking
  agent-guardrails.

### Added
- skills.sh distribution: `npx skills add Paldom/python-skills` quick start, repo-page
  groupings (`skills.sh.json`), a `skills-sh` CI job mirroring the consumer
  install, `docs/deploying.md`, and the bundled `publish-repo` skill.
- `docs/setup-prompt.md` — a paste-ready one-run `/goal` prompt that
  orchestrates all nine skills against a target project (write-surface-derived
  ordering, parallel subagents where provably safe, verifier-bracketed, ends in
  a single PR-branch commit), linked from the README quick start.

## [0.2.0] - 2026-07-04

### Added
- `python-lint` — Ruff lint + format setup, migration off Black/Flake8/isort,
  rule tuning, and fixing lint/format failures. With a read-only config
  sanity-checker script.
- `python-typing` — type-checker selection (mypy/pyright/ty presented as an
  unsettled race), strict-mode strategy and ratchet, `py.typed`/PEP 561 with
  wheel verification script.
- `python-testing` — pytest config, proven branch-coverage gates, Hypothesis,
  mutation testing as the agent-era assertion backstop, tox/nox/uv
  multi-version runs. With a test-config audit script.
- `python-packaging` — pyproject metadata, build-backend trade-offs
  (uv_build/hatchling/setuptools), src layout, uv project management,
  wheel/sdist content verification script.
- `python-release` — versioning strategy, changelog policy, uv.lock-desync
  fix, PyPI trusted publishing (OIDC) with exact-match troubleshooting, a
  fully SHA-pinned tag-triggered publish workflow, release-setup audit script.
- `python-ci` — GitHub Actions quality gates: matrices, uv caching, coverage
  combine placement, `all-checks-passed` aggregator, rulesets/required checks,
  workflow hardening (SHA pinning, zizmor, token scoping), hygiene scanner
  script.
- `python-precommit` — pre-commit baseline with ruff/hygiene/non-Python
  validators, commit-msg and pre-push stages, CI mirror and version-sync
  discipline, config footgun-linter script.
- `python-supply-chain` — Dependabot with cooldown, pip-audit against the
  lockfile, uv `exclude-newer`, secret scanning + push protection, CodeQL,
  Scorecard, SBOM/attestations, CODEOWNERS; posture audit script.
- `agent-guardrails` — Claude Code hooks (exit-code contract, layered
  enforcement), settings scopes, AGENTS.md/CLAUDE.md rules files, public-skill
  vetting; ships working hook scripts, templates, and a guardrail audit script.
- README skill catalog and layered-enforcement overview.

## [0.1.0] - 2026-07-02

### Added
- Repository scaffolded from the skills template.
