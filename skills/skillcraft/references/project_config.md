# Project Configuration

## Contents

- Purpose
- Layout
- Ownership Boundary
- Configuration Contract
- Resolver Contract
- Required Tests
- Migration

## Purpose

Use project configuration when one reusable skill must exhibit different
behavior in different repositories without absorbing project-named branches.
The reusable skill owns the workflow and resolver contract. Each target
repository owns the profile that specializes its behavior.

## Layout

```text
.agents/
├── skills/<skill-name>/
│   ├── SKILL.md
│   ├── references/<task>.md
│   └── scripts/resolve.py
├── skills-config/<skill-name>/
│   ├── config.yaml
│   └── <profile>.md
└── .cache/<skill-name>/
    └── <resolved-instructions>.md
```

Track `skills` and `skills-config`. Do not track `.agents/.cache`.

## Ownership Boundary

Keep these in the reusable skill:

- universal workflow and safety rules;
- task selection and generic fallback;
- configuration schema and resolver;
- deterministic scripts and resolver tests;
- generic references that work without a project profile.

Keep these in the target repository's `skills-config`:

- project terminology and authoritative document paths;
- project-only commands, topology, environments, and package conventions;
- repository-specific policy and validation entry points;
- profile instructions reviewed with the project.

Do not put transient user input, secrets, generated output, or runtime state in
`skills-config`.

## Configuration Contract

Use a skill-specific versioned schema:

```yaml
schema: example-skill.config.v1
profile: example-project
tasks:
  default:
    base: references/default.md
    profile: project.md
    commands:
      validate: pnpm test
```

`base` is relative to `.agents/skills/<skill-name>/`. `profile` is relative to
`.agents/skills-config/<skill-name>/`. Reject absolute paths and paths escaping
their respective roots.

Commands are declarative output. Resolving configuration must never execute
them. `SKILL.md` decides when an emitted command is appropriate and user
authorization still controls external or destructive actions.

Project instructions override generic configurable defaults when both address
the same choice. They cannot override system, developer, or user authority;
non-configurable safety invariants explicitly owned by the reusable skill;
schema validation; or path-containment rules. Mark an invariant as
non-configurable only when every consuming project must preserve it.

## Resolver Contract

Before a config-aware task, run:

```bash
uv run python .agents/skills/<skill-name>/scripts/resolve.py --task <task>
```

The resolver must:

1. Find the nearest Git repository root.
2. Load the generic task reference.
3. Optionally load `skills-config/<skill-name>/config.yaml` and its profile.
4. Validate the exact schema and task mapping.
5. Reject path traversal and missing required files.
6. Compose generic instructions before project instructions.
7. Hash all effective inputs into a stable `instructions_id`.
8. Write resolved instructions below `.agents/.cache/<skill-name>/`.
9. Return a small manifest and never execute configured commands.
10. Make the active precedence policy explicit in the resolved instructions.

Without project configuration, resolve the generic reference with profile
`generic`. Do not require every consuming repository to create an empty
configuration directory.

## Required Tests

Test generic fallback, profile composition, stable ids, schema rejection,
missing task behavior, and path-containment rejection. Also install the exact
same skill in two temporary repositories with different profiles and prove that
their resolved instructions, declared commands, profile names, and
`instructions_id` values differ. Add task-specific tests when configuration
changes validation commands or safety boundaries.

## Migration

When extracting project branches from an existing reusable skill:

1. Identify every project-named condition and project-owned fact.
2. Move facts and profile prose to `skills-config`.
3. Replace code branches with generic task inputs where possible.
4. Preserve a working generic fallback.
5. Compare resolved behavior before removing the old branch.
6. Document breaking schema or task-name changes explicitly.
