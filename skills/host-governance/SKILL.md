---
name: host-governance
description: >-
  Govern shared hosts and infrastructure across projects: authoritative inventory, server bootstrap, Docker/storage, CI runners and Jenkins, PostgreSQL, Tailscale, Caddy, Cloudflare, resource inspection, and reusable host operations. Use for shared-host reads, plans, authorized mutations, verification, rollback, or incident recovery.
metadata:
  context-budget: router
---

# Host Governance

Own shared compute, CI, network, ingress, DNS, and host transactions. Keep application identity and build intent in the consuming project; keep host facts and controllers in the authoritative host repository.

## Locate Authority

Use the first unambiguous source: current user path, authority already established for the task, `HOST_INFRA_ROOT`, then the locator in [context.md](references/context.md). Do not scan or copy infrastructure inventory.

Repository context is declared evidence, not live state. Use contracted `catalog`, `search`, `get`, or `current-device`; never infer a device, alias, address, credential, or freshness claim. Resolve `control` separately for live reads or writes.

## Resolve and Execute

From the authoritative or consuming project, resolve the selected task and operation:

```bash
uv run python <skill-root>/scripts/resolve.py \
  --cwd <project-root> --task <task> --operation <operation> --format json
```

For `host-governance.config.v2`, read the returned policy references and execute only through the validated runner:

```bash
uv run python <skill-root>/scripts/host-governance.py \
  --cwd <project-root> control <operation> [contracted arguments]
```

Use `--authorized` only when current user intent covers the non-read-only operation. The runner validates argv, parameters, mutability, authorization, secret environment requirements, outputs, exit states, and transitions. Never bypass a v2 contract with its underlying command. Legacy v1 output is instruction-only. Read [project_config.md](references/project_config.md) before changing a profile.

## Route the Operation

- Generic transaction planning and ownership: [control.md](references/control.md).
- Explicit request to turn a procedure into a reusable contracted function: [procedure-productization.md](references/procedure-productization.md).
- Initial Linux server bootstrap: [server-bootstrap.md](references/server-bootstrap.md).
- Docker Engine/Compose installation and bounded BuildKit cleanup: [docker-install.md](references/docker-install.md).
- Docker volume leaks or runtime storage incidents: [docker-storage-maintenance.md](references/docker-storage-maintenance.md).
- GitHub Actions runner: [github-actions-runner.md](references/github-actions-runner.md).
- Jenkins controller, agents, plugins, credentials, jobs, backup, upgrade, or mobile packaging: [jenkins.md](references/jenkins.md).
- PostgreSQL deployment, sizing, parameters, or lifecycle: [postgresql.md](references/postgresql.md); run `scripts/postgres_sizing.py` before rendering parameters.
- Tailscale installation, update posture, policy, or node settings: [tailscale.md](references/tailscale.md).
- Caddy and HTTP/TLS ingress: [caddy.md](references/caddy.md).
- Cloudflare accounts, DNS, WAF/Rulesets, or selective 403 diagnosis: [cloudflare.md](references/cloudflare.md).
- Cloudflare Tunnel and Access publication: [cloudflare-tunnel.md](references/cloudflare-tunnel.md).

For deployed service, listener, limit, persistence, or capacity inventory, use only the project-owned read-only inventory operation for one exact device. Collect secret-safe bounded facts; never environment values, full command lines, logs, keys, tokens, or container secret content. Treat snapshots as dated observations, not desired state.

## Authorization and Safety

Read [authorization-and-safety.md](references/authorization-and-safety.md) before any host or provider mutation, bootstrap, credential use, emergency manual operation, or conversation-scoped SSH execution. Core invariants:

- `inspect`, `plan`, and `verify` are read-only. Writes use an authorized contracted transaction; rollback and materially broader effects require their own current scope.
- One explicit `授权手动进行紧急操作` grants only the current bounded execution round. It expires on completion, blocker, or return to the user and never creates persistent arbitrary-command capability.
- Conversation-scoped SSH authorization covers only SSH actions for the established task and target; it does not authorize provider consoles, APIs, billing, identity changes, release, or new targets.
- Never expose or persist tokens, passwords, private keys, session data, environment dumps, secret request bodies, or interactive login URLs.
- Use only manifest-declared device IDs, SSH aliases, ports, and jump routes. Never guess or bypass a jump host.
- Snapshot current state, lock one serialized host transaction, re-read under lock, reject drift/collisions, validate the complete candidate, preserve recovery, and verify positive and negative paths.
- Do not broaden network access to make validation pass. Keep destructive, billable, privileged, exposure-changing, and identity-changing outcomes separate.

## Separate One-Time Operations from Productization

A request to execute, repair, recover, clean up, migrate, or order steps for one current target is a one-time operation, even when the method could be reused. Selecting a plan or sequence authorizes only that execution path; governance requirements, repetition history, summaries, and prior assistant proposals do not authorize a durable capability.

For a one-time operation, resolve and compose existing contracted operations. Do not edit the host repository, controllers, contracts, tests, documentation, or versions, and do not install or publish a capability. If no existing operation can safely complete it, report the missing capability or use only an explicitly authorized one-round manual exception.

Productize only when the current user explicitly asks to create, automate, contract, or retain a reusable long-term host capability. Then first resolve an existing contracted controller; otherwise follow [procedure-productization.md](references/procedure-productization.md). Never create a generic shell-fragment or arbitrary-package executor.

## Control Workflow

1. Establish project intent, host authority, exact target, current live state, and owner for every desired fact.
2. Build one matrix covering current/desired state, executor, authorization, validation, exposure, recovery, and rollback.
3. Inspect all coupled products before the first write; a repository declaration is not a runtime claim.
4. Apply only the authorized contracted operations under the host-owned lock. Stop on drift, collision, unexpected output, or failed verification.
5. Verify each component immediately, then run end-to-end and negative-path checks.
6. End bootstrap or recovery only as verified complete, explicitly blocked, or rolled back. Partial setup is not completion.

Product-specific completion details remain in their owning references. Examples include hardware-aware PostgreSQL sizing, root-equivalent Docker group access, separate authorization for volume deletion, fresh administrator-key bootstrap verification, immediate return of a Tailscale interactive login URL, and coupled Cloudflare origin/tunnel/DNS/Access verification.

## Report

Report repository and live changes separately; exact target, transaction/generation, validation evidence, secret-safe credential requirements, exposure, recovery/rollback state, compatibility, and every unverified gap. Do not promote observations to desired declarations without separate repository-write authority.
