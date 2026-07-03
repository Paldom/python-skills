# Skills

Distributed skills live here — one folder per skill:

```
skills/<skill-name>/
├── SKILL.md          # required: frontmatter (name, description) + instructions
├── evals/
│   └── evals.json    # trigger + quality eval cases (written BEFORE the skill body)
├── scripts/          # optional: deterministic helpers (run via Bash, never enter context)
├── references/       # optional: long-form docs loaded on demand (one level deep only)
└── assets/           # optional: output templates
```

Authoring rules and the eval-first workflow: [docs/skill-authoring.md](../docs/skill-authoring.md).
The folder name must equal the frontmatter `name`, and it becomes the `/slash-command`.
