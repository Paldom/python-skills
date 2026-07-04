# Changelog

All notable changes to this repository's skills are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning: [SemVer](https://semver.org) on the plugin manifest
(breaking skill-interface change → major, new skill → minor, fix → patch).

## [Unreleased]

### Added
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
