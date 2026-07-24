# Project Configuration

This skill supports optional repository-owned configuration so the same skill
can behave differently in different projects:

```text
.agents/skills-config/nextjs-application-performance/
├── config.yaml
└── <profile>.md
```

Example:

```yaml
schema: nextjs-application-performance.config.v1
profile: example-project
tasks:
  review:
    base: references/review.md
    profile: project.md
    commands:
      validate: <project validation command>
```

Run the resolver before a configured task:

```bash
uv run python .agents/skills/nextjs-application-performance/scripts/resolve.py --task review
```

Read the returned instruction path once per new `instructions_id`. Resolution
does not execute declared commands. The target repository owns `skills-config`;
resolved output belongs under `.agents/.cache/nextjs-application-performance/` and should not be
tracked.

Project instructions override generic configurable defaults when both address
the same choice. They cannot override external authority, non-configurable
safety invariants, schema validation, or path-containment rules.
