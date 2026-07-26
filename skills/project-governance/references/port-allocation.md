# Project Port Allocation

Use one host-visible port namespace for every governed project.

## Format

Represent every assigned port as `PPISS`:

- `PP`: two-digit project segment from `10` through `64`;
- `I`: one-digit instance identifier;
- `SS`: two-digit service identifier from `00` through `99`.

Calculate the port as `PP * 1000 + I * 100 + SS`. Reserve `01` through `09`
for system applications. Restrict ordinary project segments to `10` through
`64` so instance `6` retains all 100 service ports without exceeding port
`65535`.

## Machine-Local Project Segments

Use
`~/.agents/skills-config/project-governance/project-segments.yaml` as the
machine-local registry of canonical Git roots and their segments. Before
creating port configuration for a new project, run:

```bash
uv run --script <skill-root>/scripts/project-segments.py allocate --cwd <project-root>
```

The allocator returns an existing segment for a known project or reserves the
lowest free segment for a new project. For a project that already has a
configured segment, use `claim --segment <PP>` to add the same mapping or detect
a conflict. Use `check --segment <PP>` during read-only review. Do not edit the
registry concurrently by hand, copy it into a repository, infer that a missing
directory frees its segment, or silently renumber either project after a
conflict.

## Instance Allocation

Use these instance identifiers:

| Environment | `I` |
| --- | ---: |
| local development | `0` |
| local E2E, including Docker-based E2E | `1` |
| local preproduction | `2` |
| remote preproduction | `5` |
| remote production | `6` |

Do not assign a different meaning to these identifiers in project
configuration.

## Service Allocation

Assign service identifiers sequentially from `00`. A project has 100 service
ports per instance. Require unique assignments with no gaps between `00` and
the highest assigned service identifier.

Keep the project segment, the complete instance mapping, and the service
assignment map in
`.agents/skills-config/project-governance/config.yaml`. Treat that file as the
project-owned machine-readable source for derived ports, require it to agree
with the machine-local registry, and keep the operations document as the
human-readable authority.

## Migration and Review

When a project already uses another port scheme:

1. Resolve and validate the configured allocation.
2. Derive every environment-specific port from the same service identifiers.
3. Update listeners, clients, health checks, Compose mappings, deployment
   environment files, firewalls, tests, examples, and operations documentation.
4. Render Compose configurations for each affected environment.
5. Search the repository for stale ports and distinguish intentional historical
   references from active configuration.
6. Report the migration as breaking and state the required compatibility or
   operator action.

Do not infer that container isolation permits conflicting host-published
ports. Container-private target ports may differ only when the project
documents the translation and all host-visible ports still follow `PPISS`.
