#!/usr/bin/env python3
"""Deterministic trigger-eval runner for Agent Skills repositories.

`validate_skills.py` checks that `evals.json` is well-formed. This script
*executes* the trigger cases: it scores every eval prompt against every skill
description in the repo and fails when a skill's own prompts do not route to it.

It is a lexical proxy for the model's router, not the router itself: TF-IDF
cosine over `name` + `description`, stdlib only, no model call, no network. It
therefore catches the failure modes that are actually mechanical — a description
whose vocabulary never overlaps the prompts users type, and two skills whose
descriptions have drifted into each other — and it cannot tell you whether the
model would truly pick the skill. Passing here is necessary, not sufficient;
the `quality` cases still need a real agent (see docs/evals.md).

Checks:
  1. should_trigger      — the skill ranks in the top K (default 3) for its own
                           prompt, and scores above zero.
  2. should_not_trigger  — no non-trigger prompt outscores EVERY trigger prompt.
  3. routing collisions  — no two descriptions are near-duplicates.
  4. rank-1 ratchet      — `--min-rank1 PCT` fails when the share of
                           should_trigger prompts that rank #1 drops below PCT.

Check 2 is deliberately weak, and the reason is worth knowing. This repo requires
`should_not_trigger` cases to be *near-misses that share keywords* — so they are
built to be lexically close and semantically distant, which is precisely the
distinction TF-IDF cannot draw. Demanding that negatives simply score low would
fail every well-written eval file. What a lexical scorer can say without lying is
narrower: if a prompt you declared a non-trigger is a better match for the
description than any prompt you declared a trigger, the description is aimed at
the wrong thing. That is the check. Fine-grained negative routing needs a real
router, not this script.

Usage:
    python3 scripts/run_evals.py                      # score repo (cwd = root)
    python3 scripts/run_evals.py --root P
    python3 scripts/run_evals.py --min-rank1 75       # ratchet
    python3 scripts/run_evals.py --verbose            # print every ranking

Exit codes: 0 = OK (warnings allowed), 1 = failures.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

TOP_K = 3
COLLISION_WARN = 0.50
COLLISION_ERROR = 0.75

# Ranking needs something to rank against; below this the repo is scored for
# vocabulary overlap only (see run()).
MIN_SKILLS_FOR_RANKING = 2

TOKEN_RE = re.compile(r"[a-z0-9]+")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
# The repo requires description on ONE physical line (validate_skills.py), so a
# line-anchored match is exact here rather than a lenient guess.
FIELD_RE = {
    "name": re.compile(r"^name:[ \t]*(.+?)[ \t]*$", re.M),
    "description": re.compile(r"^description:[ \t]*(.+?)[ \t]*$", re.M),
}
USER_INVOKED_RE = re.compile(r"^disable-model-invocation:[ \t]*(true|yes|on)[ \t]*$", re.M | re.I)

STOP = {
    "a",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "before",
    "but",
    "by",
    "can",
    "do",
    "does",
    "for",
    "from",
    "get",
    "has",
    "have",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "me",
    "my",
    "need",
    "needs",
    "not",
    "of",
    "on",
    "or",
    "our",
    "out",
    "so",
    "that",
    "the",
    "them",
    "then",
    "there",
    "this",
    "to",
    "up",
    "use",
    "used",
    "user",
    "users",
    "want",
    "wants",
    "was",
    "we",
    "what",
    "when",
    "where",
    "which",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
}

errors: list[str] = []
warnings: list[str] = []


def err(where: str, msg: str) -> None:
    errors.append(f"ERROR {where}: {msg}")


def warn(where: str, msg: str) -> None:
    warnings.append(f"WARN  {where}: {msg}")


def stem(tok: str) -> str:
    """Light suffix stripping so 'triggers'/'trigger' and 'scaffolding'/'scaffold' match."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(tok) > len(suffix) + 3 and tok.endswith(suffix):
            return tok[: -len(suffix)]
    return tok


def tokenize(text: str) -> list[str]:
    return [s for t in TOKEN_RE.findall(text.lower()) if t not in STOP and (s := stem(t))]


