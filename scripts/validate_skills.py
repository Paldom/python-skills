#!/usr/bin/env python3
"""Deterministic validator for Agent Skills repositories.

Validates SKILL.md frontmatter, eval files, and plugin manifests using only the
Python standard library. It deliberately does NOT use a lenient YAML parser: it
enforces the strict subset of YAML that loads correctly in every Agent Skills
runtime, and errors on constructions that real parsers accept but that break or
degrade skills in practice.

Usage:
    python3 scripts/validate_skills.py                     # validate repo (cwd = root)
    python3 scripts/validate_skills.py --root P            # validate repo at P
    python3 scripts/validate_skills.py --file F [--root P] # single SKILL.md (hook mode)
    python3 scripts/validate_skills.py --strict            # warnings become errors

Exit codes: 0 = OK (warnings allowed unless --strict), 1 = validation errors.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RESERVED_IN_NAME = ("claude", "anthropic")
PLACEHOLDER_RE = re.compile(
    r"\{\{(REPO_NAME|REPO_TITLE|REPO_DESCRIPTION|GITHUB_OWNER|YEAR|IDEA|MODE)\}\}"
)
BLOCK_SCALAR_RE = re.compile(r"^[|>](?:[0-9]+[+-]?|[+-][0-9]*)?$")
NON_STRING_VALUES = {"[]", "{}", "null", "~", "true", "false", "yes", "no", "on", "off"}
NUMERIC_DATE_RE = re.compile(r"[-+]?[0-9][0-9_,.eE+-]*|\d{4}-\d{2}-\d{2}([Tt ].*)?")
VALID_DQ_ESCAPES = set('0abtnvfre"/\\N_LP xuU\t')
KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):(?:\s+(.*))?$")
KEY_NO_SPACE_RE = re.compile(r"^[A-Za-z0-9_-]+:\S")
EVAL_TYPES = {"should_trigger", "should_not_trigger", "quality"}
KNOWN_KEYS = {
    "name",
    "description",
    "when_to_use",
    "argument-hint",
    "allowed-tools",
    "disable-model-invocation",
    "user-invocable",
    "model",
    "effort",
    "context",
    "agent",
    "paths",
    "hooks",
    "license",
    "version",
    "author",
    "homepage",
    "tags",
    "category",
    "metadata",
}
# --- security: what an installed skill must never do -------------------------
# A skill is instructions plus scripts that land in someone else's agent after
# `npx skills add`. Registry scanners flag these patterns, and audits keep finding
# them in the wild (credential harvesting, remote payloads, instructions that hide
# behaviour from the user). Cheap, high-precision checks only: a noisy security
# gate gets ignored, which is worse than no gate.
SECURITY_RULES: tuple[tuple[re.Pattern[str], bool, str], ...] = (
    (
        re.compile(r"(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z|d)?sh\b"),
        True,
        "pipes a download straight into a shell — the classic remote-payload pattern; "
        "download to a file, show the user, then run it",
    ),
    (
        re.compile(r"\b(?:printenv|env)\b[^\n|]*\|[^\n]*\b(?:curl|wget|nc|netcat)\b"),
        True,
        "pipes the environment into a network command — this is credential exfiltration",
    ),
    (
        re.compile(r"base64\s+(?:-d|--decode)[^\n|]*\|\s*(?:ba|z)?sh\b"),
        True,
        "decodes base64 straight into a shell — obfuscated execution, never legitimate here",
    ),
    (
        re.compile(r"shell\s*=\s*True"),
        True,
        "uses shell=True — pass an argv list instead so arguments can never become commands",
    ),
    (
        re.compile(r"~/\.aws/credentials|~/\.ssh/id_|\bid_rsa\b|~/\.netrc"),
        False,
        "references a credential file — if the skill genuinely needs it, say why in the body; "
        "scanners and reviewers treat this as harvesting",
    ),
    (
        re.compile(
            r"ignore\s+(?:all\s+)?(?:previous|prior|earlier)\s+instructions"
            r"|disregard\s+(?:all\s+)?(?:previous|prior)\s+"
            r"|(?:without|don't|do not)\s+(?:telling|informing|notifying)\s+the\s+user"
            r"|hide\s+(?:this|it)\s+from\s+the\s+user",
            re.I,
        ),
        False,
        "contains an instruction-override or user-concealment phrase — the signature of a "
        "prompt-injection payload; rephrase so the intent is plain",
    ),
)
SCANNED_SUFFIXES = {".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".ts"}
# A skill may bundle a whole repo scaffold under assets/template/ (create-skill-repo
# does). Those files are not payload this skill executes — they are copies of the
# gate itself, so scanning them flags the scanner's own rule definitions and its
# test fixtures. They stay covered by check_sync.py and by code review of scripts/**.
NESTED_SCAFFOLD = ("assets", "template")

MAX_NAME_LEN = 64
MAX_DESC_LEN = 1024
DESC_SWEET_MAX = 400
MAX_BODY_LINES = 500
MAX_FRONTMATTER_LINES = 25
MIN_SHOULD_TRIGGER = 8
MIN_SHOULD_NOT_TRIGGER = 8

errors: list[str] = []
warnings: list[str] = []


def err(path: Path, msg: str) -> None:
    errors.append(f"ERROR {path}: {msg}")


def warn(path: Path, msg: str) -> None:
    warnings.append(f"WARN  {path}: {msg}")


def split_scalar(raw: str):
    """Split a raw frontmatter value into (scalar, problems).

    Handles the strict subset we allow: optional single/double quoting and
    trailing `  # comments` on unquoted values. Returns the effective string
    value a real YAML parser would produce, plus a list of problems.
    """
    problems: list[str] = []
    raw = raw.strip()
    if not raw:
        return "", problems
    if raw.startswith("#"):
        problems.append("value is only a `# comment` — a YAML parser reads this as null/empty")
        return "", problems
    q = raw[0]
    if q in ("'", '"'):
        body_chars = []
        i = 1
        closed_at = None
        while i < len(raw):
            ch = raw[i]
            if q == '"' and ch == "\\" and i + 1 < len(raw):
                if raw[i + 1] not in VALID_DQ_ESCAPES:
                    problems.append(
                        f"invalid YAML escape \\{raw[i + 1]} in double-quoted value — real parsers fail on it"
                    )
                body_chars.append(raw[i : i + 2])
                i += 2
                continue
            if q == "'" and ch == "'" and i + 1 < len(raw) and raw[i + 1] == "'":
                body_chars.append("''")
                i += 2
                continue
            if ch == q:
                closed_at = i
                break
            body_chars.append(ch)
            i += 1
        if closed_at is None:
            problems.append(
                "unterminated quoted value — real YAML parsers fail on this and the skill never loads"
            )
            return "".join(body_chars), problems
        trailing = raw[closed_at + 1 :].strip()
        if trailing and not trailing.startswith("#"):
            problems.append(f"unexpected text after closing quote: {trailing!r} — invalid YAML")
        return "".join(body_chars), problems
    # Unquoted: strip a trailing comment (space + '#'), matching YAML semantics.
    m = re.search(r"\s+#", raw)
    if m:
        problems.append(
            "trailing `# comment` in frontmatter value — a YAML parser strips it; avoid comments on value lines"
        )
        raw = raw[: m.start()].rstrip()
    if ": " in raw:
        problems.append(
            "unquoted value contains `: ` — invalid YAML in a plain scalar (parsers see a nested mapping); quote the value or rephrase without colon-space"
        )
    return raw, problems


def parse_frontmatter(path: Path, text: str):
    """Return (fields, fm_line_count, body_lines) or None on structural failure."""
    if text.startswith("\ufeff"):
        err(path, "file starts with a UTF-8 BOM — frontmatter `---` must be at byte 0")
        text = text.lstrip("\ufeff")
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---" or lines[0][:1].isspace():
        err(path, "frontmatter must start on line 1, column 0, with `---`")
        return None
    close = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---" and not lines[i][:1].isspace():
            close = i
            break
    if close is None:
        err(path, "frontmatter closing `---` not found — the whole file is being read as YAML")
        return None
    fm_lines = lines[1:close]
    body_lines = lines[close + 1 :]

    fields: dict[str, dict] = {}
    current_key: str | None = None
    for ln in fm_lines:
        if "\t" in ln:
            err(path, "tab character in frontmatter — YAML forbids tabs; use spaces")
        if not ln.strip() or ln.lstrip().startswith("#"):
            current_key = None
            continue
        if not ln[0].isspace():
            if KEY_NO_SPACE_RE.match(ln):
                err(
                    path,
                    f"missing space after colon in {ln.split(':', 1)[0]!r}: — `key:value` is invalid YAML (skill silently never loads); write `key: value`",
                )
                # continue parsing as if it were key: value so later checks still run
                key, _, rest = ln.partition(":")
                fields[key] = {
                    "raw": rest.strip(),
                    "block": False,
                    "continued": False,
                    "problems": [],
                }
                current_key = key
                continue
            m = KEY_RE.match(ln)
            if m:
                key = m.group(1)
                raw = (m.group(2) or "").strip()
                if key in fields:
                    err(path, f"duplicate frontmatter key {key!r}")
                is_block = bool(BLOCK_SCALAR_RE.match(raw)) if raw else False
                fields[key] = {"raw": raw, "block": is_block, "continued": False, "problems": []}
                current_key = key
            else:
                err(
                    path,
                    f"unparseable frontmatter line: {ln!r} — one malformed line makes the whole frontmatter fail to load",
                )
                current_key = None
        else:
            if current_key and current_key in fields:
                fields[current_key]["continued"] = True
    for key, field in fields.items():
        if key not in KNOWN_KEYS:
            warn(
                path,
                f"unknown frontmatter key {key!r} — runtimes ignore unrecognized keys silently (typo?)",
            )
        raw = field["raw"]
        if raw.startswith("[") and not (raw.endswith("]") and raw.count("[") == raw.count("]")):
            err(
                path,
                f"frontmatter key {key!r} has an unterminated flow list {raw!r} — invalid YAML, the whole skill fails to load",
            )
        if raw.startswith("{") and not (raw.endswith("}") and raw.count("{") == raw.count("}")):
            err(
                path,
                f"frontmatter key {key!r} has an unterminated flow mapping {raw!r} — invalid YAML, the whole skill fails to load",
            )
        if raw and raw[0] in ("'", '"') and key not in ("name", "description"):
            _, probs = split_scalar(raw)
            for pb in probs:
                err(path, f"{key}: {pb}")
    if len(fm_lines) > MAX_FRONTMATTER_LINES:
        warn(
            path,
            f"frontmatter is {len(fm_lines)} lines (> {MAX_FRONTMATTER_LINES}) — keep it lean; nest extras under metadata:",
        )
    return fields, len(fm_lines), body_lines


def check_skill_md(path: Path, distributed: bool) -> None:
    if path.name != "SKILL.md":
        err(
            path,
            f"skill file must be named exactly SKILL.md (found {path.name!r} — case matters on Linux/CI even when macOS matches it)",
        )
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        err(path, f"cannot read as UTF-8 text: {exc}")
        return

    for m in PLACEHOLDER_RE.finditer(text):
        err(path, f"leftover template placeholder {m.group(0)}")

    parsed = parse_frontmatter(path, text)
    if parsed is None:
        return
    fields, _fm_count, body = parsed

    # --- name ---
    name_field = fields.get("name")
    if not name_field or (not name_field["raw"] and not name_field["block"]):
        err(path, "frontmatter `name` is required and non-empty")
    else:
        name, problems = split_scalar(name_field["raw"])
        for p in problems:
            err(path, f"name: {p}")
        if not NAME_RE.match(name):
            err(
                path,
                f"name {name!r} must be kebab-case: ^[a-z0-9]+(-[a-z0-9]+)*$ (no leading/trailing/double hyphens)",
            )
        if len(name) > MAX_NAME_LEN:
            err(path, f"name is {len(name)} chars (max {MAX_NAME_LEN})")
        for word in RESERVED_IN_NAME:
            if word in name:
                err(
                    path,
                    f"name contains {word!r} — rejected on Anthropic publishing surfaces; this repo avoids it by policy",
                )
        if path.parent.name != name:
            err(
                path,
                f"name {name!r} must equal its folder name {path.parent.name!r} — the folder name is what the runtime uses for discovery and /invocation",
            )

    # --- invocation mode: decides which description rules apply ---
    # A model-invoked skill is routed by its description, so the description is a
    # router API (trigger phrasings, negative triggers, enough surface to match).
    # A user-invoked one is reached by typing /name and is never routed, so those
    # rules are noise against it — it only has to read well in a slash menu.
    user_invoked = False
    dmi = fields.get("disable-model-invocation")
    if dmi and dmi["raw"]:
        value, _ = split_scalar(dmi["raw"])
        user_invoked = value.strip().lower() in ("true", "yes", "on")

    # --- description: the activation gate ---
    desc_field = fields.get("description")
    if not desc_field or (
        not desc_field["raw"] and not desc_field["block"] and not desc_field["continued"]
    ):
        err(
            path,
            "frontmatter `description` is required — it is the ONLY text the model sees when deciding to load this skill",
        )
    elif desc_field["block"]:
        err(
            path,
            "description uses a YAML block scalar (|, >) — this repo requires ONE physical line: multi-line descriptions have failed to load in some runtimes/versions and bloat the skill catalog",
        )
    elif desc_field["continued"]:
        err(
            path,
            "description continues on an indented next line — keep it on a single physical line",
        )
    else:
        desc, problems = split_scalar(desc_field["raw"])
        for p in problems:
            err(path, f"description: {p}")
        if not desc.strip():
            err(path, "description is empty/blank — the skill can never be routed to")
        elif (
            desc.strip().lower() in NON_STRING_VALUES
            or desc.lstrip().startswith(("[", "{", "&", "*"))
            or NUMERIC_DATE_RE.fullmatch(desc.strip())
        ):
            err(
                path,
                f"description {desc!r} is not a plain string — a YAML parser reads it as a non-string (null/bool/number/date/flow) value",
            )
        else:
            if len(desc) > MAX_DESC_LEN:
                err(path, f"description is {len(desc)} chars (max {MAX_DESC_LEN})")
            elif len(desc) > DESC_SWEET_MAX:
                warn(
                    path,
                    f"description is {len(desc)} chars — aim 150-{DESC_SWEET_MAX}; front-load triggers in the first ~120 chars",
                )
            low = desc.lower()
            if low.startswith(("i ", "i'll", "you ")):
                warn(
                    path,
                    "description should be third person ('Generates...', 'Use when...'), not first/second person",
                )
            if not user_invoked:
                if len(desc) < 60:
                    warn(
                        path,
                        f"description is only {len(desc)} chars — too thin to trigger reliably; state what it does + when to use it (aim 150-{DESC_SWEET_MAX})",
                    )
                if not any(
                    t in low
                    for t in (
                        "use when",
                        "use this",
                        "use for",
                        "use it when",
                        "trigger",
                        "when the user",
                    )
                ):
                    warn(
                        path,
                        'description has no explicit trigger clause — add "Use when the user ..." with realistic phrasings',
                    )
                if len(desc) >= 60 and not any(
                    t in low for t in ("not for", "does not apply", "not when")
                ):
                    warn(
                        path,
                        'consider a negative trigger ("Not for ...") if any sibling skill could swallow its prompts',
                    )

    # --- body ---
    if len(body) > MAX_BODY_LINES:
        warn(
            path,
            f"body is {len(body)} lines (> {MAX_BODY_LINES}) — Anthropic authoring guidance; move detail into references/ so it loads only when needed",
        )
    if not any(ln.strip() for ln in body):
        err(path, "skill body is empty")

    # --- security: the instructions and everything shipped alongside them ---
    scan_security(path, text)
    check_bundled_files(path.parent)

    # --- evals ---
    evals = path.parent / "evals" / "evals.json"
    if evals.is_file():
        check_evals(evals, distributed, user_invoked)
    elif distributed:
        err(
            path,
            "missing evals/evals.json — this repo is eval-first: write the eval cases BEFORE the skill body (see docs/evals.md)",
        )
    else:
        warn(
            path, "no evals/evals.json (allowed for repo-internal dev skills, required for skills/)"
        )


def scan_security(path: Path, text: str) -> None:
    """Flag the patterns registry scanners and audits treat as malicious."""
    for pattern, is_error, message in SECURITY_RULES:
        m = pattern.search(text)
        if not m:
            continue
        line = text.count("\n", 0, m.start()) + 1
        report = err if is_error else warn
        report(path, f"security (line {line}): {message}")


def check_bundled_files(skill_dir: Path) -> None:
    """Scan the scripts and assets a skill ships — they run on the user's machine."""
    for child in sorted(skill_dir.rglob("*")):
        if not child.is_file() or child.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        rel = child.relative_to(skill_dir).parts
        if len(rel) >= 2 and rel[:2] == NESTED_SCAFFOLD:
            continue
        try:
            scan_security(child, child.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable: nothing to scan, not a skill defect


def check_evals(path: Path, distributed: bool, user_invoked: bool = False) -> None:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        err(path, f"invalid JSON: {exc}")
        return
    for m in PLACEHOLDER_RE.finditer(raw):
        err(path, f"leftover template placeholder {m.group(0)}")
    cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(cases, list) or not cases:
        err(path, 'must be an object with a non-empty "cases" array')
        return
    counts = dict.fromkeys(EVAL_TYPES, 0)
    for i, case in enumerate(cases):
        where = f"cases[{i}]"
        if not isinstance(case, dict):
            err(path, f"{where} must be an object")
            continue
        if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
            err(path, f'{where} needs a non-empty string "prompt"')
        ctype = case.get("type")
        if ctype not in EVAL_TYPES:
            err(path, f'{where} "type" must be one of {sorted(EVAL_TYPES)}')
        else:
            counts[ctype] += 1
        if ctype == "quality":
            eb = case.get("expected_behavior")
            if (
                not isinstance(eb, list)
                or not eb
                or not all(isinstance(x, str) and x.strip() for x in eb)
            ):
                err(
                    path,
                    f'{where} quality cases need "expected_behavior": [3-5 plain-language assertions]',
                )
    report = err if distributed else warn
    # A user-invoked skill (`disable-model-invocation: true`) is reached by typing
    # /name — no router ever weighs its description, so trigger cases have nothing
    # to prove. Its quality cases still do: the body must work once invoked.
    if not user_invoked:
        if counts["should_trigger"] < MIN_SHOULD_TRIGGER:
            report(
                path,
                f"only {counts['should_trigger']} should_trigger cases (need ≥{MIN_SHOULD_TRIGGER}, varying formality/typos/terseness)",
            )
        if counts["should_not_trigger"] < MIN_SHOULD_NOT_TRIGGER:
            report(
                path,
                f"only {counts['should_not_trigger']} should_not_trigger cases (need ≥{MIN_SHOULD_NOT_TRIGGER} near-misses sharing keywords)",
            )
    if counts["quality"] < 1:
        report(path, "no quality cases (need ≥1, ideally 3-5, with expected_behavior assertions)")
    elif counts["quality"] < 3:
        warn(
            path,
            f"only {counts['quality']} quality case(s) — aim for 3-5 (1 canonical, variations, edge cases)",
        )


def check_manifest(path: Path, required: tuple[str, ...]) -> None:
    if not path.is_file():
        warn(path, "manifest missing (repo will not be installable as a plugin)")
        return
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        err(path, f"invalid JSON: {exc}")
        return
    if not isinstance(data, dict):
        err(path, f"manifest must be a JSON object, got {type(data).__name__}")
        return
    for key in required:
        if key not in data or not data[key]:
            err(path, f'missing required field "{key}"')
    for m in PLACEHOLDER_RE.finditer(raw):
        err(path, f"leftover template placeholder {m.group(0)}")


# --- README: the shape rules from docs/readme-standard.md --------------------
# A skills-repo README is a landing page whose conversion event is the install
# command. Only the mechanical half is checkable here; the rest is judgement and
# belongs to whoever writes it.
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)|<img[^>]+src=[\"']([^\"']+)")
INSTALL_RE = re.compile(r"npx\s+skills(?:@\S+)?\s+add\s+\S+")
# Requirement: examples show what a *user* types. A script that lives inside a
# skill is implementation detail — matched precisely so ordinary repo commands
# (`make check`, `scripts/validate_skills.py`) stay legal.
SKILL_SCRIPT_RE = re.compile(r"skills/[A-Za-z0-9_-]+/scripts/\S+|\$\{?CLAUDE_SKILL_DIR\}?")
STEP_RE = re.compile(r"^\s*\d+\.\s+(?:\*\*\[(?P<marker>[^\]]*)\]\*\*)?")
STEP_MARKERS = ("Required", "Optional", "Afterward")
SKILL_LINK_RE = re.compile(r"\]\(\s*(?:\./)?skills/([A-Za-z0-9_-]+)/?\s*\)")
# Proof, not decoration: a local recording or screenshot. Deliberately excludes
# .svg so a remote badge or an inline diagram cannot pass as a demo.
DEMO_HINT_RE = re.compile(r"\.(?:gif|mp4|webm|png|cast|tape)$", re.I)

