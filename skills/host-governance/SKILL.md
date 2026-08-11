---
name: host-governance
description: Query and govern shared host infrastructure across projects, including safe service-deployment inventory, guarded initial Linux server bootstrap, GitHub Actions self-hosted runners, Jenkins installation, upgrades, controller and agent configuration, credentials, plugins, jobs and Android/iOS packaging; Tailscale; Caddy; PostgreSQL; Cloudflare Tunnel, DNS, and Access. Use when an agent needs authoritative host inventory, server onboarding, CI runner configuration, deployed-service and resource observations, or inspection, planning, writes, verification, and rollback owned by the host infrastructure repository.
---

# Host Governance

Use one control workflow for infrastructure shared by multiple projects. Keep
application identity and build intent in the consuming project, and shared
compute, CI, network, ingress, DNS, and host ownership in the host
infrastructure repository.

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

## Inspect Deployed Services

When the task asks which services, containers, listeners, resource limits, or
data paths exist on a host, use the project-owned read-only
`service-inventory-inspect` control operation when it is configured. Pass one
exact device ID at a time and use only the SSH alias declared by that device's
manifest. Do not scan networks, guess addresses, install a collector, or
execute arbitrary remote commands.

When a safe snapshot already exists and the task asks for drift or sizing
advice, use the project-owned read-only `service-inventory-report` operation.
It may compare only against an explicitly declared per-device baseline; a
missing baseline or missing historical metrics is a finding, not permission to
infer desired services or resize a host.

Treat the result as a dated runtime observation, not a new source of truth.
Keep the safe JSON snapshot outside Git by default. Compare it with the
device's declared service baseline only after resolving the project profile;
promoting an observation into a repository declaration is a separate
repository-write request.

The inventory must be secret-safe: collect service names, managers, states,
versions, listeners, persistence indicators, resource limits, and bounded
capacity signals, but never environment variables, full command lines, logs,
credentials, tokens, private keys, or container secret contents. Read the
project-owned inventory reference when present for schema, platform support,
redaction, and retention rules.

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
- For an initial server-bootstrap request, treat local key creation, manifest
  edits, host-key scans, `inspect`, `plan`, and `apply` as intermediate states,
  never as proof that the server was initialized. End the task only as
  `verified complete`, `explicitly blocked`, or `rolled back`; report the
  exact remote changes and verification evidence for that terminal state.
- Consume a bootstrap password only through the contracted hidden prompt or
  approved secret source, only for the first SSH connection, and never persist,
  echo, recover from page state, or place it in argv. If the credential is not
  available when needed, stop and report the initialization as blocked; do not
  imply that password authentication was attempted.
- Treat a device ID, hostname, direct target, SSH alias, and jump-host alias as
  distinct identities. Use only aliases declared by authoritative device
  manifests or a fixed operation contract. Never guess an SSH alias from a
  device ID, and use the same declared jump route for host-key observation,
  password bootstrap, administrator-key verification, and finalize checks.
- Require a successful password-bootstrap transport to disable remote PTY
  allocation, wait for an authenticated remote-ready marker before sending a
  script, send an explicit remote exit, and distinguish pre-auth closure from
  rejected credentials. Never fall back to a direct connection when the
  contract declares a jump host.
- Treat an SSH connectivity or credential blocker as scoped to SSH. Do not
  open a provider console, call a provider API, inspect a credential-bearing
  login page, or read browser autofill values unless the user separately and
  explicitly authorizes that exact provider action.
- Never expose or persist API tokens, auth keys, private keys, session data,
  environment dumps, or secret-bearing request bodies.
- When an authorized Tailscale installation uses interactive authentication,
  capture the exact `https://login.tailscale.com/a/...` URL emitted by the
  target and return it to the user as soon as it appears. Do not wait silently
  for browser authorization, replace it with an Admin Console detour, or skip
  dependent services merely because no auth key is available. Keep the
  transaction in `awaiting-tailnet-auth`, never persist the URL, and resume
  only after the user completes authentication and live node identity is
  verified. Use only a project-contracted interactive operation when a v2
  contract is active; a missing operation is an explicit contract blocker.
- Never treat a live service inventory as a desired declaration or use a single
  point-in-time sample as proof of long-term capacity. Report freshness and
  missing historical evidence explicitly.
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
- Do not report a Tailscale installation as complete until its effective update
  channel, automatic-update behavior, package reachability, and recovery path
  have been inspected and either verified or reported as an explicit gap.
