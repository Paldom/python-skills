.PHONY: check validate lint hygiene evals test hooks

# The one place the ruff version is written down; ruff.toml's required-version
# and .pre-commit-config.yaml must agree with it (required-version makes drift loud).
RUFF_PIN := $(shell sed -n 's/^ruff==//p' requirements-dev.txt)

## check: run every quality gate (what CI runs, and what the Stop hook signs off)
check: validate lint hygiene evals test

## validate: validate SKILL.md files, evals, security rules, and plugin manifests
validate:
	python3 scripts/validate_skills.py

## lint: ruff over the Python in this repo (config: ruff.toml)
#  uvx runs the pinned version with no local install; a PATH ruff is the fallback
#  and refuses to run if it is the wrong version (required-version in ruff.toml).
lint:
	@if command -v uvx >/dev/null 2>&1; then \
		uvx --from 'ruff==$(RUFF_PIN)' ruff check . && uvx --from 'ruff==$(RUFF_PIN)' ruff format --check .; \
	else \
		ruff check . && ruff format --check .; \
	fi

## hygiene: the commit-stage hooks (whitespace, EOF, YAML/JSON/TOML, private keys)
#  The same gate `git commit` runs, so a green `make check` means a clean commit.
#  Skips with a notice when pre-commit is not installed; CI installs it.
#  Auto-fixing hooks exit non-zero AFTER repairing the tree, so the second run
#  is the verdict (CI runs it once and fails on any modification instead).
hygiene:
	@if command -v pre-commit >/dev/null 2>&1; then \
		pre-commit run --all-files --hook-stage pre-commit >/dev/null 2>&1 || pre-commit run --all-files --hook-stage pre-commit; \
	else \
		echo "hygiene: pre-commit not installed (pip install -r requirements-dev.txt) - skipped locally, CI runs it"; \
	fi

## evals: score every trigger case against every description (routing + ratchet)
#  --min-rank1 is the checked-in ratchet floor: raise it deliberately as the
#  number improves, never lower it to get green.
evals:
	python3 scripts/run_evals.py --min-rank1 79

## test: self-checks for the scorer and the security rules
test:
	python3 scripts/test_run_evals.py
	python3 scripts/test_validate_skills.py

## hooks: install the commit-time layer (pre-commit + pre-push)
hooks:
	pre-commit install --install-hooks