SKILLS_SH_TOP_KEYS = {"$schema", "schema", "notGrouped", "groupings"}
SKILLS_SH_GROUP_KEYS = {"title", "description", "skills"}


def check_skills_sh(root: Path, distributed: list[str]) -> None:
    """Validate skills.sh.json against the skills.sh schema shape.

    The live schema (https://skills.sh/schemas/skills.sh.schema.json) uses
    additionalProperties:false and REQUIRES `groupings` — a file with legacy
    or guessed keys (`groups`, `name`) is silently ignored by skills.sh.
    """
    path = root / "skills.sh.json"
    if not path.is_file():
        warn(path, "missing — the skills.sh repo page cannot be customized without it")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        err(path, f"invalid JSON: {exc}")
        return
    if not isinstance(data, dict):
        err(path, f"must be a JSON object, got {type(data).__name__}")
        return
    for key in data:
        if key not in SKILLS_SH_TOP_KEYS:
            hint = ' — the schema key is "groupings" (not "groups")' if key == "groups" else ""
            err(
                path,
                f"unknown top-level key {key!r} (schema is additionalProperties:false; skills.sh ignores the file){hint}",
            )
    if data.get("notGrouped") not in (None, "top", "bottom"):
        err(path, f'notGrouped must be "top" or "bottom", got {data.get("notGrouped")!r}')
    groupings = data.get("groupings")
    if groupings is None:
        msg = 'missing "groupings" — REQUIRED by the skills.sh schema'
        if distributed:
            err(path, f"{msg}; add every skill under skills/ to exactly one grouping")
        else:
            warn(path, f"{msg}; add it when the first skill lands")
        return
    if not isinstance(groupings, list) or not 1 <= len(groupings) <= 50:
        err(
            path,
            f'"groupings" must be an array of 1-50 groups, got {type(groupings).__name__} of {len(groupings) if isinstance(groupings, list) else "?"}',
        )
        return
    seen: dict[str, int] = {}
    for i, g in enumerate(groupings):
        tag = f"groupings[{i}]"
        if not isinstance(g, dict):
            err(path, f"{tag}: must be an object")
            continue
        for key in g:
            if key not in SKILLS_SH_GROUP_KEYS:
                hint = ' — the schema key is "title" (not "name")' if key == "name" else ""
                err(path, f"{tag}: unknown key {key!r}{hint}")
        title = g.get("title")
        if not isinstance(title, str) or not 1 <= len(title) <= 120:
            err(path, f'{tag}: "title" is required (string, 1-120 chars)')
        desc = g.get("description")
        if desc is not None and (not isinstance(desc, str) or len(desc) > 500):
            err(path, f'{tag}: "description" must be a string of ≤500 chars')
        skills = g.get("skills")
        if (
            not isinstance(skills, list)
            or not 1 <= len(skills) <= 500
            or not all(isinstance(s, str) and s for s in skills)
        ):
            err(path, f'{tag}: "skills" is required (array of 1-500 skill-name strings)')
            continue
        for s in skills:
            seen[s] = seen.get(s, 0) + 1
            if distributed and s not in distributed:
                err(path, f"{tag}: references unknown skill {s!r} (not under skills/)")
    for s in distributed:
        if seen.get(s, 0) == 0:
            warn(
                path,
                f"skill {s!r} is in no grouping — repo convention is exactly one (notGrouped placement applies)",
            )
        elif seen[s] > 1:
            warn(path, f"skill {s!r} appears in {seen[s]} groupings — keep exactly one")


