---
mdq:
  version: 1
  dialect: gfm
  records:
    boundary:
      source: heading
      levels: [1]
      pattern: '^Project Configuration$'
    key:
      source: marker
  fields:
    title:
      source: heading
    raw:
      source: body
  tolerance:
    incomplete: true
---
<!-- mdq:record id="GOV-PROJECT-CONFIGURATION" -->
# Project Configuration

This skill consumes optional repository-owned configuration for
`defect-feedback-lifecycle`, `defect-diagnosis`, `defect-history-review`,
`release-deployment`, and `port-allocation` through the configuration mechanism
supplied by `skillcraft`. The mechanism belongs to `skillcraft`; it is not a
Project Governance domain or a Project-Skill Governance capability.

```text
.agents/skills-config/project-governance/
├── config.yaml
└── <profile>.md
```

The repository configuration above is distinct from the machine-local segment
registry:

```text
~/.agents/skills-config/project-governance/project-segments.yaml
```

The repository owns its selected segment and service map. The machine-local
registry prevents two local projects from selecting the same segment and lets
a new project obtain the lowest free segment. Do not copy the global registry
into a repository or commit it.

Schema `project-governance.config.v1` remains supported for configured tasks
other than port allocation. Use `project-governance.config.v2` when configuring
project ports. Configure only supported tasks. `base` is relative to the
installed `project-governance` skill root; `profile` is relative to the
repository configuration root.

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
  defect-feedback-lifecycle:
    base: references/defect-feedback-lifecycle.md
    profile: project-feedback.md
  defect-diagnosis:
    base: references/defect-governance.md
    profile: project-defects.md
    commands:
      focused: pnpm test
  defect-history-review:
    base: references/defect-governance.md
    profile: project-defects.md
  release-deployment:
    base: references/release-deployment.md
    profile: project-release.md
  port-allocation:
    base: references/port-allocation.md
```

Run the resolver adjacent to the installed skill and pass the target repository with `--cwd`. It composes generic instructions before project instructions, writes derived output below `.agents/.cache/project-governance/`, returns a stable `instructions_id`, and never executes declared commands.

The v2 resolver requires project segment `10` through `64`, reserves `01`
through `09` for system applications, requires the standard
instance mapping, and sequential unique service identifiers beginning at `0`.
It renders the derived port for every configured environment and service.

Before writing a new v2 configuration, run:

```bash
uv run --script <skill-root>/scripts/project-segments.py allocate --cwd <project-root>
```

For a project that already has v2 configuration, register its current segment
with `claim --segment <PP>`; use `check --segment <PP>` for read-only
validation. Allocation and claim use an exclusive lock and atomic replacement.
They are idempotent for the same canonical Git root and segment, reject
cross-project conflicts, and never renumber another project. The registry
schema is `project-governance.project-segments.v1` and its allocation keys are
canonical absolute Git roots.

Project instructions may specialize terminology, authoritative sources,
history locations, commands, topology, and project-only policy. They cannot
override external authority, non-configurable safety rules, resolver
validation, or path containment. Do not store transient input, secrets,
generated output, or runtime state in project configuration.
