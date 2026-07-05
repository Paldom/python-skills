---
name: python-release
description: Cuts and automates releases of a Python package — version bumps, changelogs, git tags, PyPI trusted publishing (OIDC), and the tag-triggered publish workflow with a gated environment. Use for 'cut a release', 'publish to PyPI', 'bump the version', 'automate releases', 'set up trusted publishing'. Not for packaging metadata, build backends, or non-release CI.
license: MIT
---

# python-release

Take a Python package from "the code is ready" to "the new version is on PyPI"
with a repeatable, secured release pipeline: a deliberate versioning strategy,
bump + changelog + tag, OIDC trusted publishing, and a tag-triggered GitHub
Actions publish workflow with a human gate. This skill exists because release
automation fails in specific, repeatable ways: `uv.lock` desync after a version
bump, trusted-publisher exact-match mismatches producing `invalid-publisher`
errors, tags created with `GITHUB_TOKEN` that never trigger the publish
workflow, and commit-scraped changelogs nobody can read.

Commands below use `uv`/`uvx`. Without uv, substitute `python3 -m build` +
`twine upload` for build/publish, edit `[project] version` by hand, and run
pinned tools via `pip install <pkg>==<version>` — noted here once.

## When NOT to use

- `pyproject.toml` metadata, build backend choice, src layout, building or
  verifying wheels/sdists — the python-packaging skill, if installed, covers that.
- Lint/type/test CI quality gates, matrices, required checks, general workflow
  hardening — the python-ci skill.
- Dependabot, pip-audit, secret scanning, SBOMs, CODEOWNERS — the
  python-supply-chain skill.
- Enforcing conventional-commit messages with git hooks — the python-precommit
  skill (this skill only consumes the convention).
- Writing announcement prose or marketing copy for a release — no skill needed.

## Workflow

### 1. Take stock of the repo

Run the audit script first — it detects most of the failure modes this skill fixes:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/check_release_setup.py" --repo .
```

Then confirm by hand:

- Package name in `[project]`. Check `https://pypi.org/project/<name>/` NOW —
  name collisions surface embarrassingly late, at first upload.
- Where the version lives: static `project.version`, a duplicated
  `__init__.py` `__version__`, or dynamic (`hatch-vcs` / `uv-dynamic-versioning`).
- Existing tags and their format (`git tag --list 'v*'`), existing
  `CHANGELOG.md`, existing publish workflow, and any `PYPI_API_TOKEN` /
  `UV_PUBLISH_TOKEN` secrets to retire.

### 2. Choose a versioning strategy (deliberately — this is unsettled)

There is no community consensus; pick one on purpose and record it:

| Strategy | How | Choose when | Cost |
| --- | --- | --- | --- |
| **Static** (default here) | `uv version --bump patch\|minor\|major` rewrites `project.version` and refreshes `uv.lock` | You want explicit, readable version history in git | Needs a bump commit; can drift from the tag if a bump is forgotten |
| **Dynamic** (git-tag-derived) | `hatch-vcs` or `uv-dynamic-versioning` computes the version from the tag at build time | Tag and package version must never diverge; no bump commits wanted | Disables `uv version` introspection; adds a build-time plugin; opaque to newcomers |

Either way: `pyproject.toml` (or the tag) is the single source of truth. Do not
maintain a hand-written `__version__` in `__init__.py` — read it at runtime:

```python
from importlib.metadata import version
__version__ = version("your-package-name")
```

Configs for both strategies: [references/versioning-and-changelog.md](references/versioning-and-changelog.md).

### 3. Choose the automation level (three philosophies)

The Python release-tool landscape is fragmented — there is no npm-style "just
install semantic-release" default. Three workable levels:

| Level | Tool | Ship trigger | Best for |
| --- | --- | --- | --- |
| **Human-cut, tag-driven** (default here) | `uv version` + git tag; CI publishes on the tag | Maintainer pushes a `v*` tag | Most packages; no commit-discipline dependency |
| **PR-gated automation** | release-please — maintains a standing Release PR with version + changelog | Human merges the Release PR | Teams wanting automation with a review gate |
| **Fully automated** | python-semantic-release (PSR) from conventional commits | Every qualifying push to main | Strict conventional-commits discipline, high release cadence |

Default to human-cut unless the user asks for more automation: it is the only
level with zero dependence on commit-message discipline, and every source on
agentic/automated releases converges on automating the mechanical steps while
keeping a human on "should this ship". Full PSR and release-please workflow
YAML: [references/publish-workflows.md](references/publish-workflows.md).

### 4. Choose a changelog strategy

- **Default: Keep a Changelog.** Maintain `CHANGELOG.md` with an
  `## [Unreleased]` section (subheadings from the spec vocabulary: Added /
  Changed / Deprecated / Removed / Fixed / Security). At release time, rename
  it to `## [X.Y.Z] - YYYY-MM-DD` and start a fresh Unreleased section.
