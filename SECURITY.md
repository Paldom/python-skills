# Security Policy

## Why this matters here

Agent Skills are executable instructions: a skill can direct an agent to run shell
commands, fetch content, or edit files with the user's privileges. Treat installing a
skill like installing software.

This repo's baseline:

- Skills must not fetch and execute remote code, exfiltrate data, or modify files
  outside the task the user asked for.
- Bundled `scripts/` must be reviewable, deterministic, and side-effect-scoped;
  pin versions of anything they download.
- Frontmatter must not contain hidden auto-trigger bait (descriptions engineered to
  fire on unrelated prompts) — reviewers check `description` against evals.
- `.claude/` hooks and settings are code that runs on contributors' machines: the
  committed `.claude/settings.json` wires hooks that fire in any Claude Code session
  opened here, and `make check` executes `scripts/`. **Operative rule: review diffs
  to `.claude/**`, `scripts/**`, `Makefile`, and `.github/workflows/**` in the
  GitHub UI *before* checking out a PR branch and starting an agent or running
  `make`.** These paths require owner review via CODEOWNERS.
- Client-side hooks are best-effort convenience for agent sessions, not a security
  boundary — server-side protection (a `main` ruleset blocking force pushes,
  requiring code-owner review, and requiring the `validate` check) is the real gate.

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Use GitHub's
[private vulnerability reporting](https://github.com/Paldom/python-skills/security/advisories/new)
for this repository. You should receive a response within 7 days.

> Maintainer setup note: Private Vulnerability Reporting is **off by default** and
> only available on **public** repositories — enable it under
> *Settings → Advanced Security* right after flipping the repo public, or the link
> above will 404 for reporters.

## Supported versions

Only the latest release on `main` is supported with security fixes.
