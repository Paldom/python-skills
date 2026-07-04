# PyPI Trusted Publishing (OIDC) — mechanics, troubleshooting, limits

**Contents:** [How it works](#how-it-works) · [Setup](#setup-exact-match-fields) ·
[Troubleshooting invalid-publisher](#troubleshooting-invalid-publisher) ·
[PEP 740 attestations](#pep-740-attestations) · [Known limitations](#known-limitations) ·
[Threat model](#threat-model-risk-relocated-not-removed) · [Token fallback](#token-based-publishing-legacy-fallback)

## How it works

Trusted publishing has been live on PyPI since April 2023 and is the default
recommendation over stored `PYPI_API_TOKEN` secrets (by late 2025 PyPI reported
~45,000 projects configured and more than 25% of monthly uploads, up from ~10%
in early 2024). The exchange:

1. The GitHub Actions job requests an OIDC identity token from GitHub
   (requires `permissions: id-token: write` on the job).
2. The publish tool (`pypa/gh-action-pypi-publish` or `uv publish`) presents
   that token to PyPI.
3. PyPI verifies the token's claims — repository owner, repository name,
   workflow filename, and (if configured) environment — against the registered
   trusted publisher, then mints a short-lived (~15 minutes), package-scoped
   upload token.

Nothing is stored, nothing rotates, nothing can leak from repo secrets. Docs:
<https://docs.pypi.org/trusted-publishers/adding-a-publisher/>.

## Setup (exact-match fields)

- **Never-published project:** <https://pypi.org/manage/account/publishing/> →
  "Add a new pending publisher" (reserves the name; converts to a real project
  on first publish — check the name is free on PyPI first).
- **Existing project:** project page → Settings → Publishing.

Four fields, validated by **exact, case-sensitive match** against the OIDC
token's claims:

| Field | Value | Trap |
| --- | --- | --- |
| Owner | GitHub org/user, exact casing | `MyOrg` ≠ `myorg` |
| Repository | repo name, exact casing | renamed repos need re-registration |
| Workflow filename | bare filename, e.g. `publish.yml` | `.yml` ≠ `.yaml`; not a path; it is the **top-level triggered** workflow's filename |
| Environment (optional, recommended) | e.g. `pypi` | must then equal `environment:` in the publish job |

Setting the environment field is recommended: it lets you attach required
reviewers (the human release gate) and restricts which ref can publish. If the
release process is split across multiple workflow files, each file that
publishes needs its own trusted-publisher entry.

TestPyPI (<https://test.pypi.org>) is a separate registry: register a separate
trusted publisher there for rehearsal publishes.

## Troubleshooting invalid-publisher

Symptom: `invalid-publisher`, `unable to authenticate`, or a confusing E404
even though the package exists. Work through, in order:

1. **Diff every field character-by-character** against the repo: owner casing,
   repo casing, workflow filename including extension, environment name.
2. **Indirection breaks the match.** If publishing happens inside a reusable
   workflow (`workflow_call`), PyPI validates the *calling* workflow's
   filename. Keep the publish step in the directly-triggered file, or register
   the caller's filename.
3. **`environment:` mismatch.** Publisher registered with environment `pypi`
   but the job has no `environment:` key (or a different name) — or vice versa.
4. **Runner type.** Self-hosted runners are not supported; the job must run on
   GitHub-hosted runners.
5. **Missing `id-token: write`.** Note that setting any job-level
   `permissions:` block removes all unlisted permissions — make sure the
   publish job has `id-token: write` itself.
6. **Wrong registry.** Publishing to TestPyPI with only a pypi.org publisher
   registered (or vice versa).

Do **not** "fix" this by falling back to a long-lived API token — the config
mismatch is always findable, and the token reintroduces the exfiltration risk
this setup removes (see community discussion:
<https://github.com/orgs/community/discussions/176761>).

## PEP 740 attestations

- `pypa/gh-action-pypi-publish` generates and uploads PEP 740 digital
  attestations automatically when using trusted publishing — no flags. They
  appear on the file detail pages on PyPI.
- Attestations prove **which workflow run built the artifact** — provenance,
  not safety. Real campaigns have produced validly-signed malicious packages
  by compromising the pipeline itself ("the signature is real; the software is
  not"). Treat attestations as an audit trail, not a guarantee.
- Attestations from private repositories are not supported.

## Known limitations

- GitHub-hosted runners only (also true on npm); no self-hosted support.
- No trusted-publishing path for non-GitHub/non-supported CI (Jenkins,
  CircleCI, Buildkite) — those setups still need token auth with manual
  rotation. (PyPI also supports GitLab, Google Cloud, and ActiveState as
  publishers; register accordingly if CI lives there.)
- Reusable-workflow (`workflow_call`) setups have the filename-match caveat
  above.
- The OIDC token is short-lived but a compromised job can still request one
  during its run — trusted publishing does not eliminate in-run compromise.

## Threat model: risk relocated, not removed

Stored-token risk (the 2025 PyPI token-exfiltration campaign:
<https://blog.pypi.org/posts/2025-09-16-github-actions-token-exfiltration/>)
is gone, but the CI workflow is now the trust boundary. An attacker who can
inject a step before publish — via a compromised third-party action (the
tj-actions mutable-tag hijack, March 2025) or a `pull_request_target` hole —
publishes malware with valid attestations. Consequences for release design:

- Publish job gets `id-token: write` and nothing else; workflow default is
  `permissions: {}`.
- Pin every action to a full commit SHA (tag comments for humans); refresh via
  `gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`.
- The publish job should not check out or execute project code — build in a
  separate job and pass `dist/` as an artifact.
- Gate the environment with required reviewers; protect release tags with a
  ruleset so published tags cannot be re-pointed.
- After OIDC works, revoke leftover project API tokens; a compromised PyPI
  account can otherwise mint a new token and bypass the OIDC flow.
- CODEOWNERS on `.github/workflows/` and repo-wide workflow hardening are
  worth doing but belong to the python-ci / python-supply-chain skills.
- Minority hardened practice: register a separate minimal private repo as the
  trusted publisher instead of the public source repo, shrinking the
  public-facing attack surface
  (<https://www.reddit.com/r/Python/comments/1s3r43d/dont_make_your_package_repos_trusted_publishers/>).

## Token-based publishing (legacy fallback)

For environments where trusted publishing cannot work: create a
**project-scoped** (never account-scoped) API token, store it as a CI secret,
and pass it via `UV_PUBLISH_TOKEN` (uv) or `password:` (PyPA action). Treat it
as legacy: rotate it, and migrate to OIDC when the pipeline moves to a
supported CI.