- **Commit-scraped** (PSR default, or `git-cliff`): zero effort, but
  practitioners widely deride raw commit dumps as "technically correct and
  completely useless" for end users. If chosen, either post-process into
  user-facing prose before publishing, or accept the trade-off knowingly.
- Never let tooling append dates or any extra text into the **version string
  itself** — `2.1.0 (2026-01-07)` breaks strict semver parsers downstream.
  Dates belong in the heading, outside the version.

### 5. Register the trusted publisher on PyPI

OIDC trusted publishing replaces long-lived API tokens: PyPI mints a
short-lived (~15 min), package-scoped token for the exact workflow identity —
nothing stored, nothing to rotate or exfiltrate. Configure it BEFORE the first
workflow run:

1. New (never-published) project: <https://pypi.org/manage/account/publishing/>
   → "Add a new pending publisher". Existing project: project page → Settings →
   Publishing.
2. Fill the four fields — validation is an **exact, case-sensitive match**:
   - Owner (GitHub org/user) and repository name, exact casing.
   - Workflow filename — the bare filename with extension, e.g. `publish.yml`
     (not a path, not `publish.yaml` if the file is `.yml`).
   - Environment name: `pypi` (recommended; must then match `environment:` in
     the job).
3. In the repo: Settings → Environments → `pypi` → add required reviewers.
   This is the human release gate — the publish job pauses for approval.
   (Environment protection rules require a public repo or a paid plan.)
4. After the first successful OIDC publish, revoke any leftover project-scoped
   API tokens — a compromised account can otherwise mint a token and publish
   around the OIDC flow entirely.

Full mechanics, limitations, and threat model:
[references/trusted-publishing.md](references/trusted-publishing.md).

### 6. Write the publish workflow

Tag-triggered, split into test → build → publish so the job holding the OIDC
permission never checks out or executes project code:

```yaml
# .github/workflows/publish.yml — filename must match the trusted-publisher entry
name: Publish

on:
  push:
    tags: ["v*.*.*"]

permissions: {} # deny-all default; each job requests only what it needs

jobs:
  test:
    # A tag push does NOT inherit the tagged commit's CI status — re-run the
    # quality gate here (or reuse your CI via workflow_call) before publishing.
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3
      - uses: astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0
      - run: uv sync --locked # fails loudly if uv.lock desynced from pyproject.toml
      - run: uv run pytest

  build:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3
      - uses: astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0
      - run: uv build
      - run: uvx --from twine==6.2.0 twine check --strict dist/*
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: dist
          path: dist/

  publish:
    needs: build
    runs-on: ubuntu-latest # GitHub-hosted only; OIDC fails on self-hosted runners
    environment: pypi # the gated environment — must match the PyPI publisher entry
    permissions:
      id-token: write # the only write permission publishing needs
    steps:
      - uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b # v1.14.0
        with:
          skip-existing: true # re-runs after partial failure become idempotent
```

Notes on this shape:

- `pypa/gh-action-pypi-publish` generates **PEP 740 attestations** automatically
  under trusted publishing — no extra flags. (`uv publish` also auto-detects the
  OIDC token if you prefer one tool; see the reference for that variant.)
- Every action is pinned to a full commit SHA with the tag in a comment.
  Mutable tags get hijacked (tj-actions, March 2025) — and the publish workflow
  is the highest-value target in the repo. Refresh a pin with:
  `gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`.
- Keep the publish step in this directly-triggered file. Moving it behind
  `workflow_call` indirection breaks the trusted-publisher exact match — PyPI
  validates against the top-level workflow's filename.
- Do not add `contents: write` here; publishing needs none. If you also create
  GitHub Releases, do it in a separate job with its own minimal permission.

Re-run `python3 "${CLAUDE_SKILL_DIR}/scripts/check_release_setup.py"` — it verifies trigger,
permissions, environment, SHA pinning, and leftover token secrets.

### 7. Cut a release (the repeatable manual flow)

```bash
uv version --bump minor          # rewrites pyproject.toml AND refreshes uv.lock
VERSION="$(uv version --short)"

# Roll CHANGELOG.md's Unreleased section into "## [$VERSION] - $(date +%F)"

git add pyproject.toml uv.lock CHANGELOG.md
git commit -m "chore(release): v${VERSION}"
git tag -a "v${VERSION}" -m "v${VERSION}"
git push origin main "v${VERSION}"
```

Then approve the `pypi` environment gate when the workflow pauses, and verify.

If anything other than `uv version` performed the bump (PSR, bump-my-version,
a hand edit), refresh and commit the lockfile **in the same commit**:

```bash
uv lock --upgrade-package "<package-name>"
git add uv.lock
```

For the first release ever, rehearse against TestPyPI (isolated index, its own
trusted-publisher entry) before production — recipe in
[references/publish-workflows.md](references/publish-workflows.md).

### 8. Verify the release