def read_skill(skill_md: Path) -> dict | None:
    """Return {name, description, user_invoked} from a SKILL.md, or None if unreadable.

    Shape errors are validate_skills.py's job; here a malformed file is simply
    skipped so the two gates report their own failures without duplicating.
    """
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    fm = m.group(1)
    got = {}
    for key, pattern in FIELD_RE.items():
        found = pattern.search(fm)
        if not found:
            return None
        got[key] = found.group(1).strip().strip("\"'")
    got["user_invoked"] = bool(USER_INVOKED_RE.search(fm))
    return got


def discover(root: Path) -> tuple[list[dict], list[str]]:
    """Return (routable skills, names of skills excluded as user-invoked).

    Distributed and repo-internal skills both count: a repo-internal dev skill
    still competes for the same prompts at runtime, so it belongs in the corpus.
    User-invoked skills do not — nothing routes them, so including them would
    invent competition the router never sees.
    """
    skills: list[dict] = []
    user_invoked: list[str] = []
    for base in (root / "skills", root / ".claude" / "skills"):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            skill_md = child / "SKILL.md"
            if not (child.is_dir() and skill_md.is_file()):
                continue
            parsed = read_skill(skill_md)
            if parsed is None:
                continue
            if parsed["user_invoked"]:
                user_invoked.append(parsed["name"])
                continue
            evals_path = child / "evals" / "evals.json"
            skills.append(
                {
                    "name": parsed["name"],
                    "path": child,
                    "rel": str(child.relative_to(root)),
                    # The router sees name + description; score exactly that.
                    "tokens": Counter(
                        tokenize(f"{parsed['name'].replace('-', ' ')} {parsed['description']}")
                    ),
                    "evals": evals_path if evals_path.is_file() else None,
                }
            )
    return skills, user_invoked


def build_idf(skills: list[dict]) -> dict[str, float]:
    n = len(skills)
    df: Counter[str] = Counter()
    for s in skills:
        df.update(s["tokens"].keys())
    return {t: math.log((n + 1) / (d + 1)) + 1.0 for t, d in df.items()}


def vector(tokens: Counter, idf: dict[str, float]) -> dict[str, float]:
    return {t: c * idf[t] for t, c in tokens.items() if t in idf}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    small, large = (a, b) if len(a) < len(b) else (b, a)
    dot = sum(w * large.get(t, 0.0) for t, w in small.items())
    if dot == 0.0:
        return 0.0
    na = math.sqrt(sum(w * w for w in a.values()))
    nb = math.sqrt(sum(w * w for w in b.values()))
    return dot / (na * nb)


def rank_of(target: str, scores: dict[str, float]) -> int:
    """1-based rank, ties sharing the best rank (no alphabetical tie-breaking).

    Ties must not silently promote a skill past a rival it merely drew with:
    a shared rank 1 is a genuine routing ambiguity and should be visible.
    """
    own = scores[target]
    return 1 + sum(1 for name, sc in scores.items() if name != target and sc > own)


