# Project Configuration

The global skill works without repository configuration for read-only generic
reasoning. A repository may add reviewed task-specific instructions and a
deterministic task contract:

```text
.agents/skills-config/host-governance/
├── config.yaml
├── <profile>.md
└── <task>.contract.json
```

Minimum configuration:

```yaml
schema: host-governance.config.v2
profile: project-profile
tasks:
  control:
    base: references/control.md
    profile: project.md
    contract: control.contract.json
```

Run the installed global resolver from the consuming repository:

```bash
uv run python <skill-root>/scripts/resolve.py \
  --cwd . --task control --operation inspect --format json
```

The contract schema is `host-governance.task-contract.v1`. Each operation must
declare an argv-array command, mutability, authorization, parameters, optional
environment requirements, output schema, exit-code states, and allowed next
states. Write operations must require `current_user` authorization. Supported
mutability values are `read_only`, `repository_write`, `host_write`,
`external_write`, `composite_write`, and `destructive`. Use `composite_write`
only when one serialized controller changes both host and provider state.

```json
{
  "schema": "host-governance.task-contract.v1",
  "id": "example.host-control.v1",
  "task": "control",
  "operations": {
    "inspect": {
      "description": "Inspect authoritative and live host state.",
      "command": ["uv", "run", "python", "ops/host-control.py", "inspect"],
      "mutability": "read_only",
      "authorization": "none",
      "parameters": {},
      "output_schema": "example.host-control-event.v1",
      "exit_codes": {"0": "host_inspected", "1": "host_inspection_failed"},
      "next_states": ["host_plan"]
    }
  }
}
```

An operation may declare environment requirements without values:

```json
"environment": {
  "CLOUDFLARE_API_TOKEN": {
    "required": true,
    "sensitive": true
  }
}
```

Environment names must be uppercase shell identifiers. The runner checks only
whether required variables are non-empty and never writes their values to the
resolved contract, cache, argv, or output. Do not model credentials as operation
parameters.

When a project already owns a credential in an approved secret store, declare
an ordered `sources` list on the sensitive environment requirement instead of
asking an operator to copy it into a command or browser session:

```json
"environment": {
  "CLOUDFLARE_API_TOKEN": {
    "required": true,
    "sensitive": true,
    "sources": [
      {"kind": "environment", "name": "CLOUDFLARE_API_TOKEN"},
      {
        "kind": "macos_keychain",
        "service": "project-cloudflare-token",
        "account": "project-id"
      }
    ]
  }
}
```

The runner uses the first non-empty source, injects it only into the selected
operation's child environment, and never emits the value. Keychain service and
account names are non-secret project configuration; values stay in Keychain.
Do not declare shell commands, file reads, or other arbitrary credential
resolvers. An operation must still validate the credential with the target API
and distinguish invalid authentication from insufficient permission.

The project profile may declare:

- authoritative deployment manifest paths;
- stable service IDs and environment vocabulary;
- application-owned inspection and validation commands;
- project-specific rollback entry points;
- references to host infrastructure resource identities.

An authoritative host repository may additionally declare a `context` task
whose profile and contract expose bounded, read-only repository queries. Resolve
that task with `--cwd` set to the host repository. Keep its real repository
path, device identities, hostnames, addresses, aliases, ports, endpoints, and
topology in project-owned documents or skill configuration; never add those
facts to the globally shared skill. A consuming project should use the locator
workflow and query the authority at read time instead of defining its own
`context` inventory.

The authoritative host repository owns deterministic mutation behavior,
serialization, full-candidate validation, journal persistence, readback, and
recovery. A consuming profile may reference that controller but must not copy
its inventory or shared desired state.

Do not put copied device inventories, shared Caddy mappings, tailnet policy,
Cloudflare desired state, transient observations, or secrets in a consuming
project profile. Those remain in their primary authority systems. Project-owned
context output must distinguish repository declarations from live state and
include freshness/provenance when available.

`base` is relative to the installed skill root. `profile` and `contract` are
relative to the repository's configuration directory. Absolute paths and path
traversal are rejected. The resolver verifies direct executables and scripts
when possible but never executes them. The separate runner executes only a
selected validated operation and requires `--authorized` for writes.

Schema `host-governance.config.v1` remains readable for compatibility. It may
compose legacy instructions and declarative command strings, but it cannot be
used for contracted execution. Migrate a project to v2 before allowing it to
mutate shared host infrastructure.

Project instructions override generic configurable choices but cannot override
current user authority, system or developer rules, the safety invariants in
`SKILL.md`, schema validation, or path containment. Generated instructions
belong below `.agents/.cache/host-governance/` and should not be tracked.
