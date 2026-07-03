.PHONY: check validate

## check: run every quality gate (what CI runs)
check: validate

## validate: validate all SKILL.md files, evals, and plugin manifests
validate:
	python3 scripts/validate_skills.py