- Workflow run green; approval step recorded who released.
- Package page live on PyPI with the new version; file view shows attestations.
- Install from a clean environment:
  `uvx --isolated --from "<package-name>==${VERSION}" python -c "import <module>"`.
- `python3 "${CLAUDE_SKILL_DIR}/scripts/check_release_setup.py"` reports no errors (tag, version,
  and lockfile all agree).

## Output spec — what done looks like

- A recorded versioning decision: static `project.version` (default) or a
  configured dynamic-versioning plugin — never both, never a stray `__version__`.
- `CHANGELOG.md` with the released section and a fresh Unreleased skeleton.
- A trusted publisher registered on PyPI matching the workflow exactly; no
  long-lived PyPI token secrets left in the repo.
- `.github/workflows/publish.yml` — tag-triggered, deny-all default
  permissions, `id-token: write` only on the publish job, gated `pypi`
  environment, all actions SHA-pinned, tests gating the upload.
- An annotated `vX.Y.Z` tag on a commit where `pyproject.toml`, `uv.lock`, and
  the tag agree on the version.
- A green publish run and the version installable from PyPI.

## Failure modes & gotchas

- **`uv.lock` desync (the #1 automated-release breaker).** A bump tool rewrites
  `project.version`; `uv.lock` still records the old version; the next
  `uv sync`/`uv run`/`uv build` fails its freshness check. Fix: run
  `uv lock --upgrade-package <name>` between bump and build and **commit the
  lockfile with the bump commit** — regenerating it ephemerally in the runner
  leaves every clone broken. For PSR, put it in `build_command`.
- **`invalid-publisher` / "unable to authenticate" despite correct-looking
  config.** One field differs from reality: owner/repo casing, workflow
  filename (including `.yml` vs `.yaml`), or environment name — or the publish
  step runs behind `workflow_call`/reusable-workflow indirection, or on a
  self-hosted runner. Checklist in
  [references/trusted-publishing.md](references/trusted-publishing.md).
- **Tag pushed by automation never triggers the publish workflow.** Resources
  created with the default `GITHUB_TOKEN` do not trigger other workflows — a
  GitHub platform rule, not a bug in release-please/PSR. Use a fine-grained PAT
  or a GitHub App token for the tag-creating step.
- **PSR computes no bump or the wrong bump.** Shallow checkout — PSR needs
  `fetch-depth: 0` on `actions/checkout`. Add `concurrency: release` (with
  `cancel-in-progress: false`) so racing pushes don't double-release.
- **Release hangs at the tagging step.** Git is configured to sign tags
  (semantic-release issue #3065). Disable tag signing in CI.
- **Partial failure leaves a dead tag.** semantic-release/PSR tag and create
  the GitHub Release before uploading and do not roll back if the upload fails.
  `skip-existing: true` makes re-runs idempotent; if atomicity matters, order
  the pipeline compute-version → publish → tag last.
- **Silent non-bumps under commit-driven automation.** Non-conforming commit
  messages simply produce no release (semantic-release issue #3642, closed
  not-planned). For 0.x packages, set PSR's `allow_zero_version = true`; the JS
  semantic-release declares 0.x semantics out of scope entirely.
- **`uv version --bump` side effects.** It syncs the environment as a side
  effect and cannot update files beyond `pyproject.toml` (uv issues #15286,
  #13827) — another reason to drop hand-written `__version__` attributes.
- **Multi-index `uv publish` footguns.** `uv publish` cannot find an index
  configured with `explicit = true` (uv issue #9919); the index `url` (used by
  `--check-url` to detect already-uploaded files) is distinct from
  `publish_url`. Also, uv ≥ 0.11.22 uploads wheels before sdists — don't
  assume sdist-first ordering.
- **Branch protection blocks the release bot's bump commit.** Give a dedicated
  GitHub App a targeted ruleset bypass; do not hand the bot admin rights, and
  protect tags with a ruleset so a released `vX.Y.Z` cannot be re-pointed.
- **Trusted publishing relocates risk rather than removing it.** The CI runner
  is the new trust boundary: a step injected before publish ships malware with
  valid attestations. Minimal permissions + SHA pinning (above) are part of the
  release design; repo-wide workflow hardening belongs to the python-ci and
  python-supply-chain skills.

## Bundled resources

- [references/trusted-publishing.md](references/trusted-publishing.md) — OIDC
  mechanics, exact-match troubleshooting, PEP 740 attestations, limitations,
  threat model.
- [references/versioning-and-changelog.md](references/versioning-and-changelog.md)
  — static/dynamic configs, tool landscape (PSR, release-please, git-cliff,
  bump-my-version, …), PSR + uv config, changelog strategies, SemVer caveats.
- [references/publish-workflows.md](references/publish-workflows.md) — complete
  workflow variants: PSR push-to-main, release-please, TestPyPI rehearsal,
  `uv publish` instead of the PyPA action.
- `scripts/check_release_setup.py` — read-only audit of version/lockfile/tag
  agreement and publish-workflow hygiene; non-zero exit on errors.