- Treat Jenkins installation, controller configuration, plugin state, agents,
  credentials, shared job runtime, backups, and upgrades as host-owned state.
  Preserve application identity and signing intent from the consuming project;
  never make a mobile build green by adopting another application's identity.
- Treat a Cloudflare public application as one coupled transaction spanning
  the origin, connector, tunnel ingress, proxied DNS, Access application, and
  Access policy. Never report a partially configured path as published or
  protected.
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
3. For service inventory, inspect only the exact requested devices and record
   collection provenance, freshness, capability gaps, and redaction status.
4. Inspect all involved products and compute one ordered plan without writes.
   Resolve contracted credential sources and verify exact API capability before
   proposing interactive browser or Dashboard authentication.
   For SSH port changes, inspect effective `sshd -T` ports, actual listeners,
   and `ssh.socket` activation and overrides. Treat a declared port without a
   live listener as blocked.
5. Present material exposure, deletion, billing, downtime, and recovery
   effects before requesting any missing authority.
6. Apply only authorized steps, using the relevant product reference:
   - Initial Linux server bootstrap: read [server-bootstrap.md](references/server-bootstrap.md).
   - GitHub Actions self-hosted runner installation or lifecycle: read
     [github-actions-runner.md](references/github-actions-runner.md).
   - Caddy or HTTP/TLS ingress: read [caddy.md](references/caddy.md).
   - Shared PostgreSQL service deployment or lifecycle: read [postgresql.md](references/postgresql.md).
   - Jenkins installation, upgrades, security, nodes, credentials, jobs, or
     Android/iOS packaging: read [jenkins.md](references/jenkins.md).
   - Tailscale installation, update readiness, policy, or node settings: read
     [tailscale.md](references/tailscale.md).
   - Cloudflare accounts, zones, DNS, or Terraform state: read
     [cloudflare.md](references/cloudflare.md).
   - Cloudflare Tunnel public hostnames and Access protection: read
     [cloudflare-tunnel.md](references/cloudflare-tunnel.md).
7. Apply through the host-owned lock and transaction journal. Compose from the
   latest accepted per-owner declarations, validate the complete candidate,
   atomically install, and preserve a recoverable prior generation.
8. Validate each component immediately after its change. Stop the forward
   sequence on failure and preserve evidence. A retry must resume or safely
   supersede according to the authoritative transaction, not start a blind write.
9. For initial server bootstrap, verify a fresh administrator-key connection
   on the desired SSH port plus rejection of password and prohibited root login
   before retiring the old key, closing the bootstrap port, or claiming
   completion. Treat service installation and external enrollment checks as
   separate required evidence when enabled.
   When systemd socket activation owns SSH listeners, snapshot and configure
   its override in the same host transaction; reloading only `ssh.service` is
   not evidence that a new port is listening. Keep the old listener until the
   new one is positively reachable through the declared route.
10. Run end-to-end and negative-path checks after all components pass.
    Treat local key generation, the local SSH host block, plaintext credential
    removal, identity-file migration, and old-key retirement as explicit local
    host operations. If the executor cannot write `~/.ssh`, report that exact
    permission blocker and emit a bounded patch; never imply the remote
    transaction updated local SSH configuration.
11. Report repository changes, live changes, transaction identity and
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
| Application source, identity, build, and signing intent | Consuming project | Source and signing authorities |
| Desired per-device service deployment baseline | Host infrastructure repository | Repository declaration and owning runtime |
| Live service inventory and capacity observation | Runtime host | Bounded read-only collector |
| Target host and service exposure | Host infrastructure repository | Target host and network |
| Jenkins installation, controller, plugins, nodes, credentials, backups, and upgrades | Host infrastructure repository | Jenkins controller and agents |
| Jenkins job definition and execution state | Host infrastructure repository | Jenkins controller and agents |
| Caddy host mapping and shared ingress | Host infrastructure repository | Running Caddy instance |
| Tailnet access intent | Host infrastructure repository | Saved Tailscale policy and nodes |
| Cloudflare desired resources | Host infrastructure repository | Cloudflare API and IaC state |
| Cloudflare connector placement and runtime | Host infrastructure repository | Target host and Cloudflare edge |
| Cloudflare Access application and policy | Host infrastructure repository | Cloudflare Access API |

Generated Caddy fragments, plans, caches, and inventories are derived artifacts,
not additional authorities.
