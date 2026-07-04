#!/usr/bin/env python3
"""Read-only audit of a Python package repo's release setup.

Checks the failure modes that break automated releases:
  - uv.lock desync (lockfile version != pyproject version)  [the #1 breaker]
  - git tag / pyproject version disagreement
  - publish workflow hygiene: tag trigger, id-token: write, gated environment,
    SHA-pinned actions, no pull_request_target, no leftover long-lived tokens

This script NEVER modifies the repository — it only reads files and runs
read-only `git tag` commands.

Usage:
    python3 check_release_setup.py [--repo PATH] [--strict]

Output: one `LEVEL <check-id> <path>: message` line per finding
(LEVEL in {ERROR, WARN, OK, INFO}), then a summary line.
Exit codes: 0 = no errors (warnings allowed unless --strict),
1 = errors found, 2 = cannot run (bad invocation / unsupported Python).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    print("ERROR python-version -: needs Python 3.11+ (tomllib)", file=sys.stderr)
    sys.exit(2)

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_PREFIX_RE = re.compile(r"^v?(\d+(?:\.\d+)*)")
USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*([^\s#]+)", re.MULTILINE)
TOKEN_HINTS = ("PYPI_API_TOKEN", "UV_PUBLISH_TOKEN", "TWINE_PASSWORD", "TWINE_USERNAME")
PUBLISH_HINTS = ("pypi", "uv publish", "twine upload")

findings: list[tuple[str, str, str, str]] = []  # (level, check, path, msg)


def add(level: str, check: str, path: str, msg: str) -> None:
    findings.append((level, check, path, msg))


def normalize(name: str) -> str:
    """PEP 503 name normalization."""
    return re.sub(r"[-_.]+", "-", name).lower()


def release_tuple(version: str) -> tuple[int, ...] | None:
    """Numeric release segment of a version/tag ('v1.2.3rc1' -> (1, 2, 3))."""
    m = VERSION_PREFIX_RE.match(version.strip())
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split("."))


def load_toml(path: Path) -> dict | None:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        add("ERROR", "toml-parse", str(path), f"cannot parse: {exc}")
        return None


def check_pyproject(repo: Path) -> tuple[str | None, str | None, bool]:
    """Return (normalized_name, static_version, is_dynamic)."""
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        add("ERROR", "pyproject-missing", str(pyproject), "no pyproject.toml — nothing to release")
        return None, None, False
    data = load_toml(pyproject)
    if data is None:
        return None, None, False
    project = data.get("project", {})
    name = project.get("name")
    if not name:
        add("ERROR", "project-name", str(pyproject), "[project] has no name")
        return None, None, False
    dynamic = "version" in project.get("dynamic", [])
    version = project.get("version")
    if dynamic:
        add("OK", "version-mode", str(pyproject), "dynamic versioning (git-tag-derived); skipping static version checks")
        return normalize(name), None, True
    if not version:
        add("ERROR", "version-missing", str(pyproject), "[project] has neither version nor dynamic = [\"version\"]")
        return normalize(name), None, False
    add("OK", "version-mode", str(pyproject), f"static version {version}")
    return normalize(name), str(version), False


def check_lock_desync(repo: Path, name: str, version: str) -> None:
    lock = repo / "uv.lock"
    if not lock.is_file():
        add("INFO", "uv-lock", str(lock), "no uv.lock (not uv-managed, or lockfile not committed)")
        return
    data = load_toml(lock)
    if data is None:
        return
    for pkg in data.get("package", []):
        if normalize(str(pkg.get("name", ""))) == name:
            locked = str(pkg.get("version", ""))
            if locked == version:
                add("OK", "lock-sync", str(lock), f"uv.lock agrees with pyproject.toml ({version})")
            else:
                add(
                    "ERROR", "lock-desync", str(lock),
                    f"uv.lock records {locked} but pyproject.toml says {version} — "
                    f"run `uv lock --upgrade-package {name}` and commit uv.lock with the bump",
                )
            return
    add("WARN", "lock-entry", str(lock), f"no package entry named {name!r} found in uv.lock")


def check_tags(repo: Path, version: str | None, dynamic: bool) -> None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "tag", "--list"],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        add("INFO", "git-tags", str(repo), "not a git repo or git unavailable — skipping tag checks")
        return
    tagged = [(release_tuple(t), t) for t in out.split() if release_tuple(t)]
    if not tagged:
        add("INFO", "git-tags", str(repo), "no version-shaped tags yet (first release pending)")
        return
    latest_tuple, latest_tag = max(tagged)
    if dynamic or version is None:
        add("OK", "git-tags", str(repo), f"latest version tag {latest_tag}")
        return
    current = release_tuple(version)
    if current == latest_tuple:
        add("OK", "tag-sync", str(repo), f"pyproject version {version} matches latest tag {latest_tag}")
    elif current and current < latest_tuple:
        add(
            "ERROR", "tag-behind", str(repo),
            f"latest tag {latest_tag} is AHEAD of pyproject version {version} — "
            "a bump was forgotten or the tag was cut from the wrong commit",
        )
    else:
        add("INFO", "tag-sync", str(repo), f"pyproject {version} > latest tag {latest_tag} (unreleased bump pending)")


def workflow_files(repo: Path) -> list[Path]:
    wf_dir = repo / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    return sorted(p for p in wf_dir.iterdir() if p.suffix in (".yml", ".yaml") and p.is_file())


def check_workflows(repo: Path) -> None:
    files = workflow_files(repo)
    if not files:
        add("WARN", "workflows", str(repo / ".github" / "workflows"), "no workflows directory — no publish automation")
        return
    publish_found = False
    for wf in files:
        try:
            text = wf.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            add("WARN", "workflow-read", str(wf), f"cannot read: {exc}")
            continue
        low = text.lower()
        for hint in TOKEN_HINTS:
            if hint in text:
                add("WARN", "legacy-token", str(wf), f"references {hint} — long-lived token publishing; migrate to trusted publishing (OIDC)")
        if not any(h in low for h in PUBLISH_HINTS):
            continue
        publish_found = True
        check_publish_workflow(wf, text, low)
    if not publish_found:
        add("WARN", "publish-workflow", str(repo / ".github" / "workflows"), "no publish workflow detected (no file mentions pypi / uv publish / twine upload)")


def check_publish_workflow(wf: Path, text: str, low: str) -> None:
    rel = str(wf)
    # Heuristic checks: line-oriented regexes, not a YAML parse. Good enough to
    # catch the standard misconfigurations; a hand-obfuscated workflow can fool them.
    if "pull_request_target" in low:
        add("ERROR", "dangerous-trigger", rel, "publish-related workflow triggered by pull_request_target — a fork PR can run with secrets/OIDC access")
    if re.search(r"^\s*tags:", text, re.MULTILINE) or "release:" in text:
        add("OK", "tag-trigger", rel, "tag/release-triggered")
    else:
        add("WARN", "tag-trigger", rel, "no tag trigger found — packages should publish on explicit version tags, not every push")
    if re.search(r"^\s*id-token:\s*write", text, re.MULTILINE):
        add("OK", "id-token", rel, "id-token: write present (OIDC)")
    elif not any(hint in text for hint in TOKEN_HINTS):
        add("ERROR", "id-token", rel, "no `id-token: write` and no token secret — trusted publishing will fail to authenticate")
    if re.search(r"^\s*environment:", text, re.MULTILINE):
        add("OK", "environment", rel, "gated environment present")
    else:
        add("WARN", "environment", rel, "no `environment:` on the publish job — no human approval gate, and the PyPI publisher entry cannot pin one")
    if re.search(r"^\s*workflow_call:", text, re.MULTILINE):
        add("WARN", "workflow-call", rel, "publish logic behind workflow_call — PyPI validates the CALLING workflow's filename; exact-match may fail")
    if re.search(r"^\s*contents:\s*write", text, re.MULTILINE):
        add("WARN", "contents-write", rel, "contents: write in a publishing workflow — publishing needs none; keep tag-writing jobs in a separate workflow")
    for ref in USES_RE.findall(text):
        if ref.startswith(("./", "docker://")):
            continue
        _, _, pin = ref.partition("@")
        if not pin:
            add("WARN", "unpinned-action", rel, f"`{ref}` has no ref at all")
        elif not SHA40_RE.match(pin):
            add("WARN", "unpinned-action", rel, f"`{ref}` pinned to a mutable ref — pin to a full 40-char commit SHA (mutable tags get hijacked)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, default=Path("."), help="repo root to audit (default: cwd)")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args()

    repo = args.repo.resolve()
    if not repo.is_dir():
        print(f"ERROR bad-repo {repo}: not a directory", file=sys.stderr)
        return 2

    name, version, dynamic = check_pyproject(repo)
    if name and version:
        check_lock_desync(repo, name, version)
    check_tags(repo, version, dynamic)
    check_workflows(repo)

    n_err = n_warn = 0
    for level, check, path, msg in findings:
        line = f"{level} {check} {path}: {msg}"
        if level == "ERROR":
            n_err += 1
            print(line, file=sys.stderr)
        elif level == "WARN":
            n_warn += 1
            print(line, file=sys.stderr)
        else:
            print(line)
    failed = n_err + (n_warn if args.strict else 0)
    print(f"{'FAIL' if failed else 'OK'}: {n_err} error(s), {n_warn} warning(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
