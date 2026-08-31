#!/usr/bin/env python3
"""Self-check for run_evals.py scoring. Run: python3 scripts/test_run_evals.py

Covers the parts that silently rot: stemming, tie-safe ranking, the collision
threshold, and the negative-outscores-positive rule. Plain asserts, no framework.
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_evals as R


def test_tokenize_drops_stopwords_and_stems() -> None:
    toks = R.tokenize("Use this when the user is scaffolding repositories")
    assert "use" not in toks and "the" not in toks, toks
    # 'scaffolding' -> 'scaffold' so it matches a description saying 'scaffolds'
    assert "scaffold" in toks, toks
    assert R.stem("triggers") == R.stem("trigger"), "plural must fold onto singular"
    # short words must survive: over-stemming 'adds' -> 'a' would wreck scoring
    assert R.stem("adds") == "adds", R.stem("adds")


def test_cosine_bounds() -> None:
    a = {"skill": 1.0, "eval": 1.0}
    assert math.isclose(R.cosine(a, a), 1.0, rel_tol=1e-9)  # sqrt round-trip, not exact
    assert R.cosine(a, {"unrelated": 1.0}) == 0.0
    assert R.cosine(a, {}) == 0.0


def test_rank_shares_the_best_rank_on_ties() -> None:
    # A tie for first is a real routing ambiguity: both must read as rank 1,
    # never silently broken alphabetically in the winner's favour.
    scores = {"a": 0.5, "b": 0.5, "c": 0.1}
    assert R.rank_of("a", scores) == 1 and R.rank_of("b", scores) == 1
    assert R.rank_of("c", scores) == 3
    assert R.rank_of("c", {"a": 0.9, "b": 0.5, "c": 0.1}) == 3


def test_collision_gate_fires_on_duplicate_descriptions() -> None:
    same = "Authors an agent skill from a research pack and validates it"
    skills = [
        {"name": n, "rel": n, "tokens": Counter(R.tokenize(same)), "evals": None}
        for n in ("alpha", "beta")
    ]
    R.errors.clear()
    R.warnings.clear()
    R.check_collisions(skills, R.build_idf(skills))
    assert R.errors, "identical descriptions must be an error, not a warning"
    assert "near-duplicates" in R.errors[0]

    skills[1]["tokens"] = Counter(R.tokenize("Renders vector icons as PNG sprites"))
    R.errors.clear()
    R.warnings.clear()
    R.check_collisions(skills, R.build_idf(skills))
    assert not R.errors and not R.warnings, R.errors + R.warnings


def test_repo_scores_clean() -> None:
    """The repo's own skills must pass — this is the gate `make check` runs."""
    root = Path(__file__).resolve().parent.parent
    R.errors.clear()
    R.warnings.clear()
    assert R.run(root, R.TOP_K, None, verbose=False) == 0, R.errors


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        R.errors.clear()
        R.warnings.clear()
        t()
        print(f"ok  {t.__name__}")
    print(f"OK: {len(tests)} passed")
