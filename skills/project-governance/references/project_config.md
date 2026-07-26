# Project Configuration

This skill consumes optional repository-owned configuration for
`defect-diagnosis`, `defect-history-review`, and `port-allocation` through the
configuration mechanism supplied by `skillcraft`. The mechanism belongs to
`skillcraft`; it is not a Project Governance domain or a Project-Skill
Governance capability.

```text
.agents/skills-config/project-governance/
├── config.yaml
└── <profile>.md
```

Schema `project-governance.config.v1` remains supported for defect-only
configuration. Use `project-governance.config.v2` when configuring project
ports. Configure only supported tasks. `base` is relative to the installed
`project-governance` skill root; `profile` is relative to the repository
configuration root.

```yaml
schema: project-governance.config.v2
profile: example-project
ports:
  project_segment: "42"
  instances:
    local_dev: 0
    local_e2e: 1
    local_preproduction: 2
    remote_preproduction: 5
    remote_production: 6
  services:
    allocation: sequential
    start: 0
    capacity: 100
    assignments:
      api: 0
      worker: 1
tasks:
  defect-diagnosis:
    base: references/defect-governance.md
    profile: project-defects.md
    commands:
      focused: pnpm test
  defect-history-review:
    base: references/defect-governance.md
    profile: project-defects.md
  port-allocation:
    base: references/port-allocation.md
```

Run the resolver adjacent to the installed skill and pass the target repository with `--cwd`. It composes generic instructions before project instructions, writes derived output below `.agents/.cache/project-governance/`, returns a stable `instructions_id`, and never executes declared commands.

The v2 resolver requires project segment `01` through `64`, the standard
instance mapping, and sequential unique service identifiers beginning at `0`.
It renders the derived port for every configured environment and service.

Project instructions may specialize terminology, authoritative sources,
history locations, commands, topology, and project-only policy. They cannot
override external authority, non-configurable safety rules, resolver
validation, or path containment. Do not store transient input, secrets,
generated output, or runtime state in project configuration.
