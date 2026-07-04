# Versioning strategy, release tools, and changelog practice

**Contents:** [Static vs dynamic](#static-vs-dynamic-versioning) ·
[Single-sourcing the version](#single-sourcing-the-version) ·
[Tool landscape](#release-tool-landscape) · [PSR + uv config](#python-semantic-release--uv-configuration) ·
[Conventional commits](#conventional-commits-mapping) · [Changelog strategy](#changelog-strategy) ·
[SemVer caveats](#semver-caveats)

## Static vs dynamic versioning

The clearest unresolved debate in Python release practice — pick deliberately.

**Static** — the version is a literal string in `pyproject.toml`:

```bash
uv version                      # print current version
uv version --bump minor         # rewrite pyproject.toml + refresh uv.lock
uv version --short              # print just the version (for scripts)
uv version --output-format json # machine-readable
```

Without uv: `uvx --from bump-my-version==1.2.4 bump-my-version bump minor`
(the maintained successor of bump2version) with `[tool.bumpversion]` config,
or edit `[project] version` by hand.

**Dynamic** — the version is derived from the git tag at build time. Two
common plugins:

`hatch-vcs` (with the hatchling backend):

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[project]
dynamic = ["version"]

[tool.hatch.version]
source = "vcs"
```

`uv-dynamic-versioning` (with the uv build backend; VCS-tag-driven,
<https://pypi.org/project/uv-dynamic-versioning/>):

```toml
[build-system]
requires = ["uv_build", "uv-dynamic-versioning"]
build-backend = "uv_build"

[project]
dynamic = ["version"]

[tool.uv-dynamic-versioning]
vcs = "git"
```

Tag `v0.3.1`; the build strips the leading `v` for the wheel version. Building
from an untagged commit yields a dev/local version — fine for CI, wrong for a
release, so release builds must run on the tag ref.

Trade-off summary: dynamic makes tag/version divergence impossible and removes
bump commits, at the cost of `uv version` introspection, a build-time plugin
dependency, and less obvious behavior for contributors. Static keeps the
version readable in git history but drifts from the tag if a bump is
forgotten (the audit script checks this). Changing the build backend itself is
python-packaging territory — if the project is not already on hatchling or
`uv_build`, weigh that migration separately.

## Single-sourcing the version

Whatever the strategy, expose the version at runtime via metadata, not a
duplicated literal:

```python
from importlib.metadata import version
__version__ = version("your-package-name")
```

If a literal `__version__` must stay (e.g., public API promise), make the bump
tool own it — PSR: `version_variables = ["src/pkg/__init__.py:__version__"]`;
bump-my-version: a `[[tool.bumpversion.files]]` entry. A hand-maintained copy
*will* drift — the "forgot to bump, users silently never update" failure is
endemic wherever versions are duplicated.

## Release tool landscape

Fragmented — no npm-style default exists. Three philosophies:

| Tool | Philosophy | Notes |
| --- | --- | --- |
| `uv version` + git tag (manual) | Human decides everything | Zero dependencies; the default in this skill |
| [release-please](https://github.com/googleapis/release-please-action) | Semi-autonomous: maintains a standing Release PR (version + changelog from conventional commits); merging it ships | Built-in human gate; needs a PAT/App token so the release PR and tag trigger downstream CI |
| [python-semantic-release](https://python-semantic-release.readthedocs.io/) (PSR) | Fully autonomous: computes bump from commits on every push to main, writes changelog, tags, publishes | Most-cited Python option; official uv integration guide |
| [semantic-release](https://github.com/semantic-release/semantic-release) + [semantic-release-uv](https://github.com/Deltamir/semantic-release-uv) | JS ecosystem's tool driving a Python package | Only worth it for teams already invested in Node semantic-release |
| [Changesets](https://github.com/changesets/changesets)-style: Sampo | Contributors write a short human changeset per PR; tool batches into bump + changelog | Best changelog quality and monorepo story; Python-side tools are young — evaluate maturity |
| [git-cliff](https://github.com/orhun/git-cliff) | Changelog-only generator (`[tool.git-cliff]` in pyproject.toml) | Pair with any bump strategy |
| bump-my-version / bump2version, uv-version-bumper, semversioner | Minimal multi-file bump helpers | Small packages that want no CI orchestration |

Decision guide: zero-touch on every merge + strict commit discipline → PSR;
human review gate with automation → release-please; changelog quality or
monorepo → changesets-style; everything else → manual `uv version` + tag.

## python-semantic-release + uv configuration

The canonical config (official guide:
<https://python-semantic-release.readthedocs.io/en/latest/configuration/configuration-guides/uv_integration.html>):

```toml
[tool.semantic_release]
version_toml = ["pyproject.toml:project.version"]
build_command = "uv lock --upgrade-package your-package-name && uv build"
commit_message = "chore(release): {version}"
tag_format = "v{version}"
commit_parser = "conventional"
allow_zero_version = true   # keep 0.x versions; otherwise PSR jumps to 1.0.0
```

Non-negotiables that break silently when missed:

- `build_command` must refresh `uv.lock` (above) **and** PSR must be
  configured to commit the lockfile with the bump — add `uv.lock` to
  `[tool.semantic_release].assets` so the release commit includes it.
- `actions/checkout` with `fetch-depth: 0` — with a shallow clone PSR computes
  no bump or the wrong bump, with no error.
- `concurrency: release` (`cancel-in-progress: false`) on the workflow to
  prevent racing pushes from double-releasing.
- The pushing token needs `contents: write`, and a bump commit pushed with the
  default `GITHUB_TOKEN` will NOT trigger other workflows — use a PAT or
  GitHub App token if a tag-triggered publish workflow must fire next.
- Dry-running from a PR ref fails with `ERELEASEBRANCHES`-style errors; test
  release automation on a scratch repo, not via PR dry runs.

Run PSR pinned, via uvx: `uvx --from python-semantic-release==10.6.0
semantic-release version` (pin so a new major of PSR cannot change release
behavior underneath the workflow; check for the current release before
adopting).

## Conventional commits mapping

Commit-driven tools bump from message prefixes: `fix:`/`perf:` → patch,
`feat:` → minor, `BREAKING CHANGE:` footer or `type!:` → major
(`type(scope): description` format). Everything else → no release. Two
operational consequences:

- Non-conforming commits produce **silent non-bumps** (semantic-release issue
  #3642 — closed as not-planned). Automation is only as good as commit
  discipline; enforcement hooks are the python-precommit skill's territory.
- Teams sometimes deliberately under-classify breaking changes as
  minor/patch to avoid alarm — automation encodes the label, not the truth.

## Changelog strategy

Options, most-recommended first:

1. **Keep a Changelog** (<https://keepachangelog.com/en/1.1.0/>) — manual
   `CHANGELOG.md`, `## [Unreleased]` at top with Added / Changed / Deprecated /
   Removed / Fixed / Security subheadings; rename to `## [X.Y.Z] - YYYY-MM-DD`
   at release. Best signal-to-noise for human readers; costs discipline.
2. **Changesets-style** — each PR carries a short human-written note; tooling
   batches notes into the changelog. Best of both where supported.
3. **Commit-scraped** (PSR changelog, git-cliff) — free, but widely criticized
   by practitioners as "technically correct and completely useless" (raw
   `fix:`/`chore:` dumps). Even semantic-release's maintainer recommends
   dropping its changelog plugin when quality matters. Mitigation: have an LLM
   or a human rewrite the generated notes into user-facing prose before the
   GitHub Release is published — draft-then-promote, as in Hugging Face's
   huggingface_hub release pipeline
   (<https://huggingface.co/blog/huggingface-hub-release-ci>), where automation
   drafts from a deterministic PR manifest and a human edits before promotion.

Formatting rule regardless of option: the version string stays bare. Tooling
that emitted `2.1.0 (2026-01-07)` as a "version" has broken strict semver
parsers downstream; keep dates in the heading text, and validate the tag with
a semver check before pushing.

## SemVer caveats

- SemVer encodes the **maintainer's intent** about the declared public API,
  not actual consumer impact — a "patch" can still break someone. Say so in
  release notes when unsure; don't launder breaking changes as patches.
- Pre-releases (`1.2.0rc1`, PEP 440) let you stage on PyPI without becoming
  the default install; TestPyPI is for rehearsing the *pipeline*, pre-releases
  for rehearsing the *code*.
- uv itself versions non-semantically (minor = breaking) — don't parse uv's
  own release stream with SemVer assumptions.
- CalVer is a legitimate minority choice for applications and internal tools;
  libraries on PyPI should stay with SemVer-shaped PEP 440 versions.
