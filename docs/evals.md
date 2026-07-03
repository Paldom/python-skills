# Skill Evals

Skills are software: prompts are inputs, agent behavior is output, the description
is the routing layer. Test all three — **before** writing the skill body. If you
cannot write the eval cases, the scope isn't understood yet; that's a brief problem,
not a skill problem.

## evals.json format

`skills/<name>/evals/evals.json` (validated by `scripts/validate_skills.py`):

```json
{
  "skill": "example-skill",
  "cases": [
    { "type": "should_trigger", "prompt": "write tests for utils.py" },
    { "type": "should_trigger", "prompt": "can u add test coverage here" },
    { "type": "should_not_trigger", "prompt": "why is this test failing?" },
    { "type": "should_not_trigger", "prompt": "delete the flaky tests" },
    {
      "type": "quality",
      "prompt": "add tests for the parser module",
      "expected_behavior": [
        "creates a test file next to existing tests following repo conventions",
        "covers at least the happy path and one edge case per public function",
        "runs the new tests and reports the result"
      ]
    }
  ]
}
```

- **≥ 8 `should_trigger`**: vary formality, typos, terseness, explicitness — include
  at least two prompts that never name the skill.
- **≥ 8 `should_not_trigger`**: near-misses that share keywords but belong elsewhere
  (adjacent skills, native model competence). These catch over-triggering, which
  taxes every unrelated request.
- **3–5 `quality` cases**: 1 canonical, variations, 1–2 edge cases. Assertions are
  plain-language behavior checks, not exact output text.

## Running trigger evals

There is no fully automated harness here (activation is stochastic); the working
protocol:

1. **Fresh session per probe** — `claude` in a clean context; prior turns contaminate
   routing. Paste the case prompt verbatim.
2. Ask "Which skill did you use?" afterwards — simple tasks may be solved without
   consulting any skill, which is a routing miss that looks like a pass.
3. Score: aim **≥ 80% activation** on should-trigger, **≤ 5% false positives** on
   should-not. Run flaky cases 3× before concluding anything — single runs lie.
4. Fix order: **trigger failures → quality failures → edge cases.**
   - Under-triggering → broaden verbs/nouns, add terse phrasings, be pushier.
   - Over-triggering → add a "Not for …" exclusion built from the actual
     false-positive prompts' overlapping words (don't delete positive triggers).
   - Don't paste failed queries verbatim into the description (overfitting).
5. Re-run the suite after any description edit, when adding sibling skills (trigger
   theft), and after model upgrades.

## Quality evals

Run each quality case in a fresh session with the skill installed; check every
`expected_behavior` assertion. For subjective outputs, have a *different* session
(or model) grade against the assertions — self-evaluation is near random. Compare
against a no-skill baseline once: a skill whose output matches baseline is context
tax and should be deleted.
