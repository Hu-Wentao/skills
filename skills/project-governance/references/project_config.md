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
`document-audit`, `document-maintenance`, `release-deployment`, and
`port-allocation` through the configuration mechanism supplied by `skillcraft`.
The mechanism belongs to `skillcraft`; it is not a Project Governance domain
or a Project-Skill Governance capability.

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

Schemas `project-governance.config.v1` and `v2` remain supported as legacy
composed-instruction profiles. Use `project-governance.config.v3` for
executable task contracts. Configure only supported tasks. `base` is relative
to the installed skill root; `profile` and `contract` are relative to the
repository configuration root.

```yaml
schema: project-governance.config.v3
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
    contract: defect-feedback.contract.json
  defect-diagnosis:
    base: references/defect-governance.md
    profile: project-defects.md
    contract: defect-diagnosis.contract.json
  defect-history-review:
    base: references/defect-governance.md
    profile: project-defects.md
    contract: defect-history.contract.json
  document-maintenance:
    base: references/document-maintenance.md
    profile: project-documents.md
    contract: document-maintenance.contract.json
  release-deployment:
    base: references/release-deployment.md
    profile: project-release.md
    contract: release-deployment.contract.json
  port-allocation:
    base: references/port-allocation.md
    contract: port-allocation.contract.json
```

When `document-maintenance` is not configured, the skill supplies a managed
project-neutral contract with `inspect`, `plan`, `maintain`, and `verify`.
Project configuration is required only when the repository needs different
governed roots, status vocabularies, or deterministic document commands. The
legacy `document-audit` task may remain configured during migration.

Run the resolver adjacent to the installed skill and pass the target repository
with `--cwd`. For v3 it validates the selected JSON task contract, returns a
small resolved state with policy references, mutability, authorization,
parameter and output schemas, exit states, and an entry command without writing
project files or a runtime cache. It never executes project code. Pass
`--operation <name>` to return only the operation needed for the current stage.
The separate task runner executes only validated argv arrays. Legacy v1/v2
resolution retains its ignored instruction cache for compatibility.

Each v3 contract uses:

```json
{
  "schema": "project-governance.task-contract.v1",
  "id": "example.defect-diagnosis.v1",
  "task": "defect-diagnosis",
  "operations": {
    "collect": {
      "description": "Collect allowlisted evidence.",
      "command": ["pnpm", "ops:collect-evidence", "--"],
      "mutability": "read_only",
      "authorization": "none",
      "parameters": {},
      "output_schema": "example.evidence.v1",
      "exit_codes": {"0": "evidence_collected"},
      "next_states": ["semantic_classification"]
    }
  }
}
```

Commands must be argv arrays. The resolver verifies executables and direct
script or pnpm entry points when possible. Every write operation must declare
`current_user` authorization. The runner additionally requires `--authorized`;
that flag is a mechanical gate and never replaces the AI's current-turn
authorization judgment.

The v2/v3 resolver requires project segment `10` through `64`, reserves `01`
through `09` for system applications, requires the standard
instance mapping, and sequential unique service identifiers beginning at `0`.
It renders the derived port for every configured environment and service.

Before writing a new v2/v3 port configuration, run:

```bash
uv run --script <skill-root>/scripts/project-segments.py allocate --cwd <project-root>
```

For a project that already has v2/v3 port configuration, register its current segment
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
