# Legacy Project Extraction

Use this reference only when a new project should be informed by an existing or old project.

## Contents

- Extraction Goals
- Reading Order
- Decision Classification
- Output Shape
- Safety Checks

## Extraction Goals

- Extract product intent, domain terms, workflows, module responsibilities, data ownership, runtime assumptions, and operational constraints.
- Separate useful requirements from incidental implementation details.
- Preserve user-confirmed behavior, not accidental coupling.
- Identify what the new project should inherit, replace, simplify, or intentionally drop.

## Reading Order

1. Read README, docs, architecture notes, and runbooks.
2. Inspect package manifests, workspace config, Docker/compose files, scripts, CI, and environment examples.
3. Map top-level apps/packages/modules and their runtime entrypoints.
4. Trace persistence ownership, external APIs, queues/jobs, auth, config, and deployment surfaces.
5. Read representative code paths only after the module map is clear.

Prefer `rg` and file manifests before opening large files. Do not rewrite the old project's behavior as a transcript.

## Decision Classification

Classify each extracted point as one of:

- `inherit`: keep the behavior or constraint in the new project.
- `replace`: solve the same need with a different design.
- `drop`: intentionally omit because it is obsolete, accidental, or out of scope.
- `review`: user confirmation needed before deciding.

Use review levels from `design-doc-rules.md` when converting extracted decisions into new project docs.

## Output Shape

When extraction is part of a bootstrap task, produce a short extraction summary before writing new docs:

```text
Inherited constraints
Replaced design choices
Dropped legacy behavior
Open review questions
New project implications
```

Then create or update the normal design docs and `implementation-prompt.md`.

## Safety Checks

- Do not copy secrets, credentials, private endpoints, or production data into the new project.
- Do not preserve old compatibility behavior unless the user confirms it matters.
- Do not assume old scripts, ports, databases, or package managers are correct for the new project.
- Search for stale legacy names before finishing.