def load_cases(skill: dict) -> list[dict]:
    if skill["evals"] is None:
        return []
    try:
        data = json.loads(skill["evals"].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []  # validate_skills.py reports malformed eval files
    cases = data.get("cases") if isinstance(data, dict) else None
    return [c for c in cases if isinstance(c, dict)] if isinstance(cases, list) else []


def check_collisions(skills: list[dict], idf: dict[str, float]) -> None:
    vectors = {s["name"]: vector(s["tokens"], idf) for s in skills}
    names = sorted(vectors)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            sim = cosine(vectors[a], vectors[b])
            if sim >= COLLISION_ERROR:
                err(
                    "routing",
                    f"descriptions of {a!r} and {b!r} are near-duplicates "
                    f"(similarity {sim:.2f} ≥ {COLLISION_ERROR}) — they will swallow "
                    "each other's prompts; split the scopes or merge the skills",
                )
            elif sim >= COLLISION_WARN:
                warn(
                    "routing",
                    f"descriptions of {a!r} and {b!r} overlap (similarity {sim:.2f}) — "
                    "sharpen the triggers or add a negative trigger to each",
                )


def run(root: Path, top_k: int, min_rank1: float | None, verbose: bool) -> int:
    skills, user_invoked = discover(root)
    if user_invoked:
        print(
            f"skipped {len(user_invoked)} user-invoked skill(s), never routed: {', '.join(sorted(user_invoked))}"
        )
    if not skills:
        print("no routable skills found — nothing to score")
        return 0

    idf = build_idf(skills)
    vectors = {s["name"]: vector(s["tokens"], idf) for s in skills}
    rankable = len(skills) >= MIN_SKILLS_FOR_RANKING
    if not rankable:
        print(
            f"note: only {len(skills)} skill in the repo — scoring vocabulary overlap "
            "only; ranking checks need something to rank against"
        )
    else:
        check_collisions(skills, idf)

    rank1 = 0
    triggered_total = 0
    for skill in skills:
        name = skill["name"]
        best_positive = (0.0, "")
        best_negative = (0.0, "")
        for case in load_cases(skill):
            ctype = case.get("type")
            prompt = case.get("prompt")
            if ctype not in ("should_trigger", "should_not_trigger") or not isinstance(prompt, str):
                continue  # quality cases need a real agent; shape errors belong to the validator
            q = vector(Counter(tokenize(prompt)), idf)
            scores = {s["name"]: cosine(q, vectors[s["name"]]) for s in skills}
            own = scores[name]
            rank = rank_of(name, scores)
            if verbose:
                order = ", ".join(
                    f"{n}={scores[n]:.2f}" for n in sorted(scores, key=lambda n: -scores[n])[:top_k]
                )
                print(
                    f"  {ctype:18} {name:26} rank {rank} own={own:.2f} | {prompt[:52]!r} | {order}"
                )

            if ctype == "should_trigger":
                triggered_total += 1
                best_positive = max(best_positive, (own, prompt))
                if own <= 0.0:
                    err(
                        skill["rel"],
                        f"should_trigger prompt shares no vocabulary with the description: "
                        f"{prompt!r} — the router has nothing to match on",
                    )
                elif not rankable:
                    continue
                elif rank > top_k:
                    winner = max(scores, key=lambda n: scores[n])
                    err(
                        skill["rel"],
                        f"should_trigger prompt ranks {name!r} at {rank} (need ≤{top_k}): "
                        f"{prompt!r} — {winner!r} outranks it",
                    )
                elif rank == 1:
                    rank1 += 1
            else:
                best_negative = max(best_negative, (own, prompt))

        if best_positive[1] and best_negative[0] > best_positive[0]:
            err(
                skill["rel"],
                f"a should_not_trigger prompt matches the description better than every "
                f"should_trigger one: {best_negative[1]!r} ({best_negative[0]:.2f}) beats "
                f"{best_positive[1]!r} ({best_positive[0]:.2f}) — the description is aimed "
                "at the wrong thing",
            )

    pct = (rank1 / triggered_total * 100.0) if triggered_total else 0.0
    if rankable and triggered_total:
        print(f"rank-1 accuracy: {rank1}/{triggered_total} ({pct:.1f}%) of should_trigger prompts")
        if min_rank1 is not None and pct < min_rank1:
            err(
                "ratchet",
                f"rank-1 accuracy {pct:.1f}% is below the checked-in floor of {min_rank1:.1f}%",
            )

    for line in errors + warnings:
        print(line, file=sys.stderr)
    label = "FAIL" if errors else "OK"
    print(f"{label}: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="repo root (default: cwd)")
    ap.add_argument(
        "--top-k",
        type=int,
        default=TOP_K,
        help=f"required rank for should_trigger (default {TOP_K})",
    )
    ap.add_argument(
        "--min-rank1", type=float, help="fail below this rank-1 percentage (the ratchet)"
    )
    ap.add_argument("--verbose", action="store_true", help="print the ranking for every case")
    args = ap.parse_args()
    return run(args.root.resolve(), args.top_k, args.min_rank1, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