def split_fences(text: str) -> tuple[list[str], list[str]]:
    """Return (lines outside code fences, lines inside them)."""
    outside, inside, in_fence = [], [], False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        (inside if in_fence else outside).append(line)
    return outside, inside


def check_readme(root: Path, distributed: list[str]) -> None:
    """Validate README.md against docs/readme-standard.md (the checkable half)."""
    path = root / "README.md"
    if not path.is_file():
        warn(path, "missing — this is the landing page a skills.sh visitor lands on")
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        err(path, f"cannot read as UTF-8 text: {exc}")
        return
    # HTML comments are not rendered, so commented-out markup is neither a broken
    # image nor a stripped-by-skills.sh tag. The scaffold README carries its icon
    # snippet that way on purpose, as guidance rather than a dead reference.
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    outside, inside = split_fences(text)

    # --- icon first, and every referenced local image present ---
    images = [m.group(1) or m.group(2) for m in IMAGE_RE.finditer(text)]
    local = [src for src in images if not src.startswith(("http://", "https://", "data:"))]
    if not local:
        # A freshly scaffolded repo has no icon yet and that is fine; a repo that
        # ships skills without one is an unfinished landing page.
        report = err if distributed else warn
        report(path, "no local image — every repo opens with an icon (docs/readme-standard.md)")
    else:
        first = local[0]
        if "icon" not in first.lower():
            warn(path, f"first local image is {first!r} — the icon comes first, above the title")
        for src in local:
            target = (root / src.split("#")[0].split("?")[0]).resolve()
            if not target.is_file():
                err(
                    path,
                    f"references {src!r}, which does not exist — a broken image on the landing page",
                )

    # --- the conversion event ---
    if not INSTALL_RE.search(text):
        err(
            path,
            "no `npx skills add <owner>/<repo>` command — the install line is the point of the page",
        )

    # --- examples must be skills-level, never a skill's own internals ---
    for line in inside:
        m = SKILL_SCRIPT_RE.search(line)
        if m:
            err(
                path,
                f"code example invokes a skill's internals ({m.group(0)!r}) — show the "
                "install command, a /skill-name invocation, or the plain-English ask instead",
            )
            break

    # --- catalogue parity: the table IS the product ---
    linked = {m.group(1) for m in SKILL_LINK_RE.finditer(text)}
    for name in distributed:
        if name not in linked:
            err(path, f"skill {name!r} has no catalogue row linking `skills/{name}/`")
    for name in sorted(linked - set(distributed)):
        if distributed:  # an empty catalogue is a fresh scaffold, not a defect
            err(path, f"catalogue links `skills/{name}/`, which is not a skill in this repo")

    # --- step markers ---
    marked = unmarked = 0
    for line in outside:
        m = STEP_RE.match(line)
        if not m:
            continue
        marker = m.group("marker")
        if marker is None:
            unmarked += 1
        elif marker not in STEP_MARKERS:
            err(path, f"step marker {marker!r} is not one of {', '.join(STEP_MARKERS)}")
        else:
            marked += 1
    if marked and unmarked:
        warn(
            path,
            f"{marked} marked step(s) and {unmarked} unmarked — mark every step in a "
            "procedure so an unmarked one reads as a defect, not an ambiguity",
        )

    # --- markup that does not survive skills.sh ---
    for tag, why in (
        ("<details", "collapsed sections are stripped, so the content simply vanishes"),
        ("> [!", "GitHub alert syntax renders as a plain blockquote elsewhere"),
    ):
        if tag in text:
            warn(
                path,
                f"uses {tag!r} — {why}; plain headings, bold and lists render everywhere "
                "(docs/readme-standard.md)",
            )

    # --- proof ---
    if not any(
        DEMO_HINT_RE.search(src.split("#")[0].split("?")[0])
        for src in local
        if "icon" not in src.lower()
    ):
        warn(
            path,
            "no demo media — a GIF or cast is what converts a visitor (docs/readme-standard.md)",
        )


