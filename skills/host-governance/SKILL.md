---
name: host-governance
description: Query and govern shared host infrastructure across projects. Use when an agent needs repository-declared device IDs, hostnames, SSH aliases, Tailscale names or addresses, ports, service endpoints, topology or ownership, or when a project deployment needs inspection, planning, writes, verification, and rollback owned by the authoritative host infrastructure repository.
---

# Host Governance

Use one control workflow for infrastructure shared by multiple projects. Keep
application deployment ownership in the consuming project and shared network,
ingress, DNS, and host ownership in the host infrastructure repository.

## Query Shared Context

When another project needs shared host facts, locate the authoritative host
repository instead of copying an inventory into the consuming project or this
skill. Use the first unambiguous source in this order:

1. an exact repository path supplied by the current user;
2. a repository already established as authoritative in the current task;
3. the `HOST_INFRA_ROOT` environment variable;
4. the runtime locator documented in [context.md](references/context.md).

Resolve the `context` task against the authoritative host repository, not the
consuming repository. Read every returned policy reference before execution:

```bash
uv run python <skill-root>/scripts/resolve.py \
  --cwd <host-root> --task context --operation <operation> --format json
uv run python <skill-root>/scripts/host-governance.py \
  --cwd <host-root> execute --task context --operation <operation> \
  [contracted arguments]
```

Use `catalog` when identities are unknown, `search` to get candidate metadata,
and `get` with one exact kind and ID to retrieve authoritative content. Use
`current-device` only when the project contract provides it; stop rather than
guess when no device or multiple devices match.

Context results are repository declarations with their stated provenance and
freshness. They are not live observations. Do not fetch or pull implicitly,
probe networks, call provider APIs, or convert repository-declared values into
runtime claims. Do not persist a derived inventory or return secret-bearing
fields. Resolve `control` separately for live inspection or mutation.

## Resolve Project Behavior

Before inspecting or changing infrastructure, resolve the `control` task from
the consuming Git repository. Prefer the JSON operation contract when the
repository uses `host-governance.config.v2`:

```bash
uv run python <skill-root>/scripts/resolve.py \
  --cwd <project-root> --task control --operation <operation> --format json
```

Execute a configured operation only through the validated runner:

```bash
uv run python <skill-root>/scripts/host-governance.py \
  --cwd <project-root> control <operation> [contracted arguments]
```

Use `--authorized` only after the current user authorizes a non-read-only
operation. The flag is a mechanical gate, not proof of authorization. Never
bypass a v2 contract with its underlying command. The resolver validates argv,
mutability, authorization, parameters, output schema, exit states, and allowed
next states without executing project code.

Legacy `host-governance.config.v1` profiles and the generic fallback remain
readable composed instructions. Read the returned `instructions.path` whenever
`instructions_id` changes, but do not execute legacy declared command strings
as a substitute for a v2 contract. Without a configured transaction contract,
leave shared host infrastructure unchanged.

Read [project_config.md](references/project_config.md) before creating or
changing a project profile.

## Establish Authority

1. Identify the consuming project and its deployment intent.
2. Locate the host infrastructure repository using an explicit user path,
   `HOST_INFRA_ROOT`, or the runtime locator described in the resolved
   instructions. Do not guess a path or copy infrastructure facts locally.
3. Read the infrastructure repository's root scope, module boundaries, storage
   rules, operations policy, and target device or provider resource.
4. Inspect the current live state of every affected system before proposing a
   write. Repository intent and live state are separate evidence.
5. Classify each requested change by owner and executor. A consuming project
   may request infrastructure but does not acquire authority to rewrite shared
   configuration.

## Preserve Safety Invariants

- Treat `inspect` and `plan` as read-only. Require current-turn authorization
  for each remote write, reload, policy save, DNS mutation, migration, or
  rollback target.
- Never expose or persist API tokens, auth keys, private keys, session data,
  environment dumps, or secret-bearing request bodies.
- Snapshot the exact current resource and keep a tested recovery path before a
  shared configuration change.
- Require one host-owned serialized transaction for each shared-resource
  mutation. Record its stable transaction ID, owner, target, base and result
  generation, desired resource digest, composed candidate digest, phase, and
  verification state without copying secrets or complete private configuration.
- Re-read authoritative and live state under the executor lock before apply.
  Treat an earlier plan as advisory; never install a stale rendered candidate.
- Detect overlapping hostnames, listeners, routes, selectors, resource IDs,
  and ownership before editing. Stop on an unresolved collision.
- Generate the complete combined plan before the first mutation. Do not let a
  successful application deployment imply that Caddy, Tailscale, DNS, or TLS
  is correct.
- Prefer product-specific skills when available. This skill remains the
  transaction owner and must reconcile their results into one final report.
- Do not broaden network access to make verification pass. Verify required
  flows positively and forbidden flows negatively.
- Keep billable, destructive, or identity-changing actions separate from
  ordinary deployment authorization.

## Control Workflow

1. Resolve the project profile and authoritative host infrastructure root.
2. Build a change matrix: owner, target, current state, desired state,
   executor, validation, rollback, and authorization state.
3. Inspect all involved products and compute one ordered plan without writes.
4. Present material exposure, deletion, billing, downtime, and recovery
   effects before requesting any missing authority.
5. Apply only authorized steps, using the relevant product reference:
   - Caddy or HTTP/TLS ingress: read [caddy.md](references/caddy.md).
   - Tailscale policy or node settings: read
     [tailscale.md](references/tailscale.md).
   - Cloudflare resources or DNS: read
     [cloudflare.md](references/cloudflare.md).
6. Apply through the host-owned lock and transaction journal. Compose from the
   latest accepted per-owner declarations, validate the complete candidate,
   atomically install, and preserve a recoverable prior generation.
7. Validate each component immediately after its change. Stop the forward
   sequence on failure and preserve evidence. A retry must resume or safely
   supersede according to the authoritative transaction, not start a blind write.
8. Run end-to-end and negative-path checks after all components pass.
9. Report repository changes, live changes, transaction identity and
   generation, credentials/configuration needed,
   compatibility, rollback state, and every item still unverified.

`inspect`, `plan`, and `verify` are read-only. `apply` and `reconcile` require
current write authority for the exact target. `rollback` requires separate
current authority and must restore only the selected owner's declaration by
recomposing the latest complete host state; it must never restore a historical
monolithic shared configuration.

## Ownership Boundaries

| Surface | Primary authority | Runtime authority |
| --- | --- | --- |
| Application port and health contract | Consuming project | Deployed application |
| Target host and service exposure | Host infrastructure repository | Target host and network |
| Caddy host mapping and shared ingress | Host infrastructure repository | Running Caddy instance |
| Tailnet access intent | Host infrastructure repository | Saved Tailscale policy and nodes |
| Cloudflare desired resources | Host infrastructure repository | Cloudflare API and IaC state |

Generated Caddy fragments, plans, caches, and inventories are derived artifacts,
not additional authorities.
