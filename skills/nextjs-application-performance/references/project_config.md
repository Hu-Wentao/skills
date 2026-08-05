# Project Configuration

This skill supports optional repository-owned configuration so the same skill
can behave differently in different projects:

```text
.agents/skills-config/nextjs-application-performance/
├── config.yaml
├── <profile>.md
└── <project-owned manifests>.json
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

Repository-specific inventories and selectors belong in project-owned
manifests, not in the reusable skill. For overlay boundaries, use schema
`nextjs-overlay-contracts.v1` and declare each shared owner, focused test,
required source evidence, forbidden consumer CSS selectors, and browser
geometry selectors/viewports. The generic audit and probe scripts consume this
manifest; they do not embed project component names or route selectors.

For pnpm workspace and production build boundaries, use schema
`nextjs-build-contracts.v1`. Declare each Next app, its package and config
paths, the `server`/`client`/`hybrid` classification and public entrypoints of
every direct workspace dependency, the exact allowed external packages, the
standalone directory, the container memory gate, cold-output path, and runtime
smoke routes. Keep measured exceptions for heap increases,
`resolve.symlinks=false`, or `optimizePackageImports` in the manifest with a
repository evidence file and required marker. The generic scripts reject
unclassified workspace dependencies, whole-package hybrid externalization,
cross-boundary root barrels, source-workspace resolution from standalone
output, non-cold builds, unbounded cgroups, and unevidenced exceptions.