def exact_case_child(directory: Path, filename: str) -> bool:
    """True iff `filename` exists in `directory` with EXACT casing (APFS-safe)."""
    try:
        return filename in (p.name for p in directory.iterdir())
    except OSError:
        return False


def discover_and_check(root: Path) -> None:
    distributed_names: list[str] = []
    for base, distributed in ((root / "skills", True), (root / ".claude" / "skills", False)):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            if distributed and exact_case_child(child, "SKILL.md"):
                distributed_names.append(child.name)
            if exact_case_child(child, "SKILL.md"):
                check_skill_md(child / "SKILL.md", distributed)
            else:
                wrong = [p.name for p in child.iterdir() if p.name.lower() == "skill.md"]
                hint = (
                    f" (found {wrong[0]!r} — rename it; Linux/CI is case-sensitive)"
                    if wrong
                    else ""
                )
                err(child, f"skill folder has no SKILL.md (exact name, case-sensitive){hint}")
    check_manifest(root / ".claude-plugin" / "plugin.json", ("name", "description", "version"))
    check_manifest(root / ".claude-plugin" / "marketplace.json", ("name", "plugins"))
    check_skills_sh(root, distributed_names)
    check_readme(root, distributed_names)


def classify_distributed(f: Path, root: Path) -> bool:
    """A skill is 'distributed' when it lives under <root>/skills/ (not .claude/skills/)."""
    try:
        parts = f.resolve().relative_to(root.resolve()).parts
    except ValueError:
        parts = f.parts  # outside root: fall back to absolute-path heuristic
    return "skills" in parts and ".claude" not in parts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="repo root (default: cwd)")
    ap.add_argument("--file", type=Path, help="validate a single SKILL.md (hook mode)")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args()

    root = args.root.resolve()
    if args.file:
        f = args.file if args.file.is_absolute() else root / args.file
        if f.name.lower() == "skill.md" and f.name != "SKILL.md":
            print(
                f"ERROR {f}: skill files must be named exactly SKILL.md (case-sensitive on Linux/CI)",
                file=sys.stderr,
            )
            print("FAIL: 1 error(s), 0 warning(s)")
            return 1
        check_skill_md(f, classify_distributed(f, root))
    else:
        discover_and_check(root)

    for line in errors + warnings:
        print(line, file=sys.stderr)
    n_err = len(errors) + (len(warnings) if args.strict else 0)
    label = "FAIL" if n_err else "OK"
    print(f"{label}: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
