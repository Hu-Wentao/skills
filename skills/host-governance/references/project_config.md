# Project Configuration

The global skill works without repository configuration. A consuming project
may add reviewed deployment-specific instructions and declarative commands:

```text
.agents/skills-config/host-governance/
├── config.yaml
└── <profile>.md
```

Minimum configuration:

```yaml
schema: host-governance.config.v1
profile: project-profile
tasks:
  control:
    base: references/control.md
    profile: project.md
    commands:
      inspect: <read-only project inspection command>
      validate: <project-owned validation command>
```

Run the installed global resolver from the consuming repository:

```bash
uv run python <skill-root>/scripts/resolve.py --cwd . --task control
```

The project profile may declare:

- authoritative deployment manifest paths;
- stable service IDs and environment vocabulary;
- application-owned inspection and validation commands;
- project-specific rollback entry points;
- references to host infrastructure resource identities.

Do not put device inventories, shared Caddy mappings, tailnet policy, Cloudflare
desired state, transient observations, or secrets in a consuming project
profile. Those remain in their primary authority systems.

`base` is relative to the installed skill root. `profile` is relative to the
repository's configuration directory. Absolute paths and path traversal are
rejected. Commands are returned as declarations and never run by resolution.

Project instructions override generic configurable choices but cannot override
current user authority, system or developer rules, the safety invariants in
`SKILL.md`, schema validation, or path containment. Generated instructions
belong below `.agents/.cache/host-governance/` and should not be tracked.
