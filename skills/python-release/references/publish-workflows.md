# Publish workflow variants

**Contents:** [uv publish instead of the PyPA action](#uv-publish-instead-of-the-pypa-action) ·
[PSR push-to-main](#python-semantic-release-on-push-to-main) ·
[release-please](#release-please-pr-gated) · [TestPyPI rehearsal](#testpypi-rehearsal) ·
[Refreshing action pins](#refreshing-action-pins)

The canonical tag-triggered workflow lives in SKILL.md step 6. All variants
keep the same invariants: deny-all default permissions, `id-token: write` only
where publishing happens, a gated environment, actions pinned to full commit
SHAs (mutable tags get hijacked — tj-actions, March 2025), and tests gating
the upload because a tag push does not inherit the tagged commit's CI status.

## uv publish instead of the PyPA action

`uv publish` auto-detects the OIDC token on GitHub Actions — no token flag, no
secret. Swap the publish job's last step:

```yaml
  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1
        with:
          name: dist
          path: dist/
      - uses: astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0
      - run: uv publish
```

Trade-off vs `pypa/gh-action-pypi-publish`: one tool for the whole pipeline,
but check current uv release notes for attestation behavior before relying on
PEP 740 attestations from this path — the PyPA action generates them
automatically under trusted publishing. Multi-index caveats: `uv publish`
cannot resolve an index configured with `explicit = true`
(<https://github.com/astral-sh/uv/issues/9919>), and `--check-url` (or the
index's `url` next to `publish_url`) is what makes re-runs skip
already-uploaded files.

## python-semantic-release on push to main

Fully automated bump + changelog + tag + GitHub Release from conventional
commits. Pair with the tag-triggered publish workflow from SKILL.md: PSR
pushes the tag, the publish workflow uploads. That split keeps the PyPI OIDC
permission out of the job that runs with `contents: write`.

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    branches: [main]

permissions: {}

concurrency:
  group: release
  cancel-in-progress: false # never kill a half-finished release

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write # push the bump commit + tag
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3
        with:
          fetch-depth: 0 # PSR silently mis-computes the bump on shallow clones
          token: ${{ secrets.RELEASE_BOT_TOKEN }} # PAT/App token, NOT GITHUB_TOKEN
      - uses: astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0
      - name: Semantic release
        env:
          GH_TOKEN: ${{ secrets.RELEASE_BOT_TOKEN }}
        run: uvx --from python-semantic-release==10.6.0 semantic-release version
```

Why the PAT/App token matters twice:

- Tags/commits created with the default `GITHUB_TOKEN` do **not** trigger the
  tag-triggered publish workflow (GitHub platform rule) — the release would
  tag and then nothing ships.
- Branch protection on `main` blocks the bot's bump commit; give a dedicated
  GitHub App a targeted ruleset bypass rather than admin rights.

Also required: the `[tool.semantic_release]` config from
[versioning-and-changelog.md](versioning-and-changelog.md), including the
`uv lock --upgrade-package` build command and committing `uv.lock` with the
bump. Disable git tag signing in CI or the release hangs at tagging
(semantic-release issue #3065).

## release-please (PR-gated)

Maintains a standing Release PR; merging it creates the tag and GitHub
Release, which then fires the tag-triggered publish workflow:

```yaml
# .github/workflows/release-please.yml
name: release-please

on:
  push:
    branches: [main]

permissions: {}

jobs:
  release-please:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: googleapis/release-please-action@45996ed1f6d02564a971a2fa1b5860e934307cf7 # v5.0.0
        with:
          release-type: python
          token: ${{ secrets.RELEASE_BOT_TOKEN }} # so the release PR runs CI and the tag triggers publish
```

Notes:

- `release-type: python` updates `pyproject.toml` (and `CHANGELOG.md`); the
  release PR is the human gate — review the proposed version and edit the
  changelog text there (curated notes beat raw commit scrapes).
- The default `GITHUB_TOKEN` would create a release PR whose CI never runs and
  a tag that never triggers publishing — same platform rule as above; use a
  PAT or App token.
- release-please does not know about `uv.lock`. Add a small workflow step (or
  a bot job on the release PR) that runs
  `uv lock --upgrade-package <package-name>` and commits the lockfile to the
  release PR branch, so the bump commit and lockfile land together.

## TestPyPI rehearsal

Rehearse the whole pipeline before the first real publish:

1. Register a trusted publisher on <https://test.pypi.org> (separate registry,
   separate "pending publisher" entry; same exact-match rules) with
   environment `testpypi`.
2. Duplicate the publish job with the TestPyPI repository URL:

```yaml
  publish-testpypi:
    needs: build
    runs-on: ubuntu-latest
    environment: testpypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b # v1.14.0
        with:
          repository-url: https://test.pypi.org/legacy/
          skip-existing: true
```

3. Install from TestPyPI in a clean environment to verify (dependencies still
   resolve from real PyPI):
   `uv pip install --index-url https://test.pypi.org/simple/ --index-strategy unsafe-best-match <package-name>`
4. Once green, delete or gate the TestPyPI job; some teams keep it as an
   early-access channel for pushes to main.

TestPyPI projects are isolated from production PyPI and periodically pruned —
never depend on them.

## Refreshing action pins

Pinned SHAs in these recipes were resolved at authoring time (tags in the
trailing comments). To bump a pin:

```bash
gh api repos/actions/checkout/commits/v6.0.3 --jq .sha
```

Update the SHA and the comment together — a comment that lies about the SHA is
worse than no comment. Automated pin updates (Dependabot/Renovate for actions)
are the python-supply-chain skill's territory.
