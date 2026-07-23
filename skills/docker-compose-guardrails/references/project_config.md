# Project Configuration

This skill supports optional repository-owned deployment policy:

```text
.agents/skills-config/docker-compose-guardrails/
├── config.yaml
└── <profile>.md
```

Example:

```yaml
schema: docker-compose-guardrails.config.v1
profile: example-host
tasks:
  deploy:
    base: references/deploy.md
    profile: host-policy.md
    commands:
      preflight: <read-only admission check>
      verify: <post-start effective cgroup check>
```

The profile should declare service-to-class mapping, host reserve, critical
memory minima, maximum commitments, CPU isolation requirements, builder
placement and pressure thresholds. Keep credentials, transient measurements,
generated output, and secrets out of configuration.

Run the resolver before resource review, change, or deployment:

```sh
uv run python .agents/skills/docker-compose-guardrails/scripts/resolve.py --task deploy
```

Read the returned instruction path once per new `instructions_id`. Resolution
does not execute declared commands. The target repository owns
`skills-config`; resolved output belongs under
`.agents/.cache/docker-compose-guardrails/` and should not be tracked.

Project instructions override generic configurable defaults when both address
the same choice. They cannot override external authority, schema or
path-containment validation, or these universal safety invariants:

- every long-running container has finite memory, CPU, and PID limits;
- protected minima are enforced and verified on the host, not inferred from
  Compose reservations;
- admitted protected minima plus host reserve fit within physical capacity;
- builders are bounded as a complete execution tree and never consume protected
  critical capacity.
