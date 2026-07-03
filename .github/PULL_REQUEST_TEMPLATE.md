## What

<!-- One or two sentences: what does this PR add or change, and why? -->

## Checklist

- [ ] `make check` passes locally (validator: frontmatter, evals, manifests)
- [ ] Skill `description` is a **single line**, third person, with trigger phrases and
      at least one "not for …" exclusion where a sibling skill could overlap
- [ ] Trigger evals updated (`skills/<name>/evals/evals.json`, ≥8 positive / ≥8 negative)
- [ ] Tested activation in a fresh Claude Code session (natural language, not just `/name`)
- [ ] README skill catalog and `CHANGELOG.md` updated
- [ ] No `.local/` working content (only its README is committed), secrets, or leftover template placeholder tokens
