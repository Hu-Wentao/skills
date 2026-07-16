# Project Configuration

This skill consumes optional repository-owned configuration for `defect-diagnosis` and `defect-history-review` through the configuration mechanism supplied by `skillcraft`. The mechanism belongs to `skillcraft`; it is not a Project Governance domain or a Project-Skill Governance capability.

```text
.agents/skills-config/project-governance/
├── config.yaml
└── <profile>.md
```

Use schema `project-governance.config.v1`. Configure only supported tasks. `base` is relative to the installed `project-governance` skill root; `profile` is relative to the repository configuration root.

```yaml
schema: project-governance.config.v1
profile: example-project
tasks:
  defect-diagnosis:
    base: references/defect-governance.md
    profile: project-defects.md
    commands:
      focused: pnpm test
  defect-history-review:
    base: references/defect-governance.md
    profile: project-defects.md
```

Run the resolver adjacent to the installed skill and pass the target repository with `--cwd`. It composes generic instructions before project instructions, writes derived output below `.agents/.cache/project-governance/`, returns a stable `instructions_id`, and never executes declared commands.

Project instructions may specialize terminology, authoritative sources, history locations, commands, topology, and project-only policy. They cannot override external authority, non-configurable safety rules, resolver validation, or path containment. Do not store transient input, secrets, generated output, or runtime state in project configuration.
